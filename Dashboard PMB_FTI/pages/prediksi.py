from textwrap import dedent
import base64
import html as html_lib
import pickle
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH    = BASE_DIR / "database.db"
MODEL_PATH = BASE_DIR / "model_rfr.pkl"


# ── Database ──────────────────────────────────────────────────────────────────

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_tables():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS riwayat_prediksi (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                tahun          INTEGER,
                prediksi       INTEGER,
                biaya_kuliah   INTEGER,
                akreditasi     INTEGER,
                kuota_beasiswa INTEGER,
                jumlah_prodi   INTEGER,
                top_feature    TEXT,
                top_pct        REAL,
                dibuat_pada    DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)


def load_data_historis():
    try:
        with get_connection() as conn:
            df = pd.read_sql_query(
                """
                SELECT tahun,
                       informatika,
                       sistem_informasi,
                       (informatika + sistem_informasi) AS total,
                       (informatika + sistem_informasi) AS total_mahasiswa,
                       biaya_kuliah,
                       akreditasi,
                       kuota_beasiswa,
                       jumlah_prodi
                FROM data_historis
                ORDER BY tahun
                """,
                conn,
            )
            return df
    except Exception:
        return pd.DataFrame()


def load_riwayat():
    try:
        with get_connection() as conn:
            return pd.read_sql_query(
                "SELECT * FROM riwayat_prediksi ORDER BY dibuat_pada DESC LIMIT 20", conn
            )
    except Exception:
        return pd.DataFrame()


def load_prediksi_terakhir():
    """Ambil 1 prediksi terbaru dari DB untuk restore session state."""
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT tahun, prediksi, top_feature, top_pct FROM riwayat_prediksi ORDER BY dibuat_pada DESC LIMIT 1"
            ).fetchone()
        return row
    except Exception:
        return None


def simpan_riwayat(tahun, prediksi, biaya, akreditasi, beasiswa, prodi, top_feat, top_pct):
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO riwayat_prediksi "
                "(tahun,prediksi,biaya_kuliah,akreditasi,kuota_beasiswa,jumlah_prodi,top_feature,top_pct) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (tahun, prediksi, biaya, akreditasi, beasiswa, prodi, top_feat, top_pct)
            )
    except Exception:
        pass


def hapus_riwayat(riwayat_id):
    try:
        with get_connection() as conn:
            conn.execute("DELETE FROM riwayat_prediksi WHERE id = ?", (int(riwayat_id),))
    except Exception:
        pass


# ── Model ─────────────────────────────────────────────────────────────────────

@st.cache_resource
def load_model():
    if not MODEL_PATH.exists():
        return None
    with MODEL_PATH.open("rb") as f:
        return pickle.load(f)


FEATURE_LABELS   = ["Biaya Kuliah", "Akreditasi", "Kuota Beasiswa", "Jumlah Prodi"]
AKREDITASI_LABEL = {1: "1 - Kurang", 2: "2 - Baik", 3: "3 - Baik Sekali", 4: "4 - Unggul"}


def run_prediction(biaya, akreditasi, beasiswa, prodi):
    model = load_model()
    X = [[biaya, akreditasi, beasiswa, prodi]]
    if model is None:
        return 190, [("Akreditasi", 41.2), ("Kuota Beasiswa", 29.4), ("Biaya Kuliah", 17.6), ("Jumlah Prodi", 11.8)]
    pred = int(max(0, round(model.predict(X)[0])))
    if hasattr(model, "feature_importances_"):
        imps = [(lbl, round(v * 100, 1)) for lbl, v in zip(FEATURE_LABELS, model.feature_importances_)]
        imps.sort(key=lambda x: x[1], reverse=True)
    else:
        imps = [("Akreditasi", 41.2), ("Kuota Beasiswa", 29.4), ("Biaya Kuliah", 17.6), ("Jumlah Prodi", 11.8)]
    return pred, imps


