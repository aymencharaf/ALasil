package com.alasil.scanner

import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

class SettingsActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)
        val p = getSharedPreferences("alasil", MODE_PRIVATE)
        val host = findViewById<EditText>(R.id.host)
        val port = findViewById<EditText>(R.id.port)
        val token = findViewById<EditText>(R.id.token)
        host.setText(p.getString("host", "192.168.1.1"))
        port.setText(p.getString("port", "8765"))
        token.setText(p.getString("token", "alasil"))
        findViewById<Button>(R.id.save).setOnClickListener {
            p.edit()
                .putString("host", host.text.toString().trim())
                .putString("port", port.text.toString().trim())
                .putString("token", token.text.toString().trim())
                .apply()
            Toast.makeText(this, "تم الحفظ", Toast.LENGTH_SHORT).show()
            finish()
        }
    }
}
