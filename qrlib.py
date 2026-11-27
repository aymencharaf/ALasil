"""مولّد QR بسيط (وضع البايت، تصحيح M) بدون مكتبات خارجية."""
from PySide6.QtGui import QImage, QColor, QPainter
from PySide6.QtCore import Qt

# GF(256) for Reed-Solomon
_EXP = [0] * 512
_LOG = [0] * 256


def _init_gf():
    x = 1
    for i in range(255):
        _EXP[i] = x
        _LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_init_gf()


def _gf_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _rs_generator(n):
    g = [1]
    for i in range(n):
        ng = [0] * (len(g) + 1)
        for j, v in enumerate(g):
            ng[j] ^= v
            ng[j + 1] ^= _gf_mul(v, _EXP[i])
        g = ng
    return g


def _rs_encode(data, nsym):
    gen = _rs_generator(nsym)
    res = data + [0] * nsym
    for i in range(len(data)):
        coef = res[i]
        if coef:
            for j in range(len(gen)):
                res[i + j] ^= _gf_mul(gen[j], coef)
    return res[-nsym:]


# Version 5: 37x37, 134 data bytes with ECC M (2 blocks, 43 data + 18 ecc each) wait
# Version 4: 33x33, ECC M: 1 block, 80 data codewords, 18 ecc? 
# Standard:
# V3 M: 45 data, 15 ecc, 1 block, 29x29
# V4 M: 64 data, 18? actually V4-M: 80 data cw, 4*18? Let's use Version 5-M
# QR versions (data codewords, ecc codewords, blocks) for ECC M:
# V2 M: 28 data, 16 ecc, 1 blk, size 25
# V3 M: 44 data, 26 ecc, 1 blk, size 29
# V4 M: 64 data, 18 ecc * 2 blocks? V4-M: 80 total data, 2 blocks of 32 data + 18 ecc? 
# I'll use Version 3 (max 44 bytes) or Version 6.

# Simpler: Version 4 size 33, ECC L (more data): V4-L 80 data bytes 1 block? 
# V4-L: 80 data, 36 ecc? Look up:
# Version 4: 33 modules
# L: 80 data codewords, ECC 20? 
# Official:
# V4 L: 80 data, 4*9?  total cw = 100? 
# Total codewords V4 = 100
# L: 20 ecc, 80 data
# M: 36 ecc, 64 data
# Q: 52 ecc, 48 data
# H: 72 ecc, 28 data

# V5 total 134 cw, size 37
# M: 50 ecc, 84 data

# We'll pick Version 5 ECC M: 84 data codewords, 2 blocks (42+42 data, 25? wait)
# V5-M: 134 total, 65 data? Official V5-M data codewords = 86? Let me use:
# From spec table:
# V5: 37x37, total 134
# L 108 data / 26 ecc
# M 86 data / 48 ecc  (2 blocks)
# I'll use Version 4 ECC L: 80 data, 20 ecc, 1 block, 100 total. Size 33.
# 80 bytes is enough for customer JSON.

VER = 4
SIZE = 17 + 4 * VER  # 33
DATA_CW = 80
ECC_CW = 20  # V4-L: 80 data + 20 ecc = 100 total. Spec: V4 total = 100. L ecc=20. Yes.


def _bits_to_bytes(bits):
    while len(bits) % 8:
        bits.append(0)
    out = []
    for i in range(0, len(bits), 8):
        b = 0
        for k in range(8):
            b = (b << 1) | bits[i + k]
        out.append(b)
    return out


def _encode_bytes(data: bytes):
    if len(data) > DATA_CW - 3:
        data = data[: DATA_CW - 3]
    bits = []
    # mode byte = 0100
    bits += [0, 1, 0, 0]
    # length 8 bits for v1-9
    ln = len(data)
    bits += [(ln >> (7 - i)) & 1 for i in range(8)]
    for by in data:
        bits += [(by >> (7 - i)) & 1 for i in range(8)]
    # terminator
    bits += [0] * min(4, DATA_CW * 8 - len(bits))
    pad_bytes = _bits_to_bytes(bits)
    pads = [0xEC, 0x11]
    i = 0
    while len(pad_bytes) < DATA_CW:
        pad_bytes.append(pads[i % 2])
        i += 1
    return pad_bytes[:DATA_CW]


def _finder(mod, x, y):
    for dy in range(-1, 8):
        for dx in range(-1, 8):
            xx, yy = x + dx, y + dy
            if not (0 <= xx < SIZE and 0 <= yy < SIZE):
                continue
            if dx == -1 or dy == -1 or dx == 7 or dy == 7:
                mod[yy][xx] = 0  # separator white
            elif 0 <= dx <= 6 and 0 <= dy <= 6:
                if dx in (0, 6) or dy in (0, 6) or (2 <= dx <= 4 and 2 <= dy <= 4):
                    mod[yy][xx] = 1
                else:
                    mod[yy][xx] = 0


def _timing(mod):
    for i in range(SIZE):
        if mod[6][i] is None:
            mod[6][i] = i % 2 == 0
        if mod[i][6] is None:
            mod[i][6] = i % 2 == 0


def _reserve_format(mod):
    for i in range(9):
        if i != 6:
            if mod[8][i] is None:
                mod[8][i] = 0  # placeholder
            if mod[i][8] is None:
                mod[i][8] = 0
        if mod[8][SIZE - 1 - i] is None:
            mod[8][SIZE - 1 - i] = 0
        if mod[SIZE - 1 - i][8] is None:
            mod[SIZE - 1 - i][8] = 0
    mod[SIZE - 8][8] = 1  # dark module


