import base64
import hashlib
import html
import sqlite3
from pathlib import Path
from textwrap import dedent
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "database.db"

# ── DB helpers ────────────────────────────────────────────────────────────────
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def ensure_users_table():
    with get_connection() as conn:
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
        conn.commit()

def hash_password(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()

def is_valid_sha256(s: str) -> bool:
    if len(s) != 64:
        return False
    try:
        int(s, 16)
        return True
    except ValueError:
        return False

def load_users():
    ensure_users_table()
    try:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, nama, email, role, status, terakhir_login FROM users ORDER BY id"
            ).fetchall()
        return [
            {
                "id": r[0],
                "nama": r[1],
                "email": r[2],
                "role": r[3],
                "status": r[4],
                "terakhir_login": r[5] or "-",
            }
            for r in rows
        ]
    except Exception:
        return []

def insert_user(nama, email, password_hash, role, status):
    ensure_users_table()
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO users (nama, email, password_hash, role, status) VALUES (?,?,?,?,?)",
                (nama.strip(), email.strip(), password_hash, role, status),
            )
            conn.commit()
        return True, None
    except sqlite3.IntegrityError:
        return False, "Email sudah terdaftar."
    except Exception as e:
        return False, str(e)

def update_user(user_id, nama, email, role, status, new_password_hash=None):
    ensure_users_table()
    try:
        with get_connection() as conn:
            if new_password_hash:
                conn.execute(
                    "UPDATE users SET nama=?, email=?, role=?, status=?, password_hash=? WHERE id=?",
                    (nama.strip(), email.strip(), role, status, new_password_hash, user_id),
                )
            else:
                conn.execute(
                    "UPDATE users SET nama=?, email=?, role=?, status=? WHERE id=?",
                    (nama.strip(), email.strip(), role, status, user_id),
                )
            conn.commit()
        return True, None
    except sqlite3.IntegrityError:
        return False, "Email sudah digunakan akun lain."
    except Exception as e:
        return False, str(e)

def delete_user(user_id):
    ensure_users_table()
    try:
        with get_connection() as conn:
            conn.execute("DELETE FROM users WHERE id=?", (user_id,))
            conn.commit()
        return True, None
    except Exception as e:
        return False, str(e)

def get_user_by_id(user_id):
    ensure_users_table()
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id, nama, email, role, status FROM users WHERE id=?", (user_id,)
            ).fetchone()
        if row:
            return {"id": row[0], "nama": row[1], "email": row[2], "role": row[3], "status": row[4]}
    except Exception:
        pass
    return None

# ── Asset helper ──────────────────────────────────────────────────────────────
def icon_svg(name):
    icon_paths = {
        "dashboard": "assets/dashboard_utama.png",
        "database":  "assets/datahistoris_sidebar.png",
        "chart":     "assets/prediksi_sidebar.png",
        "list":      "assets/evaluasi_sidebar.png",
        "account":   "assets/akun_sidebar.png",
        "report":    "assets/dokumen_sidebar.png",
        "logout":    "assets/logout.png",
    }
    path = BASE_DIR / icon_paths.get(name, "")
    if not path.is_file():
        return ""
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{b64}" alt="{name}">'