def rebuild_importances_from_db(top_feature, top_pct):
    model = load_model()
    if model and hasattr(model, "feature_importances_"):
        imps = [(lbl, round(v * 100, 1)) for lbl, v in zip(FEATURE_LABELS, model.feature_importances_)]
        imps.sort(key=lambda x: x[1], reverse=True)
        return imps
    others = [l for l in FEATURE_LABELS if l != top_feature]
    remaining = max(0, 100 - top_pct)
    imps = [(top_feature, top_pct)]
    for l in others:
        imps.append((l, round(remaining / len(others), 1)))
    return imps


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_number(v):
    try:
        return f"{int(v):,}".replace(",", ".")
    except Exception:
        return str(v)


def make_icon(name):
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
    image_base64 = base64.b64encode(path.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{image_base64}" alt="{name}">'


# ── Main ──────────────────────────────────────────────────────────────────────

def show_prediksi():
    init_tables()

    role        = st.session_state.get("role", "admin")
    role_label  = "Administrator" if role == "admin" else "Staff FTI"
    active_name = "Admin BAAK FTI" if role == "admin" else "Staff FTI"
    base        = f"/?logged_in=true&role={role}"

    # ── Handle hapus riwayat ──────────────────────────────────────────────
    hapus_id = st.query_params.get("hapus_riwayat", "")
    if hapus_id:
        hapus_riwayat(hapus_id)
        sisa = load_prediksi_terakhir()
        if sisa is None:
            st.session_state.pred_result = None
            st.session_state.pred_tahun  = None
            st.session_state.pred_error  = None
        st.query_params.clear()
        st.query_params.update({"logged_in": "true", "role": role, "page": "Prediksi"})
        st.rerun()

    df_hist = load_data_historis()
    df_riw  = load_riwayat()

    tahun_tersedia  = sorted({int(t) for t in df_hist["tahun"].dropna().tolist()}) if not df_hist.empty else []
    tahun_max       = int(max(tahun_tersedia)) if tahun_tersedia else None
    tahun_default   = (tahun_max + 1) if tahun_max is not None else 2026
    tahun_min       = max(1, int(min(tahun_tersedia)) + 1) if tahun_tersedia else 1
    tahun_max_input = max(tahun_default + 10, 2035)

    # ── Init session state ────────────────────────────────────────────────
    for k, v in [("pred_result", None), ("pred_tahun", None), ("pred_error", None)]:
        if k not in st.session_state:
            st.session_state[k] = v

    # ── RESTORE dari DB jika session kosong ───────────────────────────────
    if st.session_state.pred_result is None and st.session_state.pred_error is None:
        last = load_prediksi_terakhir()
        if last is not None:
            tahun_db, prediksi_db, top_feat_db, top_pct_db = last
            imps = rebuild_importances_from_db(top_feat_db, top_pct_db)
            st.session_state.pred_result = (int(prediksi_db), imps)
            st.session_state.pred_tahun  = int(tahun_db)
            st.session_state.pred_error  = None

    has_result = st.session_state.pred_result is not None and not st.session_state.pred_error

    # ── CSS ───────────────────────────────────────────────────────────────
    st.markdown("""
    <style>
    [data-testid="stHeader"],
    [data-testid="stSidebar"] { display: none !important; }

    html, body, .stApp, [data-testid="stAppViewContainer"] {
        margin: 0 !important; padding: 0 !important; background: #e3e7eb !important;
    }
   [data-testid="stMain"] {
        position: fixed !important; inset: 0 !important;
        margin: 0 !important; padding: 0 !important;
        background: #e3e7eb !important;
        overflow-y: auto !important; overflow-x: hidden !important;
    }
    .block-container {
        max-width: 100% !important;
        min-height: 100vh !important;
        padding: 104px 52px 140px 332px !important;
        margin: 0 !important;
        font-family: Arial, sans-serif !important;
        box-sizing: border-box !important;
        overflow: visible !important;
        position: static !important;
    }

    section[data-testid="stMain"] > div.block-container {
        padding: 104px 52px 140px 332px !important;
        margin: 0 !important;
        max-width: 100% !important;
        min-height: 100vh !important;
        position: static !important;
        box-sizing: border-box !important;
    }

    .element-container:has(.p-sidebar),
    div:has(> .p-sidebar) {
        display: contents !important;
        position: static !important;
    }

    /* ── Sidebar: fixed, tidak menggeser konten ── */
    .p-sidebar {
        width: 280px;
        background: #4a9498;
        color: white;
        padding: 36px 22px 28px;
        display: flex;
        flex-direction: column;
        position: absolute;
        top: 0;
        left: 0;
        height: auto;
        min-height: 180vh;
        overflow: visible;
        z-index: 9999;
        box-sizing: border-box;
        font-family: Arial, sans-serif;
    }
    .p-brand-title { font-size:21px; font-weight:800; line-height:1.2; color:white; }
    .p-brand-sub {
        font-size:13px; font-weight:700; margin-top:6px; color:white;
        padding-bottom:18px; border-bottom:1px solid rgba(255,255,255,0.25);
    }
    .p-nav { margin-top:24px; display:flex; flex-direction:column; gap:16px; }
    .p-nav-item {
        color: white !important; text-decoration: none !important;
        display: flex; align-items: center; gap: 13px;
        padding: 11px 10px; border-radius: 4px;
        font-size: 16px; font-weight: 500;
        white-space: normal !important; line-height: 1.35;
    }
    .p-nav-item:hover { background: rgba(255,255,255,0.12); }
    .p-nav-item.active {
        background: #e9c91d !important; color: white !important;
        font-weight: 700; width: calc(100% + 25px);
        min-height: 60px; margin-left: -13px;
        padding-left: 20px; padding-right: 14px;
        box-sizing: border-box;
    }
    .p-nav-icon {
        width: 24px; height: 24px; flex: 0 0 24px;
        display: inline-flex; align-items: center; justify-content: center;
    }
    .p-nav-icon img { width:23px !important; height:23px !important; object-fit:contain; }

    /* user info di bawah sidebar */
    .p-sidebar-user {
        margin-top: auto;
        padding: 16px 8px 0;
        border-top: 1px solid rgba(255,255,255,0.25);
        color: rgba(255,255,255,0.6);
        font-size: 16px;
        line-height: 1.35;
    }
    .p-logout {
        margin-top: 220px;
        color: white !important; text-decoration: none !important;
        display: flex; align-items: center; gap: 12px; font-size: 16px;
    }

    /* ── Header ── */
    .p-header {
        height: 84px;
        background: white;
        display: flex;
        align-items: center;
        padding: 0 28px;
        box-shadow: 0 2px 6px rgba(0,0,0,.25);
        box-sizing: border-box;
        width: calc(100vw - 280px);
        position: absolute;
        top: 0;
        left: 280px;
        z-index: 9998;
    }
    .element-container:has(.p-header) {
        margin-top: 0 !important;
        margin-bottom: 0 !important;
    }
    .p-header-title {
        margin: 0 !important; color: #4A8E93 !important;
        font-size: 32px !important; font-weight: 800 !important; line-height: 1.05 !important;
        margin-top: -25px !important;
    }
    .p-header-sub { display:block; color:#4A8E93 !important; font-size:17px; font-weight:800; margin-top:-13px; }

    /* ── Form ── */
    div[data-testid="stForm"] {
        background: white !important; border: 0 !important;
        border-radius: 0 !important;
        box-shadow: 0 3px 8px rgba(0,0,0,0.25) !important;
        padding: 20px 22px 24px !important;
    }
    div[data-testid="stForm"] h3 {
        color: #4a9498 !important; font-size: 17px !important;
        font-weight: 800 !important; margin-bottom: 10px !important;
        padding-bottom: 10px !important; border-bottom: 1px solid #e0e7ea !important;
    }
    div[data-testid="stNumberInput"] label,
    div[data-testid="stSelectbox"] label {
        font-size: 13px !important; font-weight: 700 !important; color: #123047 !important;
    }
    div[data-testid="stNumberInput"] input,
    div[data-testid="stSelectbox"] [data-baseweb="select"] > div {
        min-height: 32px !important; border: 1px solid #d0dde0 !important;
        border-radius: 4px !important; background: #f3f5f7 !important;
        box-shadow: inset 0 2px 4px rgba(0,0,0,0.14) !important; font-size: 14px !important;
    }
    div[data-testid="stFormSubmitButton"] button {
        background: #4a9498 !important; color: white !important;
        border: none !important; font-weight: 700 !important;
        font-size: 14px !important; border-radius: 4px !important;
        padding: 10px 32px !important; margin-top: 10px !important; width: 100% !important;
    }

    /* ── Info / warning boxes ── */
    .p-info {
        background: #f0f8f8; border-left: 4px solid #4a9498;
        padding: 10px 14px; color: #123047; font-size: 13px; margin-bottom: 14px;
    }
    .p-warning {
        background: #fff3cd; border-left: 4px solid #ffc107;
        padding: 10px 14px; color: #7a5200; font-size: 13px;
        font-weight: 700; margin-bottom: 14px;
    }
    .p-error-panel {
        background: #fff0f0; border: 1px solid #ffcccc;
        box-shadow: 0 3px 8px rgba(0,0,0,0.15);
        padding: 20px; color: #c00; font-size: 14px; font-weight: 700;
    }

    /* ── Hasil prediksi ── */
    .p-result-card {
        background: #4a9498; color: white;
        box-shadow: 0 3px 8px rgba(0,0,0,0.25);
        padding: 32px 36px 34px; min-height: 420px; box-sizing: border-box;
    }
    .p-result-title { font-size:14px; font-weight:700; opacity:.9; margin-bottom:12px; }
    .p-result-year  { font-size:15px; font-weight:700; opacity:.88; }
    .p-result-number { font-size:76px; font-weight:900; line-height:1; margin-top:8px; }
    .p-result-unit  { font-size:22px; font-weight:700; opacity:.9; margin-bottom:32px; }
    .p-fi-title { font-size:12px; font-weight:800; margin-bottom:14px; text-transform:uppercase; opacity:.86; }
    .p-fi-row {
        display:grid; grid-template-columns:120px 1fr 48px;
        align-items:center; gap:10px; margin-bottom:11px;
        font-size:12px; font-weight:700;
    }
    .p-fi-track { height:18px; border-left:1px solid rgba(255,255,255,.28); }
    .p-fi-bar { height:18px; background:white; border-radius:4px; }
    .p-fi-bar.accent { background:#e9f4ff; outline:2px solid #30a7ff; }
    .p-result-legend {
        display:grid; grid-template-columns:repeat(4,1fr); gap:8px;
        margin-top:20px; padding-top:14px;
        border-top:1px solid rgba(255,255,255,.25);
        text-align:center; font-size:11px;
    }
    .p-result-legend strong { display:block; font-size:13px; margin-bottom:3px; }

    /* ── Riwayat ── */
    .p-riwayat-card {
        background: white; box-shadow: 0 3px 8px rgba(0,0,0,0.25);
        padding: 20px 22px 24px; margin-top: 24px;
    }
    .p-riwayat-title {
        color:#4a9498; font-size:17px; font-weight:800;
        margin-bottom:14px; padding-bottom:10px; border-bottom:1px solid #e0e7ea;
    }
    .p-rtable { width:100%; border-collapse:collapse; font-size:14px; }
    .p-rtable th {
        padding:10px 12px; text-align:left; color:#6a777c;
        font-weight:700; border-bottom:1px solid #d3dadd;
    }
    .p-rtable td { padding:10px 12px; border-bottom:1px solid #edf0f2; color:#123047; }
    .p-rtable tr:last-child td { border-bottom:none; }
    .p-rtable tr:hover td { background:#f0f7f8; }
    .p-delete-btn {
        background: #ff4444; color: white !important;
        text-decoration: none !important; display: inline-flex;
        align-items: center; justify-content: center;
        padding: 6px 12px; border-radius: 4px; font-size: 13px; font-weight: 800;
    }

    @media (max-width: 768px) {
        section[data-testid="stMain"] > div.block-container { padding: 120px 20px 40px 20px !important; }
        .p-sidebar { width: 100%; position: relative; min-height: auto; padding: 20px; }
        .p-header { left: 0; width: 100%; padding: 0 20px; }
        .p-logout { margin-top: 40px; }
        .p-result-card { padding: 20px; min-height: auto; }
        .p-result-legend { grid-template-columns: 1fr 1fr; }
        .p-rtable { display: block; overflow-x: auto; white-space: nowrap; }
    }
    </style>
    """, unsafe_allow_html=True)

    # ── Sidebar + Header ──────────────────────────────────────────────────
    st.markdown(dedent(f"""
    <div class="p-sidebar">
        <div class="p-brand-title">Prediksi Mahasiswa</div>
        <div class="p-brand-sub">Fakultas Teknologi Informasi</div>
        <nav class="p-nav">
            <a class="p-nav-item" href="{base}&page=Dashboard" target="_self">
                <span class="p-nav-icon">{make_icon("dashboard")}</span>Dashboard Utama</a>
            <a class="p-nav-item" href="{base}&page=Histori" target="_self">
                <span class="p-nav-icon">{make_icon("database")}</span>Data Historis</a>
            <a class="p-nav-item active" href="{base}&page=Prediksi" target="_self">
                <span class="p-nav-icon">{make_icon("chart")}</span>Prediksi Mahasiswa Baru</a>
            <a class="p-nav-item" href="{base}&page=Evaluasi" target="_self">
                <span class="p-nav-icon">{make_icon("list")}</span>Evaluasi Model</a>
            <a class="p-nav-item" href="{base}&page=Akun" target="_self">
                <span class="p-nav-icon">{make_icon("account")}</span>Manajemen Akun</a>
            <a class="p-nav-item" href="{base}&page=Laporan" target="_self">
                <span class="p-nav-icon">{make_icon("report")}</span>Visualisasi dan Laporan</a>
        </nav>
        <div class="p-sidebar-user">
            {html_lib.escape(active_name)}<br>{html_lib.escape(role_label)}
        </div>
        <a class="p-logout" href="/?logout=true" target="_self">
            <span class="p-nav-icon">{make_icon("logout")}</span>Log out</a>
    </div>
    <header class="p-header">
        <div>
            <h1 class="p-header-title">Prediksi Mahasiswa Baru</h1>
            <span class="p-header-sub">FTI UNSAP</span>
        </div>
    </header>
    """), unsafe_allow_html=True)

    # ── Layout kolom ──────────────────────────────────────────────────────
    if has_result or st.session_state.pred_error:
        left_col, right_col, _ = st.columns([5, 4.2, 2], gap="large")
    else:
        left_col, _ = st.columns([5, 7], gap="large")
        right_col = None

    # ── Form input ────────────────────────────────────────────────────────
    with left_col:
        if df_hist.empty:
            with st.form("form_prediksi"):
                st.markdown("### Input Parameter Prediksi")
                st.markdown('<div class="p-warning">Belum ada data historis. Tambahkan data historis terlebih dahulu.</div>', unsafe_allow_html=True)
                st.form_submit_button("Jalankan Prediksi", disabled=True)
        else:
            last_row         = df_hist.iloc[-1]
            default_biaya    = int(last_row["biaya_kuliah"])
            default_ak       = int(last_row["akreditasi"])
            default_beasiswa = int(last_row["kuota_beasiswa"])
            default_prodi    = int(last_row["jumlah_prodi"])
            ak_options       = [1, 2, 3, 4]

            with st.form("form_prediksi"):
                st.markdown("### Input Parameter Prediksi")
                st.markdown(
                    f'<div class="p-info">Prediksi tahun berikutnya hanya bisa dijalankan jika data historis '
                    f'tahun sebelumnya tersedia. Data historis terakhir: tahun <strong>{tahun_max}</strong>.</div>',
                    unsafe_allow_html=True,
                )
                tahun_input = st.number_input(
                    "Tahun Prediksi", min_value=tahun_min, max_value=tahun_max_input,
                    value=tahun_default, step=1,
                    help="Prediksi tahun N membutuhkan data historis tahun N-1",
                )
                biaya      = st.number_input("Biaya Kuliah (Rp)", min_value=0, value=default_biaya, step=50_000)
                akreditasi = st.selectbox(
                    "Akreditasi", options=ak_options,
                    index=ak_options.index(default_ak) if default_ak in ak_options else 1,
                    format_func=lambda x: AKREDITASI_LABEL[x],
                )
                beasiswa = st.number_input("Kuota Beasiswa", min_value=0, value=default_beasiswa, step=1)
                prodi    = st.number_input("Jumlah Program Studi", min_value=1, value=max(1, default_prodi), step=1)
                submitted = st.form_submit_button("Jalankan Prediksi")

            if submitted:
                tahun_prediksi   = int(tahun_input)
                tahun_dibutuhkan = tahun_prediksi - 1
                if tahun_dibutuhkan not in tahun_tersedia:
                    st.session_state.pred_result = None
                    st.session_state.pred_tahun  = tahun_prediksi
                    st.session_state.pred_error  = (
                        f"Prediksi tahun {tahun_prediksi} tidak dapat dijalankan karena "
                        f"data historis tahun {tahun_dibutuhkan} belum tersedia."
                    )
                    st.rerun()

                hasil, importances = run_prediction(biaya, akreditasi, beasiswa, prodi)
                st.session_state.pred_result = (hasil, importances)
                st.session_state.pred_tahun  = tahun_prediksi
                st.session_state.pred_error  = None

                top_feat, top_pct = importances[0]
                simpan_riwayat(tahun_prediksi, hasil, biaya, akreditasi, beasiswa, prodi, top_feat, top_pct)
                st.rerun()

    # ── Panel hasil ───────────────────────────────────────────────────────
    if right_col is not None:
        with right_col:
            if st.session_state.pred_error:
                st.html(f'<div class="p-error-panel">&#9888; {html_lib.escape(st.session_state.pred_error)}</div>')
            elif has_result:
                hasil, importances = st.session_state.pred_result
                tahun_pred = st.session_state.pred_tahun
                max_pct = max([pct for _, pct in importances] or [1])

                fi_rows = ""
                for i, (label, pct) in enumerate(importances):
                    width  = max(6, (pct / max_pct) * 100)
                    accent = " accent" if i == 0 else ""
                    fi_rows += f"""
                    <div class="p-fi-row">
                        <span>{html_lib.escape(label)}</span>
                        <div class="p-fi-track">
                            <div class="p-fi-bar{accent}" style="width:{width:.1f}%;"></div>
                        </div>
                        <span>{pct:.1f}%</span>
                    </div>"""

                legend = "".join(
                    f'<div><strong>{pct:.1f}%</strong>{html_lib.escape(label)}</div>'
                    for label, pct in importances
                )

                st.html(f"""
                <div class="p-result-card">
                    <div class="p-result-title">Hasil Prediksi</div>
                    <div class="p-result-year">Tahun {tahun_pred}</div>
                    <div class="p-result-number">{fmt_number(hasil)}</div>
                    <div class="p-result-unit">Mahasiswa</div>
                    <div class="p-fi-title">Feature Importance</div>
                    {fi_rows}
                    <div class="p-result-legend">{legend}</div>
                </div>""")

    # ── Riwayat prediksi ──────────────────────────────────────────────────
    df_riw = load_riwayat()
    if df_riw.empty:
        riwayat_rows = '<tr><td colspan="4" style="text-align:center;color:#aaa;padding:20px;">Belum ada riwayat prediksi</td></tr>'
    else:
        riwayat_rows = ""
        for _, r in df_riw.iterrows():
            riwayat_rows += f"""
            <tr>
                <td>{int(r['tahun'])}</td>
                <td>{fmt_number(r['prediksi'])}</td>
                <td>{html_lib.escape(str(r['top_feature']))} ({float(r['top_pct']):.1f}%)</td>
                <td><a class="p-delete-btn"
                       href="{base}&page=Prediksi&hapus_riwayat={int(r['id'])}"
                       target="_self">Hapus</a></td>
            </tr>"""

    st.markdown(f"""
    <div class="p-riwayat-card">
        <div class="p-riwayat-title">Riwayat Prediksi</div>
        <table class="p-rtable">
            <thead>
                <tr>
                    <th>Tahun</th><th>Prediksi</th><th>Top Feature</th><th>Aksi</th>
                </tr>
            </thead>
            <tbody>{riwayat_rows}</tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)