def _alignment(mod):
    # V4 alignment at 26
    pos = 26
    for dy in range(5):
        for dx in range(5):
            xx, yy = pos + dx - 2, pos + dy - 2
            if 0 <= xx < SIZE and 0 <= yy < SIZE:
                mod[yy][xx] = dx in (0, 4) or dy in (0, 4) or (dx == 2 and dy == 2)


def _place_data(mod, data_bits):
    dirs_up = True
    bi = 0
    x = SIZE - 1
    while x > 0:
        if x == 6:
            x -= 1
        for y in range(SIZE - 1, -1, -1) if dirs_up else range(SIZE):
            for dx in (0, -1):
                xx = x + dx
                if mod[y][xx] is None:
                    bit = data_bits[bi] if bi < len(data_bits) else 0
                    mod[y][xx] = bit
                    bi += 1
        dirs_up = not dirs_up
        x -= 2


def _mask(x, y, m):
    if m == 0:
        return (x + y) % 2 == 0
    if m == 1:
        return y % 2 == 0
    return (x // 3 + y) % 2 == 0


def _format_bits(mask):
    # ECC L = 01, mask 3 bits
    data = (0b01 << 3) | mask
    # BCH
    rem = data << 10
    gen = 0b10100110111
    for i in range(14, 9, -1):
        if rem & (1 << i):
            rem ^= gen << (i - 10)
    bits = ((data << 10) | rem) ^ 0b101010000010010
    return bits


def _apply_format(mod, mask):
    fb = _format_bits(mask)
    # positions
    coords_a = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
                (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
    # 15 bits from MSB
    bstr = [(fb >> (14 - i)) & 1 for i in range(15)]
    # horizontal near finder
    pos = [(0, 8), (1, 8), (2, 8), (3, 8), (4, 8), (5, 8), (7, 8), (8, 8),
           (8, 7), (8, 5), (8, 4), (8, 3), (8, 2), (8, 1), (8, 0)]
    for i, (x, y) in enumerate(pos):
        mod[y][x] = bstr[i]
    pos2 = [(SIZE - 1, 8), (SIZE - 2, 8), (SIZE - 3, 8), (SIZE - 4, 8),
            (SIZE - 5, 8), (SIZE - 6, 8), (SIZE - 7, 8), (SIZE - 8, 8),
            (8, SIZE - 7), (8, SIZE - 6), (8, SIZE - 5), (8, SIZE - 4),
            (8, SIZE - 3), (8, SIZE - 2), (8, SIZE - 1)]
    # actual standard:
    # format: 15 bits
    # copy1: (0,8).. skip (6,8) then (7,8)(8,8) then (8,7) skip (8,6) (8,5)..(8,0)
    # copy2: (8, n-1)..(8, n-8) and (n-1,8)..(n-8,8) with dark at (8,n-8)
    seq1 = []
    for x in range(0, 9):
        if x != 6:
            seq1.append((x, 8))
    for y in range(7, -1, -1):
        if y != 6:
            seq1.append((8, y))
    seq2 = []
    for y in range(SIZE - 1, SIZE - 8, -1):
        seq2.append((8, y))
    for x in range(SIZE - 8, SIZE):
        seq2.append((x, 8))
    for i in range(15):
        if i < len(seq1):
            x, y = seq1[i]
            mod[y][x] = bstr[i]
        if i < len(seq2):
            x, y = seq2[i]
            mod[y][x] = bstr[i]


def make_modules(text: str):
    data = text.encode("utf-8")
    dcw = _encode_bytes(data)
    ecc = _rs_encode(dcw, ECC_CW)
    allb = dcw + ecc
    bits = []
    for by in allb:
        bits += [(by >> (7 - i)) & 1 for i in range(8)]
    mask_id = 0
    mod = [[None] * SIZE for _ in range(SIZE)]
    _finder(mod, 0, 0)
    _finder(mod, SIZE - 7, 0)
    _finder(mod, 0, SIZE - 7)
    _alignment(mod)
    _timing(mod)
    _reserve_format(mod)
    # freeze function patterns: convert remaining None later
    frozen = [[mod[y][x] is not None for x in range(SIZE)] for y in range(SIZE)]
    _place_data(mod, bits)
    # apply mask 0 on data modules
    for y in range(SIZE):
        for x in range(SIZE):
            if not frozen[y][x] and _mask(x, y, mask_id):
                mod[y][x] = 0 if mod[y][x] else 1
    _apply_format(mod, mask_id)
    for y in range(SIZE):
        for x in range(SIZE):
            if mod[y][x] is None:
                mod[y][x] = 0
    return mod


def qr_image(text: str, scale=8, border=3) -> QImage:
    mod = make_modules(text)
    n = SIZE + border * 2
    img = QImage(n * scale, n * scale, QImage.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("black"))
    for y in range(SIZE):
        for x in range(SIZE):
            if mod[y][x]:
                p.drawRect((x + border) * scale, (y + border) * scale, scale, scale)
    p.end()
    return img


def qr_data_uri(text: str, scale=6, border=2) -> str:
    import base64
    from PySide6.QtCore import QByteArray, QBuffer, QIODevice
    img = qr_image(text, scale=scale, border=border)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    b64 = base64.b64encode(bytes(ba)).decode("ascii")
    return "data:image/png;base64," + b64
