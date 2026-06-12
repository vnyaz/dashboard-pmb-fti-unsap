import base64
import hashlib
import mimetypes
import sqlite3
from datetime import datetime
from pathlib import Path

import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "logo_fti.png"
DB_PATH   = BASE_DIR / "database.db"


def hash_password(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def get_logo_src():
    if LOGO_PATH.exists():
        mime_type   = mimetypes.guess_type(LOGO_PATH)[0] or "image/png"
        logo_base64 = base64.b64encode(LOGO_PATH.read_bytes()).decode()
        return f"data:{mime_type};base64,{logo_base64}"
    return ""


def ensure_default_admin():
    """
    Jika tabel users kosong, buat akun admin default:
      email   : admin@unsap.ac.id
      password: admin123
    Ini hanya fallback — segera ganti via Manajemen Akun setelah login pertama.
    """
    if not DB_PATH.exists():
        return
    try:
        with sqlite3.connect(DB_PATH) as conn:
            # pastikan tabel ada
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    nama           TEXT    NOT NULL,
                    email          TEXT    NOT NULL UNIQUE,
                    password_hash  TEXT    NOT NULL,
                    role           TEXT    NOT NULL DEFAULT 'internal',
                    status         TEXT    NOT NULL DEFAULT 'Aktif',
                    terakhir_login TEXT
                )
            """)
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if count == 0:
                conn.execute(
                    "INSERT INTO users (nama, email, password_hash, role, status) VALUES (?,?,?,?,?)",
                    ("Admin BAAK FTI", "admin@unsap.ac.id", hash_password("admin123"), "admin", "Aktif"),
                )
                conn.commit()
    except Exception:
        pass


def verify_login(email: str, password: str):
    """
    Return (role, nama) jika cocok dan aktif, atau:
      ("nonaktif", nama) jika akun dinonaktifkan
      (None, None)       jika tidak ditemukan / password salah
    """
    if not DB_PATH.exists():
        return None, None
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                """
                SELECT role, nama, status
                FROM   users
                WHERE  LOWER(email) = LOWER(?)
                  AND  password_hash = ?
                """,
                (email.strip(), hash_password(password)),
            ).fetchone()
        if row:
            role, nama, status = row
            if status != "Aktif":
                return "nonaktif", nama
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "UPDATE users SET terakhir_login = ? WHERE LOWER(email) = LOWER(?)",
                    (datetime.now().strftime("%d %b %Y %H:%M"), email.strip()),
                )
                conn.commit()
            return role, nama
    except Exception:
        pass
    return None, None


def login_page():
    # Seed admin default jika tabel kosong
    ensure_default_admin()

    logo_src = get_logo_src()

    st.markdown(
        """
        <style>
        .stApp { background: linear-gradient(135deg, #4A8E93, #C4C96B); }
        [data-testid="stHeader"]  { display: none; }
        [data-testid="stSidebar"] { display: none; }
        .block-container {
            max-width: 760px !important;
            margin-top: 110px !important;
            padding: 46px 90px 42px 90px !important;
            background-color: #ffffff;
            box-shadow: 0 3px 8px rgba(0,0,0,.25);
        }
        div[data-testid="stForm"] { border:none; padding:0; }
        label { color:#111827 !important; font-size:15px !important; font-weight:400 !important; }
        .stTextInput input {
            height:42px !important; background-color:#d9d9d9 !important;
            color:#111827 !important; border:none !important;
            border-radius:0 !important; box-shadow:none !important;
        }
        .stTextInput input:focus { border:1px solid #FFC400 !important; box-shadow:none !important; }
        .stFormSubmitButton { display:flex; justify-content:flex-end; margin-top:12px; }
        .stFormSubmitButton button {
            background-color:#FFC400 !important; color:white !important;
            border:none !important; border-radius:0 !important;
            padding:8px 38px !important; font-weight:800 !important; font-size:16px !important;
        }
        .stFormSubmitButton button:hover { background-color:#e6b000 !important; }
        .back-link { text-align:right; margin-top:-6px; }
        .back-link a { color:#b8b8b8; text-decoration:none; font-size:13px; }
        .back-link a:hover { color:#777777; }
        .login-logo { display:flex; justify-content:center; margin-bottom:8px; }
        .login-logo img { width:92px; height:92px; object-fit:contain; }
        .login-title { text-align:center; color:#111827; font-size:30px;
                       line-height:1.22; margin-bottom:18px; }
        .login-title span { display:block; font-size:25px; }
        [data-testid="stAlert"] { margin-top:14px; }
        @media (max-width: 768px) {
            .block-container { margin-top: 40px !important; padding: 30px 20px !important; }
            .login-title { font-size: 24px; }
            .login-title span { font-size: 20px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.html(
        f"""
        <div class="login-logo"><img src="{logo_src}"></div>
        <div class="login-title">
            Login
            <span>Sistem Prediksi Mahasiswa Baru</span>
            <span>Fakultas Teknologi Informasi</span>
        </div>
        """
    )

    with st.form("login_form"):
        email         = st.text_input("Email")
        password      = st.text_input("Password", type="password")
        login_clicked = st.form_submit_button("LOGIN")

    st.markdown(
        '<div class="back-link"><a href="/" target="_self">← Kembali ke beranda</a></div>',
        unsafe_allow_html=True,
    )

    if login_clicked:
        if not email.strip() or not password:
            st.error("Email dan password wajib diisi.")
            return

        role, nama = verify_login(email, password)

        if role == "nonaktif":
            st.error("Akun Anda dinonaktifkan. Hubungi administrator.")
        elif role is None:
            st.error("Email atau password salah.")
        else:
            st.session_state.logged_in = True
            st.session_state.role      = role
            st.session_state.nama      = nama

            st.query_params["logged_in"] = "true"
            st.query_params["role"]      = role
            st.query_params["page"]      = "Dashboard"
            st.rerun()