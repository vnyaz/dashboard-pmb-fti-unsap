import sqlite3
import hashlib

DB_PATH = "database.db"
conn = sqlite3.connect(DB_PATH)

# Cek kolom yang ada sekarang
cols = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
print("Kolom saat ini:", cols)

# Drop tabel lama dan buat ulang dengan struktur benar
conn.execute("DROP TABLE IF EXISTS users")
conn.execute("""
CREATE TABLE users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    nama           TEXT    NOT NULL,
    email          TEXT    NOT NULL UNIQUE,
    password_hash  TEXT    NOT NULL,
    role           TEXT    NOT NULL DEFAULT 'internal',
    status         TEXT    NOT NULL DEFAULT 'Aktif',
    terakhir_login TEXT
)
""")

pw_hash = hashlib.sha256("admin123".encode()).hexdigest()
conn.execute(
    "INSERT INTO users (nama, email, password_hash, role, status) VALUES (?,?,?,?,?)",
    ("Admin BAAK FTI", "admin@unsap.ac.id", pw_hash, "admin", "Aktif")
)
conn.commit()

row = conn.execute(
    "SELECT id, nama, email, role, status FROM users WHERE email='admin@unsap.ac.id'"
).fetchone()
print("Berhasil. Data:", row)
print("Coba login: admin@unsap.ac.id / admin123")
conn.close()