def _base_css():
    return """
    [data-testid="stHeader"], [data-testid="stSidebar"] { display:none !important; }
    html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"] { margin:0 !important; padding:0 !important; }
    .stApp { background:#e3e7eb; }
    .block-container { max-width:100% !important; padding:0 !important; margin:0 !important; }
    .akun-shell { position:fixed; inset:0; z-index:999; height:100vh; overflow-y:auto;
                  display:grid; grid-template-columns:280px 1fr;
                  background:#e3e7eb; color:#123047; font-family:Arial,sans-serif; }
    .akun-sidebar { background:#4a9498; color:white; padding:36px 22px 28px;
                    display:flex; flex-direction:column; min-height:180vh; }
    .brand-title   { font-size:21px; font-weight:800; line-height:1.2; }
    .brand-subtitle { font-size:13px; font-weight:700; margin-top:6px; padding-bottom:18px;
                      border-bottom:1px solid rgba(255,255,255,.25); }
    .side-menu  { margin-top:24px; display:grid; gap:16px; }
    .side-item  { color:white; text-decoration:none; display:flex; align-items:center;
                  gap:13px; padding:11px 10px; border-radius:4px; font-size:16px; line-height:1.35; }
    .side-item.active { background:#e9c91d; }
    .side-icon  { width:24px; height:24px; flex:0 0 24px; display:inline-flex;
                  align-items:center; justify-content:center; }
    .side-icon img { width:23px; height:23px; object-fit:contain; }
    .sidebar-user { margin-top:auto; padding:16px 8px 0;
                    border-top:1px solid rgba(255,255,255,.25);
                    color:rgba(255,255,255,.6); line-height:1.35; font-size:16px; }
    .logout-link { margin-top:220px; color:white; text-decoration:none;
                   display:flex; align-items:center; gap:12px; font-size:16px; }
    .akun-header { height:84px; background:white; display:flex; align-items:center;
                   padding:0 28px; box-shadow:0 2px 6px rgba(0,0,0,.25); flex-shrink:0; }
    .akun-header h1 { margin:0; color:#4a9498; font-size:28px; font-weight:800; line-height:1.05; }
    .akun-header span { display:block; color:#4a9498; font-size:17px; margin-top:5px; font-weight:800; }
    .akun-content { padding:34px 52px 52px; }
    """

def _sidebar_nav(base, active_name, role_label):
    return f"""
    <aside class="akun-sidebar">
        <div class="brand-title">Prediksi Mahasiswa</div>
        <div class="brand-subtitle">Fakultas Teknologi Informasi</div>
        <nav class="side-menu">
            <a class="side-item" href="{base}&page=Dashboard"  target="_top"><span class="side-icon">{icon_svg('dashboard')}</span>Dashboard Utama</a>
            <a class="side-item" href="{base}&page=Histori"    target="_top"><span class="side-icon">{icon_svg('database')}</span>Data Historis</a>
            <a class="side-item" href="{base}&page=Prediksi"   target="_top"><span class="side-icon">{icon_svg('chart')}</span>Prediksi Mahasiswa Baru</a>
            <a class="side-item" href="{base}&page=Evaluasi"   target="_top"><span class="side-icon">{icon_svg('list')}</span>Evaluasi Model</a>
            <a class="side-item active" href="{base}&page=Akun" target="_top"><span class="side-icon">{icon_svg('account')}</span>Manajemen Akun</a>
            <a class="side-item" href="{base}&page=Laporan"    target="_top"><span class="side-icon">{icon_svg('report')}</span>Visualisasi dan Laporan</a>
        </nav>
        <div class="sidebar-user">{html.escape(active_name)}<br>{html.escape(role_label)}</div>
        <a class="logout-link" href="/?logout=true" target="_top"><span class="side-icon">{icon_svg('logout')}</span>Log out</a>
    </aside>
    """

def _form_css():
    return """
    .form-card { background:white; box-shadow:0 3px 8px rgba(0,0,0,.25);
                 padding:28px 32px 36px; max-width:480px; }
    .form-card-title { color:#4a9498; font-size:18px; font-weight:800; margin-bottom:20px; }
    .form-group { margin-bottom:16px; display:flex; flex-direction:column; gap:6px; }
    .form-label { font-size:13px; font-weight:700; color:#4a4f52; }
    .form-hint  { font-size:11px; color:#8a9ba3; font-weight:600; margin-top:2px; }
    .form-input { border:1px solid #cfd8dc; border-radius:4px; padding:9px 12px;
                  font-size:14px; color:#123047; outline:none; width:100%; box-sizing:border-box; }
    .form-input:focus { border-color:#4a9498; box-shadow:0 0 0 2px rgba(74,148,152,.15); }
    .form-select { border:1px solid #cfd8dc; border-radius:4px; padding:9px 12px;
                   font-size:14px; color:#123047; outline:none; width:100%; box-sizing:border-box;
                   background:white; cursor:pointer; }
    .form-select:focus { border-color:#4a9498; }
    .form-row { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:8px; }
    .btn-simpan { background:#4a9498; color:white; border:none; border-radius:4px;
                  padding:10px 0; font-size:14px; font-weight:800; cursor:pointer; width:100%; }
    .btn-simpan:hover { background:#3a7d80; }
    .btn-simpan:disabled { background:#9abcbe; cursor:not-allowed; }
    .btn-batal { background:white; color:#52666d; border:1px solid #cfd8dc; border-radius:4px;
                 padding:10px 0; font-size:14px; font-weight:800; cursor:pointer; width:100%;
                 text-decoration:none; display:flex; align-items:center; justify-content:center; }
    .btn-batal:hover { background:#f1f5f8; }
    .form-error { background:#fee2e2; border:1px solid #fca5a5; color:#991b1b;
                  padding:10px 14px; border-radius:4px; font-size:13px; font-weight:700;
                  margin-bottom:16px; }
    .pw-mask { -webkit-text-security:disc; font-family:text-security-disc,monospace; }
    """

