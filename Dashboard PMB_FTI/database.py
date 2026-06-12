import sqlite3
import hashlib
from datetime import datetime

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
DB_NAME = BASE_DIR / "database.db"
# =====================================================
# KONEKSI DATABASE
# =====================================================

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# =====================================================
# INIT DATABASE
# =====================================================

def init_db():

    conn = get_connection()
    c = conn.cursor()

    # =================================================
    # USERS
    # =================================================
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL,
        status TEXT DEFAULT 'Aktif',
        created_at TEXT,
        last_login TEXT
    )
    """)

    # =================================================
    # HISTORI PREDIKSI
    # =================================================
    c.execute("""
    CREATE TABLE IF NOT EXISTS prediksi_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tahun INTEGER,
        biaya_kuliah REAL,
        akreditasi INTEGER,
        kuota_beasiswa INTEGER,
        jumlah_prodi INTEGER,
        hasil_prediksi REAL,
        created_by TEXT,
        created_at TEXT
    )
    """)

    # =================================================
    # EVALUASI MODEL
    # =================================================
    c.execute("""
    CREATE TABLE IF NOT EXISTS model_evaluation (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mae REAL,
        mse REAL,
        rmse REAL,
        r2_score REAL,
        jumlah_data INTEGER,
        training_date TEXT
    )
    """)

    # =================================================
    # LOG DATASET
    # =================================================
    c.execute("""
    CREATE TABLE IF NOT EXISTS dataset_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama_file TEXT,
        jumlah_data INTEGER,
        uploaded_by TEXT,
        uploaded_at TEXT
    )
    """)

    # =================================================
    # DEFAULT USER
    # =================================================

    admin_password = hashlib.sha256(
        "admin123".encode()
    ).hexdigest()

    user_password = hashlib.sha256(
        "user123".encode()
    ).hexdigest()

    # cek admin
    c.execute(
        "SELECT * FROM users WHERE email=?",
        ("admin@unsap.ac.id",)
    )

    if not c.fetchone():

        c.execute("""
        INSERT INTO users (
            nama,
            email,
            password,
            role,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """, (
            "Admin BAAK FTI",
            "admin@unsap.ac.id",
            admin_password,
            "admin",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

    # cek user
    c.execute(
        "SELECT * FROM users WHERE email=?",
        ("user@unsap.ac.id",)
    )

    if not c.fetchone():

        c.execute("""
        INSERT INTO users (
            nama,
            email,
            password,
            role,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """, (
            "Staff FTI",
            "user@unsap.ac.id",
            user_password,
            "user",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

    conn.commit()
    conn.close()

# =====================================================
# GET USER BY EMAIL
# =====================================================

def get_user_by_email(email):

    conn = get_connection()
    c = conn.cursor()

    c.execute(
        "SELECT * FROM users WHERE email=?",
        (email,)
    )

    user = c.fetchone()

    conn.close()

    return user


# =====================================================
# UPDATE LAST LOGIN
# =====================================================

def update_last_login(email):

    conn = get_connection()
    c = conn.cursor()

    c.execute("""
    UPDATE users
    SET last_login=?
    WHERE email=?
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        email
    ))

    conn.commit()
    conn.close()