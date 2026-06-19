import streamlit as st
import time

st.set_page_config(
    page_title="PMB FTI UNSAP",
    layout="wide",
    initial_sidebar_state="expanded"
)

from pages.landing   import show_landing
from auth            import login_page
from pages.dashboard import show_dashboard
from pages.historis  import show_historis
from pages.prediksi  import show_prediksi
from pages.evaluasi  import show_evaluasi
from pages.laporan import show_visualisasi_laporan
from pages.akun      import show_akun


# ── Hak akses per role ────────────────────────────────────────────────────────
ADMIN_PAGES    = {"Dashboard", "Histori", "Prediksi", "Evaluasi", "Akun", "Laporan"}
INTERNAL_PAGES = {"Dashboard", "Laporan"}

def allowed(page: str, role: str) -> bool:
    if role == "admin":
        return page in ADMIN_PAGES
    if role == "internal":
        return page in INTERNAL_PAGES
    return False


# ── Session default ───────────────────────────────────────────────────────────
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "role" not in st.session_state:
    st.session_state.role = None
if "last_active" not in st.session_state:
    st.session_state.last_active = time.time()


# ── Baca query params ─────────────────────────────────────────────────────────
query_logged_in  = st.query_params.get("logged_in")
query_role       = st.query_params.get("role")          # navigasi normal
f_role_session   = st.query_params.get("f_role_session") # dari submit form akun
page             = st.query_params.get("page", "")
mode             = st.query_params.get("mode", "")

# Tentukan role yang efektif (normal nav atau dari form submit)
effective_role = None
if query_role in ("admin", "internal"):
    effective_role = query_role
elif f_role_session in ("admin", "internal"):
    effective_role = f_role_session

# ── Restore login dari query params ──────────────────────────────────────────
if query_logged_in == "true" and effective_role:
    st.session_state.logged_in = True
    st.session_state.role      = effective_role

# ── Cek Session Timeout (120 Menit) ───────────────────────────────────────────
SESSION_TIMEOUT_SECONDS = 120 * 60  # 120 menit dalam detik

if st.session_state.logged_in:
    current_time = time.time()
    if current_time - st.session_state.last_active > SESSION_TIMEOUT_SECONDS:
        # Sesi habis
        st.session_state.logged_in = False
        st.session_state.role = None
        st.session_state.last_active = current_time
        st.query_params.clear()
        st.query_params["page"] = "Login"
        st.query_params["timeout"] = "true"
        st.rerun()
    else:
        # Perbarui waktu aktivitas terakhir jika masih aktif
        st.session_state.last_active = current_time


# ── Routing ───────────────────────────────────────────────────────────────────

# Belum login
if not st.session_state.logged_in:
    if page == "Login":
        login_page()
    else:
        show_landing()

# Sudah login
else:
    role = st.session_state.role

    # Halaman tidak diizinkan → redirect ke Dashboard
    if page and page not in ("", ) and not allowed(page, role):
        st.query_params["logged_in"] = "true"
        st.query_params["role"]      = role
        st.query_params["page"]      = "Dashboard"
        st.rerun()

    elif page == "Dashboard" or page == "":
        show_dashboard()
    elif page == "Histori":
        show_historis()
    elif page == "Prediksi":
        show_prediksi()
    elif page == "Evaluasi":
        show_evaluasi()
    elif page == "Laporan":
        show_visualisasi_laporan()
    elif page == "Akun":
        show_akun()
    else:
        show_dashboard()