def _hash_js():
    """
    JS untuk hash password SHA-256 lalu redirect via window.parent.location.href
    agar Streamlit (yang merender st.html() dalam iframe) bisa menangkap query params.
    """
    return """
    <script>
        window.hashAndSubmit = async function(formId) {
            const form = document.getElementById(formId);
            if (!form) return;

            const btn = form.querySelector('.btn-simpan');
            if (btn) {
                btn.disabled = true;
                btn.textContent = 'Menyimpan...';
            }

            const pwField = form.querySelector('[name=f_pw]');
            if (pwField && pwField.value.trim().length > 0) {
                const raw = pwField.value.trim();
                if (raw.length !== 64 || !/^[0-9a-f]+$/i.test(raw)) {
                    try {
                        const buf = await crypto.subtle.digest('SHA-256',
                            new TextEncoder().encode(raw));
                        const hex = Array.from(new Uint8Array(buf))
                            .map(b => b.toString(16).padStart(2, '0')).join('');
                        pwField.value = hex;
                    } catch(e) {
                        console.warn('Hash error (mungkin bukan HTTPS). Melanjutkan dengan password raw:', e);
                        // Lanjut submit raw password ke Python untuk di-hash
                    }
                }
            }

            /* Kumpulkan semua field lalu redirect di level parent (bukan iframe) */
            const inputs = form.querySelectorAll('input, select, textarea');
            const params = new URLSearchParams();
            inputs.forEach(function(el) {
                if (el.name) params.set(el.name, el.value);
            });

            window.parent.location.href = '/?' + params.toString();
        };

        // Pasang event listener secara global agar tidak terhapus oleh DOMPurify
        // dan mencegah Streamlit SPA membajak link navigasi kustom kita
        if (!window.__globalLinkListenerAdded) {
            document.addEventListener('click', function(e) {
                // Handle form submit
                if (e.target && e.target.classList && e.target.classList.contains('btn-simpan')) {
                    const form = e.target.closest('form');
                    if (form) {
                        e.preventDefault();
                        window.hashAndSubmit(form.id);
                        return;
                    }
                }
                
                // Handle anchor links
                let link = e.target.closest('a');
                if (link && link.getAttribute('target') === '_top' && link.href) {
                    e.preventDefault();
                    window.top.location.href = link.href;
                }
            });
            window.__globalLinkListenerAdded = true;
        }
    </script>
    """

def _opt(val, label, selected):
    sel = "selected" if selected == val else ""
    return f'<option value="{val}" {sel}>{label}</option>'

# ── Page ──────────────────────────────────────────────────────────────────────
def show_akun():
    # ── Restore session dari query params ─────────────────────────────────────
    qp = st.query_params

    # Handle logout
    if qp.get("logout") == "true":
        st.session_state.logged_in = False
        st.session_state.role = None
        st.query_params.clear()
        st.rerun()

    # Restore role dari query param
    role = (
        qp.get("f_role_session")
        or qp.get("role")
        or st.session_state.get("role", "admin")
    )
    if role not in ("admin", "internal"):
        role = "admin"

    st.session_state.logged_in = True
    st.session_state.role = role

    role_label  = "Administrator" if role == "admin" else "Staff FTI"
    active_name = "Admin BAAK FTI" if role == "admin" else "Staff FTI"
    base        = f"/?logged_in=true&role={role}"
    mode        = qp.get("mode", "")
    target_id   = qp.get("user_id", "")

    # ══════════════════════════════════════════════════════════════════════════
    # PROSES SUBMIT: do_tambah
    # ══════════════════════════════════════════════════════════════════════════
    if mode == "do_tambah":
        nama       = qp.get("f_nama", "").strip()
        email      = qp.get("f_email", "").strip()
        pw_raw     = qp.get("f_pw", "").strip()
        role_val   = qp.get("f_role", "internal")
        status_val = qp.get("f_status", "Aktif")

        errors = []
        if not nama:
            errors.append("Nama wajib diisi.")
        if not email:
            errors.append("Email wajib diisi.")
        if not pw_raw:
            errors.append("Password wajib diisi.")

        if errors:
            st.session_state["form_error"] = " ".join(errors)
            st.session_state["form_data"]  = {
                "nama": nama, "email": email,
                "role": role_val, "status": status_val
            }
            st.query_params.clear()
            st.query_params.update({
                "logged_in": "true", "role": role,
                "page": "Akun", "mode": "tambah"
            })
            st.rerun()
            return

        if is_valid_sha256(pw_raw):
            pw_hash = pw_raw
        else:
            pw_hash = hash_password(pw_raw)

        if role_val not in ("admin", "internal"):
            role_val = "internal"

        ok, err = insert_user(nama, email, pw_hash, role_val, status_val)
        if ok:
            st.session_state["akun_msg"] = ("success", "Pengguna berhasil ditambahkan.")
            st.query_params.clear()
            st.query_params.update({
                "logged_in": "true", "role": role, "page": "Akun"
            })
        else:
            st.session_state["form_error"] = err or "Gagal menyimpan pengguna."
            st.session_state["form_data"]  = {
                "nama": nama, "email": email,
                "role": role_val, "status": status_val
            }
            st.query_params.clear()
            st.query_params.update({
                "logged_in": "true", "role": role,
                "page": "Akun", "mode": "tambah"
            })
        st.rerun()
        return

    # ══════════════════════════════════════════════════════════════════════════
    # PROSES SUBMIT: do_edit
    # ══════════════════════════════════════════════════════════════════════════
    if mode == "do_edit" and target_id:
        nama       = qp.get("f_nama", "").strip()
        email      = qp.get("f_email", "").strip()
        pw_raw     = qp.get("f_pw", "").strip()
        role_val   = qp.get("f_role", "internal")
        status_val = qp.get("f_status", "Aktif")

        errors = []
        if not nama:
            errors.append("Nama wajib diisi.")
        if not email:
            errors.append("Email wajib diisi.")

        if errors:
            st.session_state["form_error"] = " ".join(errors)
            st.session_state["form_data"]  = {
                "nama": nama, "email": email,
                "role": role_val, "status": status_val
            }
            st.query_params.clear()
            st.query_params.update({
                "logged_in": "true", "role": role,
                "page": "Akun", "mode": "edit", "user_id": target_id
            })
            st.rerun()
            return

        pw_hash = None
        if pw_raw:
            if is_valid_sha256(pw_raw):
                pw_hash = pw_raw
            else:
                pw_hash = hash_password(pw_raw)

        if role_val not in ("admin", "internal"):
            role_val = "internal"

        ok, err = update_user(
            int(target_id), nama, email, role_val, status_val,
            new_password_hash=pw_hash
        )
        if ok:
            st.session_state["akun_msg"] = ("success", "Pengguna berhasil diperbarui.")
            st.query_params.clear()
            st.query_params.update({
                "logged_in": "true", "role": role, "page": "Akun"
            })
        else:
            st.session_state["form_error"] = err or "Gagal memperbarui pengguna."
            st.session_state["form_data"]  = {
                "nama": nama, "email": email,
                "role": role_val, "status": status_val
            }
            st.query_params.clear()
            st.query_params.update({
                "logged_in": "true", "role": role,
                "page": "Akun", "mode": "edit", "user_id": target_id
            })
        st.rerun()
        return

    # ══════════════════════════════════════════════════════════════════════════
    # MODE: HAPUS
    # ══════════════════════════════════════════════════════════════════════════
    if mode == "hapus" and target_id:
        ok, err = delete_user(int(target_id))
        st.session_state["akun_msg"] = (
            ("success", "Pengguna berhasil dihapus.") if ok
            else ("error", f"Gagal menghapus: {err}")
        )
        st.query_params.clear()
        st.query_params.update({"logged_in": "true", "role": role, "page": "Akun"})
        st.rerun()
        return

    # ══════════════════════════════════════════════════════════════════════════
    # MODE: TAMBAH — tampilkan form
    # ══════════════════════════════════════════════════════════════════════════
    if mode == "tambah":
        err_msg   = st.session_state.pop("form_error", "")
        form_data = st.session_state.pop("form_data", {})
        v_nama    = html.escape(form_data.get("nama", ""))
        v_email   = html.escape(form_data.get("email", ""))
        v_role    = form_data.get("role", "internal")
        v_status  = form_data.get("status", "Aktif")
        batal_url = f"/?logged_in=true&role={role}&page=Akun"
        err_html  = (
            f'<div class="form-error">{html.escape(err_msg)}</div>'
            if err_msg else ""
        )

        st.html(dedent(f"""
        <style>
        {_base_css()}
        {_form_css()}
        </style>
        {_hash_js()}
        <div class="akun-shell">
            {_sidebar_nav(base, active_name, role_label)}
            <main>
                <header class="akun-header">
                    <div><h1>Manajemen Akun</h1><span>FTI UNSAP</span></div>
                </header>
                <section class="akun-content">
                    <div class="form-card">
                        <div class="form-card-title">Tambah Pengguna Baru</div>
                        {err_html}
                        <form id="form_tambah">
                            <input type="hidden" name="logged_in"      value="true">
                            <input type="hidden" name="f_role_session" value="{html.escape(role)}">
                            <input type="hidden" name="page"           value="Akun">
                            <input type="hidden" name="mode"           value="do_tambah">
                            <div class="form-group">
                                <label class="form-label">Nama Lengkap</label>
                                <input class="form-input" type="text" name="f_nama"
                                       value="{v_nama}" required placeholder="Masukkan nama lengkap">
                            </div>
                            <div class="form-group">
                                <label class="form-label">Email</label>
                                <input class="form-input" type="email" name="f_email"
                                       value="{v_email}" required placeholder="contoh@unsap.ac.id">
                            </div>
                            <div class="form-group">
                                <label class="form-label">Password</label>
                                <input class="form-input pw-mask" type="text" name="f_pw"
                                       required placeholder="Minimal 6 karakter"
                                       autocomplete="new-password" minlength="6">
                            </div>
                            <div class="form-group">
                                <label class="form-label">Role</label>
                                <select class="form-select" name="f_role">
                                    {_opt("admin",    "Admin (BAAK FTI)",     v_role)}
                                    {_opt("internal", "Internal (Staff FTI)", v_role)}
                                </select>
                            </div>
                            <div class="form-group">
                                <label class="form-label">Status</label>
                                <select class="form-select" name="f_status">
                                    {_opt("Aktif",     "Aktif",     v_status)}
                                    {_opt("Non-aktif", "Non-aktif", v_status)}
                                </select>
                            </div>
                            <div class="form-row">
                                <button class="btn-simpan" type="button"
                                        data-label="Simpan">Simpan</button>
                                <a class="btn-batal" href="{batal_url}" target="_top">Batal</a>
                            </div>
                        </form>
                    </div>
                </section>
            </main>
        </div>
        """), unsafe_allow_javascript=True)
        return

    # ══════════════════════════════════════════════════════════════════════════
    # MODE: EDIT — tampilkan form edit
    # ══════════════════════════════════════════════════════════════════════════
    if mode == "edit" and target_id:
        user = get_user_by_id(int(target_id))
        if not user:
            st.session_state["akun_msg"] = ("error", "Pengguna tidak ditemukan.")
            st.query_params.clear()
            st.query_params.update({"logged_in": "true", "role": role, "page": "Akun"})
            st.rerun()
            return

        err_msg   = st.session_state.pop("form_error", "")
        form_data = st.session_state.pop("form_data", {})
        v_nama    = html.escape(form_data.get("nama",   user["nama"]))
        v_email   = html.escape(form_data.get("email",  user["email"]))
        v_role    = form_data.get("role",   user["role"])
        v_status  = form_data.get("status", user["status"])
        batal_url = f"/?logged_in=true&role={role}&page=Akun"
        err_html  = (
            f'<div class="form-error">{html.escape(err_msg)}</div>'
            if err_msg else ""
        )

        st.html(dedent(f"""
        <style>
        {_base_css()}
        {_form_css()}
        </style>
        {_hash_js()}
        <div class="akun-shell">
            {_sidebar_nav(base, active_name, role_label)}
            <main>
                <header class="akun-header">
                    <div><h1>Manajemen Akun</h1><span>FTI UNSAP</span></div>
                </header>
                <section class="akun-content">
                    <div class="form-card">
                        <div class="form-card-title">Edit Pengguna</div>
                        {err_html}
                        <form id="form_edit">
                            <input type="hidden" name="logged_in"      value="true">
                            <input type="hidden" name="f_role_session" value="{html.escape(role)}">
                            <input type="hidden" name="page"           value="Akun">
                            <input type="hidden" name="mode"           value="do_edit">
                            <input type="hidden" name="user_id"        value="{html.escape(target_id)}">
                            <div class="form-group">
                                <label class="form-label">Nama Lengkap</label>
                                <input class="form-input" type="text" name="f_nama"
                                       value="{v_nama}" required>
                            </div>
                            <div class="form-group">
                                <label class="form-label">Email</label>
                                <input class="form-input" type="email" name="f_email"
                                       value="{v_email}" required>
                            </div>
                            <div class="form-group">
                                <label class="form-label">Password Baru</label>
                                <input class="form-input pw-mask" type="text" name="f_pw"
                                       placeholder="Kosongkan jika tidak diubah"
                                       autocomplete="new-password">
                                <span class="form-hint">Biarkan kosong jika tidak ingin mengubah password.</span>
                            </div>
                            <div class="form-group">
                                <label class="form-label">Role</label>
                                <select class="form-select" name="f_role">
                                    {_opt("admin",    "Admin (BAAK FTI)",     v_role)}
                                    {_opt("internal", "Internal (Staff FTI)", v_role)}
                                </select>
                            </div>
                            <div class="form-group">
                                <label class="form-label">Status</label>
                                <select class="form-select" name="f_status">
                                    {_opt("Aktif",     "Aktif",     v_status)}
                                    {_opt("Non-aktif", "Non-aktif", v_status)}
                                </select>
                            </div>
                            <div class="form-row">
                                <button class="btn-simpan" type="button"
                                        data-label="Simpan Perubahan">Simpan Perubahan</button>
                                <a class="btn-batal" href="{batal_url}" target="_top">Batal</a>
                            </div>
                        </form>
                    </div>
                </section>
            </main>
        </div>
        """), unsafe_allow_javascript=True)
        return

    # ══════════════════════════════════════════════════════════════════════════
    # MODE: DEFAULT — daftar pengguna
    # ══════════════════════════════════════════════════════════════════════════
    users = load_users()

    flash_html = ""
    if "akun_msg" in st.session_state:
        level, msg = st.session_state.pop("akun_msg")
        color  = "#166534" if level == "success" else "#991b1b"
        bg     = "#dcfce7" if level == "success" else "#fee2e2"
        border = "#86efac" if level == "success" else "#fca5a5"
        flash_html = (
            f'<div style="background:{bg};color:{color};border:1px solid {border};'
            f'padding:12px 18px;border-radius:4px;font-weight:800;font-size:14px;'
            f'margin-bottom:20px;">{html.escape(msg)}</div>'
        )

    rows_html = ""
    if users:
        for u in users:
            role_badge = (
                '<span class="badge-role badge-admin">&#9679; Admin</span>'
                if u["role"] == "admin"
                else '<span class="badge-role badge-internal">&#9679; Internal</span>'
            )
            status_badge = (
                '<span class="badge-status badge-aktif">Aktif</span>'
                if u["status"] == "Aktif"
                else '<span class="badge-status badge-nonaktif">Non-aktif</span>'
            )
            edit_url  = f"{base}&page=Akun&mode=edit&user_id={u['id']}"
            hapus_url = f"{base}&page=Akun&mode=hapus&user_id={u['id']}"
            rows_html += f"""
            <tr>
                <td>{html.escape(u['nama'])}</td>
                <td>{html.escape(u['email'])}</td>
                <td>{role_badge}</td>
                <td>{status_badge}</td>
                <td>{html.escape(u['terakhir_login'])}</td>
                <td>
                    <div class="aksi-wrap">
                        <a class="btn-edit"  href="{edit_url}"  target="_top">&#9998; Edit</a>
                        <a class="btn-hapus" href="{hapus_url}" target="_top">&#128465; Hapus</a>
                    </div>
                </td>
            </tr>"""
    else:
        rows_html = '<tr><td colspan="6"><div class="empty-state">Belum ada pengguna terdaftar.</div></td></tr>'

    tambah_url = f"{base}&page=Akun&mode=tambah"

    st.html(dedent(f"""
    <style>
    {_base_css()}
    .table-card {{ background:white; box-shadow:0 3px 8px rgba(0,0,0,.25); padding:20px 24px 28px; }}
    .table-topbar {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:20px; }}
    .table-title {{ color:#4a9498; font-size:18px; font-weight:800; }}
    .btn-tambah {{ background:#4a9498; color:white; text-decoration:none;
                   padding:9px 20px; border-radius:4px; font-size:14px; font-weight:800;
                   display:inline-flex; align-items:center; gap:8px; }}
    .user-table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    .user-table th {{ color:#6a777c; text-align:left; padding:10px 14px;
                      border-bottom:2px solid #cfd8dc; font-weight:800; font-size:13px; }}
    .user-table td {{ color:#123047; padding:11px 14px; border-bottom:1px solid #e3e8eb; vertical-align:middle; }}
    .user-table tr:last-child td {{ border-bottom:none; }}
    .user-table tr:hover td {{ background:#f5f9f9; }}
    .badge-role {{ display:inline-flex; align-items:center; gap:6px;
                   padding:3px 12px; border-radius:20px; font-size:12px; font-weight:800; }}
    .badge-admin    {{ background:#e0f2f1; color:#00796b; border:1px solid #80cbc4; }}
    .badge-internal {{ background:#fff3e0; color:#e65100; border:1px solid #ffcc80; }}
    .badge-status   {{ display:inline-flex; padding:3px 14px; border-radius:20px; font-size:12px; font-weight:800; }}
    .badge-aktif    {{ background:#dcfce7; color:#166534; border:1px solid #86efac; }}
    .badge-nonaktif {{ background:#fee2e2; color:#991b1b; border:1px solid #fca5a5; }}
    .aksi-wrap {{ display:flex; gap:8px; }}
    .btn-edit  {{ background:#fff8e1; border:1px solid #ffd54f; color:#f57f17;
                  text-decoration:none; padding:5px 12px; border-radius:4px; font-size:12px; font-weight:800; }}
    .btn-hapus {{ background:#fef2f2; border:1px solid #fca5a5; color:#dc2626;
                  text-decoration:none; padding:5px 12px; border-radius:4px; font-size:12px; font-weight:800; }}
    .empty-state {{ text-align:center; padding:52px 0; color:#8a9ba3; font-size:15px; font-weight:700; }}
    </style>
    {_hash_js()}
    <div class="akun-shell">
        {_sidebar_nav(base, active_name, role_label)}
        <main>
            <header class="akun-header">
                <div><h1>Manajemen Akun</h1><span>FTI UNSAP</span></div>
            </header>
            <section class="akun-content">
                {flash_html}
                <div class="table-card">
                    <div class="table-topbar">
                        <div class="table-title">Daftar Pengguna</div>
                        <a class="btn-tambah" href="{tambah_url}" target="_top">&#43; Tambah Pengguna</a>
                    </div>
                    <table class="user-table">
                        <thead>
                            <tr>
                                <th>Nama</th><th>Email</th><th>Role</th>
                                <th>Status</th><th>Terakhir Login</th><th>Aksi</th>
                            </tr>
                        </thead>
                        <tbody>{rows_html}</tbody>
                    </table>
                </div>
            </section>
        </main>
    </div>
    """), unsafe_allow_javascript=True)