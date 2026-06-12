import base64
import html as html_lib
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "database.db"


# ── Database ──────────────────────────────────────────────────────────────────

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS data_historis (
                tahun            INTEGER PRIMARY KEY,
                informatika      INTEGER DEFAULT 0,
                sistem_informasi INTEGER DEFAULT 0,
                biaya_kuliah     INTEGER DEFAULT 0,
                akreditasi       INTEGER DEFAULT 2,
                kuota_beasiswa   INTEGER DEFAULT 0,
                jumlah_prodi     INTEGER DEFAULT 2
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mahasiswa (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                tahun INTEGER,
                nama  TEXT,
                nim   TEXT,
                prodi TEXT
            )
        """)


def load_data_historis():
    with get_connection() as conn:
        df = pd.read_sql_query(
            """
            SELECT tahun, informatika, sistem_informasi,
                   (informatika + sistem_informasi) AS total,
                   biaya_kuliah, akreditasi, kuota_beasiswa, jumlah_prodi
            FROM data_historis ORDER BY tahun
            """,
            conn,
        )
    return df


def upsert_row(tahun, informatika, sistem_informasi, biaya_kuliah, akreditasi, kuota_beasiswa, jumlah_prodi):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO data_historis
                (tahun, informatika, sistem_informasi, biaya_kuliah, akreditasi, kuota_beasiswa, jumlah_prodi)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tahun) DO UPDATE SET
                informatika      = excluded.informatika,
                sistem_informasi = excluded.sistem_informasi,
                biaya_kuliah     = excluded.biaya_kuliah,
                akreditasi       = excluded.akreditasi,
                kuota_beasiswa   = excluded.kuota_beasiswa,
                jumlah_prodi     = excluded.jumlah_prodi
            """,
            (tahun, informatika, sistem_informasi, biaya_kuliah, akreditasi, kuota_beasiswa, jumlah_prodi),
        )


def delete_row(tahun):
    with get_connection() as conn:
        conn.execute("DELETE FROM data_historis WHERE tahun = ?", (tahun,))


def get_row(tahun):
    with get_connection() as conn:
        return conn.execute(
            "SELECT tahun, informatika, sistem_informasi, biaya_kuliah, akreditasi, kuota_beasiswa, jumlah_prodi FROM data_historis WHERE tahun = ?",
            (tahun,),
        ).fetchone()


# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_int(v):
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return 0
        return int(v)
    except:
        return 0

def fmt_currency(v):
    return f"Rp {safe_int(v):,}".replace(",", ".")

def fmt_number(v):
    return f"{safe_int(v):,}".replace(",", ".")

def akreditasi_badge(level):
    colors = {
        1: ("#ff4444", "1-Kurang"),
        2: ("#ff7a00", "2-Baik"),
        3: ("#22c55e", "3-Baik Sekali"),
        4: ("#0000FF", "4-Unggul"),
    }
    color, label = colors.get(level, ("#aaa", str(level)))
    return (
        f'<span style="background:{color};color:white;padding:2px 10px;'
        f'border-radius:4px;font-size:12px;font-weight:700;">{label}</span>'
    )

def compute_stats(df):
    if df.empty:
        return []
    rows = []
    numeric_cols = {
        "Biaya Kuliah (X1)":   ("biaya_kuliah",  fmt_currency),
        "Akreditasi (X2)":     ("akreditasi",    lambda v: str(round(float(v), 2)) if pd.notna(v) else "0"),
        "Kuota Beasiswa (X3)": ("kuota_beasiswa", fmt_number),
        "Jumlah Prodi (X4)":   ("jumlah_prodi",  fmt_number),
        "Mahasiswa (Y)":       ("total",         fmt_number),
    }
    notes = {
        "biaya_kuliah":   lambda s: f"Naik signifikan {int(df.loc[s.idxmin(), 'tahun'])}" if s.max() > s.min() else "Stabil",
        "akreditasi":     lambda s: f"Naik ke {int(s.max())} pada {int(df.loc[s.idxmax(), 'tahun'])}" if s.max() > s.min() else "Stabil",
        "kuota_beasiswa": lambda s: f"Turun drastis di {int(df.loc[s.idxmin(), 'tahun'])}" if s.min() < s.mean() * 0.7 else "Stabil",
        "jumlah_prodi":   lambda s: f"Tidak terdapat perubahan selama tahun {int(df['tahun'].min())}-{int(df['tahun'].max())}" if s.nunique() == 1 else "Berubah",
        "total":          lambda s: f"Tren menurun {int(df.loc[s.idxmin(), 'tahun'])}" if s.iloc[-1] < s.iloc[0] else f"Tren naik {int(df.loc[s.idxmax(), 'tahun'])}",
    }
    for label, (col, fmtfn) in numeric_cols.items():
        s = df[col].fillna(0)
        try:
            std_val = fmt_number(s.std()) if col == "biaya_kuliah" else str(round(s.std(), 1))
        except:
            std_val = "0"
        try:
            catatan = notes[col](s)
        except:
            catatan = "-"
        rows.append({
            "variabel": label,
            "min":      fmtfn(s.min()),
            "maks":     fmtfn(s.max()),
            "rata":     fmtfn(s.mean()),
            "std":      std_val,
            "catatan":  catatan,
        })
    return rows

def process_csv_upload(uploaded_file):
    try:
        df = pd.read_csv(
            uploaded_file,
            on_bad_lines="skip",
            sep=None,
            engine="python"
        )

        # bersihkan nama kolom
        df.columns = (
            df.columns
            .astype(str)
            .str.strip()
            .str.lower()
        )

        # hapus baris kosong
        df = df.dropna(how="all")


        # ===== HITUNG BERDASARKAN KOLOM NOMOR =====
        first_col = df.columns[0]

        nomor = pd.to_numeric(
            df[first_col],
            errors="coerce"
        )

        # ambil nomor valid saja
        nomor = nomor.dropna()

        # jumlah berdasarkan nomor terbesar
        if len(nomor) > 0:
            count = int(nomor.max())
            return count, None


        # fallback kalau tidak ada nomor
        for col in df.columns:

            if "nim" in col:

                nim = (
                    df[col]
                    .astype(str)
                    .str.strip()
                )

                nim = nim[
                    (nim != "") &
                    (nim.str.lower() != "nan")
                ]

                return int(
                    nim.drop_duplicates().count()
                ), None


        return int(len(df)), None


    except Exception as e:
        return 0, str(e)

def icon_b64(name):
    icon_paths = {
        "dashboard": "assets/dashboard_utama.png",
        "database":  "assets/datahistoris_sidebar.png",
        "chart":     "assets/prediksi_sidebar.png",
        "list":      "assets/evaluasi_sidebar.png",
        "account":   "assets/akun_sidebar.png",
        "report":    "assets/dokumen_sidebar.png",
        "logout":    "assets/logout.png",
    }
    path = Path(icon_paths.get(name, ""))
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode()

def make_icon(name):
    b = icon_b64(name)
    if b:
        return f'<span class="side-icon"><img src="data:image/png;base64,{b}" alt="{name}"></span>'
    return ""


# ── Main ──────────────────────────────────────────────────────────────────────

def show_historis():
    init_db()

    role        = st.session_state.get("role", "admin")
    role_label  = "Administrator" if role == "admin" else "Staff FTI"
    active_name = "Admin BAAK FTI" if role == "admin" else "Staff FTI"
    base        = f"/?logged_in=true&role={role}"

    mode       = st.query_params.get("mode", "")
    edit_tahun = st.query_params.get("edit_tahun", "")

    if "dh_mode" not in st.session_state:
        st.session_state.dh_mode = None
    if "dh_edit_tahun" not in st.session_state:
        st.session_state.dh_edit_tahun = None

    if mode in ("upload", "tambah", "edit", "hapus"):
        st.session_state.dh_mode = mode
        if edit_tahun:
            st.session_state.dh_edit_tahun = int(edit_tahun)

    current_mode = st.session_state.get("dh_mode")

    def back():
        st.session_state.dh_mode = None
        st.session_state.dh_edit_tahun = None
        st.query_params.clear()
        st.query_params.update({"logged_in": "true", "role": role, "page": "Histori"})
        st.rerun()

    # ── Global CSS ─────────────────────────────────────────────────────────
    st.markdown("""
    <style>
    [data-testid="stHeader"] { display: none !important; }
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="stAppViewContainer"] { background: #e3e7eb !important; }
    [data-testid="stMain"] {
        position: fixed !important;
        inset: 0 !important;
        background: #e3e7eb !important;
        padding: 0 !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
    }
    .block-container {
        padding: 0 0 0 280px !important;
        margin: 0 !important;
        max-width: 100% !important;
        min-height: 100vh !important;
        position: static !important;
        box-sizing: border-box !important;
    }
    .element-container:has(.dh-sidebar),
    div:has(> .dh-sidebar) {
        display: contents !important;
        position: static !important;
    }

    /* Layout utama */
    .dh-outer {
        display: flex;
        min-height: 100vh;
        font-family: Arial, sans-serif;
    }
    .dh-sidebar {
        width: 280px;
        min-width: 280px;
        background: #4a9498;
        color: white;
        padding: 36px 22px 28px;
        display: flex;
        flex-direction: column;
        min-height: 180vh;
        position: absolute;
        top: 0;
        left: 0;
        height: auto;
        overflow: visible;
        z-index: 100;
        box-sizing: border-box;
        font-family: Arial, sans-serif;
    }
    .dh-main {
        margin-left: 280px;
        flex: 1;
        display: flex;
        flex-direction: column;
        min-height: 100vh;
    }
    .dh-header {
        height: 84px;
        background: white;
        display: flex;
        align-items: center;
        padding: 0 28px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.25);
        position: sticky;
        top: 0;
        z-index: 10;
    }
    .dh-header h1 {
        margin: 0;
        color: #4a9498;
        font-size: 28px;
        line-height: 1.05;
        font-weight: 800;
    }
    .dh-header h1 span {
        display: block;
        font-size: 17px;
        margin-top: 5px;
        font-weight: 800;
    }
    .dh-content { padding: 28px 40px 52px; }

    /* Sidebar items */
    .brand-title { font-size: 21px; font-weight: 800; line-height: 1.2; }
    .brand-subtitle {
        font-size: 13px; font-weight: 700; margin-top: 6px;
        padding-bottom: 18px; border-bottom: 1px solid rgba(255,255,255,0.25);
    }
    .side-menu { margin-top: 24px; display: grid; gap: 16px; }
    .side-item {
        color: white !important; text-decoration: none !important;
        display: flex; align-items: center; gap: 13px;
        padding: 11px 10px; border-radius: 4px; font-size: 16px;
    }
    .side-item:hover { background: rgba(255,255,255,0.1); }
    .side-item.active { background: #e9c91d !important; }
    .side-icon {
        width: 24px;
        height: 24px;
        flex: 0 0 24px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
    }
    .side-icon img {
        width: 23px;
        height: 23px;
        object-fit: contain;
    }
    .sidebar-user {
        margin-top: auto; padding: 16px 8px 0;
        border-top: 1px solid rgba(255,255,255,0.25);
        color: rgba(255,255,255,0.6); line-height: 1.35; font-size: 16px;
    }
    .logout-link {
        margin-top: 220px; color: white !important; text-decoration: none !important;
        display: flex; align-items: center; gap: 12px; font-size: 16px;
    }

    /* Table card */
    .table-card {
        background: white; box-shadow: 0 3px 8px rgba(0,0,0,0.25);
        padding: 20px 22px 24px; margin-bottom: 24px;
    }
    .table-card-header {
        display: flex; justify-content: space-between;
        align-items: center; margin-bottom: 16px;
    }
    .table-card-title { color: #4a9498; font-size: 18px; font-weight: 800; }
    .table-card-actions { display: flex; gap: 10px; }
    .btn-upload {
        background: #4a9498; color: white !important; text-decoration: none !important;
        padding: 8px 18px; border-radius: 4px; font-size: 14px;
        font-weight: 700; display: inline-flex; align-items: center; gap: 6px;
    }
    .btn-tambah {
        background: #e9c91d; color: white !important; text-decoration: none !important;
        padding: 8px 18px; border-radius: 4px; font-size: 14px;
        font-weight: 700; display: inline-flex; align-items: center;
    }
    .data-table { width: 100%; border-collapse: collapse; font-size: 14px; }
    .data-table th {
        background: #4a9498; color: white; padding: 10px 12px;
        text-align: left; font-weight: 700; font-size: 13px;
    }
    .data-table td {
        padding: 9px 12px; border-bottom: 1px solid #e0e7ea; color: #123047;
    }
    .data-table tr:last-child td { border-bottom: none; }
    .data-table tr:hover td { background: #f0f7f8; }

    /* Stats card */
    .stats-card {
        background: white; box-shadow: 0 3px 8px rgba(0,0,0,0.25);
        padding: 20px 22px 24px; border: 2px solid #4a9498;
    }
    .stats-card-title { color: #4a9498; font-size: 17px; font-weight: 800; margin-bottom: 14px; }
    .stats-table { width: 100%; border-collapse: collapse; font-size: 14px; }
    .stats-table th {
        border-bottom: 2px solid #e0e7ea; padding: 8px 12px;
        text-align: left; color: #4a9498; font-weight: 700;
    }
    .stats-table td {
        padding: 10px 12px; border-bottom: 1px solid #e0e7ea; color: #123047;
    }
    .stats-table tr:last-child td { border-bottom: none; }

    /* Form */
    .form-header {
        color: #4a9498; font-size: 22px; font-weight: 800;
        margin: 0 0 20px 0; font-family: Arial, sans-serif;
    }
    
    /* PAKSA HALAMAN NEMPEL ATAS SEPERTI DASHBOARD */
    .stApp > div,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stMain"] > div,
    section.main,
    .main {

        padding-top:0px !important;
        margin-top:0px !important;

    }


    /* container utama streamlit */
    .block-container {

        padding-top:0px !important;
        margin-top:0px !important;

    }


    /* header data historis */
    .custom-header {

        position:relative !important;

        top:0px !important;

        margin-bottom:0px !important;

    }   
                
    /* ===============================
   FORM UPLOAD CSV
================================ */


/* samakan Tahun Akademik dengan Pilih File CSV */
[data-testid="stNumberInput"],
[data-testid="stSelectbox"] {

    margin-left:0 !important;

}


/* alert ditemukan mahasiswa full panjang */
[data-testid="stAlert"] {

    margin-left:0 !important;
    width:100% !important;

}


[data-testid="stAlert"] div {

    white-space:nowrap !important;

}


/* ===============================
   LENGKAPI DATA INSTITUSI SAJA
================================ */


/* geser hanya judul lengkapi data institusi */
div[data-testid="stMarkdownContainer"] p strong {

    margin-left:0 !important;

}


/* tombol tetap */
.stButton {

    margin-left:0 !important;

}            
    </style>
    """, unsafe_allow_html=True)

    # ── Sidebar HTML ───────────────────────────────────────────────────────
    st.html(f"""
    <div class="dh-sidebar">
        <div class="brand-title">Prediksi Mahasiswa</div>
        <div class="brand-subtitle">Fakultas Teknologi Informasi</div>
        <div class="side-menu">
            <a class="side-item" href="{base}&page=Dashboard" target="_self">
                {make_icon("dashboard")}Dashboard Utama</a>
            <a class="side-item active" href="{base}&page=Histori" target="_self">
                {make_icon("database")}Data Historis</a>
            <a class="side-item" href="{base}&page=Prediksi" target="_self">
                {make_icon("chart")}Prediksi Mahasiswa Baru</a>
            <a class="side-item" href="{base}&page=Evaluasi" target="_self">
                {make_icon("list")}Evaluasi Model</a>
            <a class="side-item" href="{base}&page=Akun" target="_self">
                {make_icon("account")}Manajemen Akun</a>
            <a class="side-item" href="{base}&page=Laporan" target="_self">
                {make_icon("report")}Visualisasi dan Laporan</a>
        </div>
        <div class="sidebar-user">
            {html_lib.escape(active_name)}<br>{html_lib.escape(role_label)}
        </div>
        <a class="logout-link" href="/?logout=true" target="_self">
            {make_icon("logout")}Log out
        </a>
    </div>
    """)

    # ── Header ───────────────────────────────────────────

    st.markdown("""
    <style>

    /* buang jarak bawaan streamlit */
    [data-testid="stMain"] {
        margin-left:0 !important;
        width:100% !important;
        background:#e3e7eb !important;
        padding:0 !important;
    }


    section[data-testid="stMain"] > div.block-container {

        padding:0 0 0 280px !important;
        margin:0 !important;
        max-width:100% !important;
        min-height:100vh !important;
        position:static !important;
        box-sizing:border-box !important;

    }


    /* HEADER PERSIS DASHBOARD */
    .custom-header {

        height:84px;

        background:white;

        display:flex;

        align-items:center;

        padding:0 28px;

        margin:0 !important;

        box-shadow:
            0 2px 6px rgba(0,0,0,.25);

    }


    .custom-header-title {

        margin:0;

        color:#4a9498;

        font-size:30px;

        line-height:1.05;

        font-weight:800;

    }


    .custom-header-sub {

        display:block;

        color:#4a9498;

        font-size:17px;

        margin-top:5px;

        font-weight:800;

    }


    /* kasih jarak hanya setelah header */
    .element-container:has(.custom-header) {

        margin-top: -38px !important;
        margin-bottom:0px !important;

    }


    /* FORM + TABLE TETAP POSISI LAMA */
    .form-header,
    [data-testid="stFileUploader"],
    [data-testid="stNumberInput"],
    [data-testid="stSelectbox"],
    [data-testid="stAlert"],
    .stButton {

        margin-left:45px !important;

    }


    .table-card,
    .stats-card {

        margin-left:90px !important;
        margin-right:70px !important;

    }

    .table-card {
        margin-top:12px !important;
    }


    .btn-upload,
    .btn-tambah {
        background:#4a9498 !important;
    }


    .data-table th {
        background:white !important;
        color:#555 !important;
    }

    .data-table td {
        color:#555 !important;
    }


    </style>
    """, unsafe_allow_html=True)


    st.html("""
    <header class="custom-header">

        <div>
            <h1 class="custom-header-title">
                Data Historis
            </h1>

            <span class="custom-header-sub">
                FTI UNSAP
            </span>
        </div>

    </header>
    """)

    def back():
        st.session_state.dh_mode = None
        st.session_state.dh_edit_tahun = None
        st.query_params.clear()
        st.query_params.update({"logged_in": "true", "role": role, "page": "Histori"})
        st.rerun()

    # ══════════════════════════
    # MODE: TABEL
    # ══════════════════════════
    if not current_mode:
        df    = load_data_historis()
        stats = compute_stats(df)

        table_rows = ""
        if df.empty:
            table_rows = '<tr><td colspan="9" style="text-align:center;padding:24px;color:#aaa;">Belum ada data</td></tr>'
        else:
            for _, row in df.iterrows():
                t = safe_int(row["tahun"])
                table_rows += f"""
                <tr>
                    <td>{t}</td>
                    <td>{fmt_number(row['informatika'])}</td>
                    <td>{fmt_number(row['sistem_informasi'])}</td>
                    <td>{fmt_number(row['total'])}</td>
                    <td>{fmt_currency(row['biaya_kuliah'])}</td>
                    <td>{akreditasi_badge(safe_int(row['akreditasi']))}</td>
                    <td>{fmt_number(row['kuota_beasiswa'])}</td>
                    <td>{fmt_number(row['jumlah_prodi'])}</td>
                    <td style="display:flex;gap:6px;">
                        <a href="{base}&page=Histori&mode=edit&edit_tahun={t}" target="_self"
                           style="background:#4a9498;color:white;padding:4px 10px;border-radius:4px;font-size:13px;text-decoration:none;">✏️</a>
                        <a href="{base}&page=Histori&mode=hapus&edit_tahun={t}" target="_self"
                           style="background:#ff4444;color:white;padding:4px 10px;border-radius:4px;font-size:13px;text-decoration:none;">🗑️</a>
                    </td>
                </tr>
                """

        stats_rows = ""
        for s in stats:
            stats_rows += f"""
            <tr>
                <td>{html_lib.escape(s['variabel'])}</td>
                <td>{html_lib.escape(s['min'])}</td>
                <td>{html_lib.escape(s['maks'])}</td>
                <td>{html_lib.escape(s['rata'])}</td>
                <td>{html_lib.escape(s['std'])}</td>
                <td>{html_lib.escape(s['catatan'])}</td>
            </tr>
            """
        if not stats_rows:
            stats_rows = '<tr><td colspan="6" style="text-align:center;color:#aaa;padding:20px;">Belum ada data</td></tr>'

        st.html(f"""
        <div class="table-card">
            <div class="table-card-header">
                <div class="table-card-title">Data Historis Mahasiswa FTI</div>
                <div class="table-card-actions">
                    <a class="btn-upload" href="{base}&page=Histori&mode=upload" target="_self">☁ Upload CSV</a>
                    <a class="btn-tambah" href="{base}&page=Histori&mode=tambah" target="_self">+ Tambahkan Manual</a>
                </div>
            </div>
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Tahun</th><th>Informatika</th><th>Sistem Informasi</th>
                        <th>Total</th><th>Biaya Kuliah</th><th>Akreditasi</th>
                        <th>Kuota Beasiswa</th><th>Jumlah Program Studi</th><th>Aksi</th>
                    </tr>
                </thead>
                <tbody>{table_rows}</tbody>
            </table>
        </div>
        <div class="stats-card">
            <div class="stats-card-title">Statistik Deskriptif</div>
            <table class="stats-table">
                <thead>
                    <tr>
                        <th>Variabel</th><th>Min</th><th>Maks</th>
                        <th>Rata - Rata</th><th>STD. DEV</th><th>Catatan</th>
                    </tr>
                </thead>
                <tbody>{stats_rows}</tbody>
            </table>
        </div>
        """)
        return

    # ══════════════════════════
    # MODE: FORM
    # ══════════════════════════

    # ── Upload CSV ──
    if current_mode == "upload":
        st.markdown('<p class="form-header">☁ Upload CSV Mahasiswa</p>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            tahun_up = st.number_input("Tahun Akademik", min_value=2000, max_value=2100, value=2025, key="up_tahun")
        with c2:
            prodi_up = st.selectbox("Program Studi", ["Informatika", "Sistem Informasi"], key="up_prodi")

        file_up = st.file_uploader("Pilih file CSV", type=["csv"], key="up_file")

        if file_up is not None:
            count, err = process_csv_upload(file_up)
            if err:
                st.error(f"Gagal membaca CSV: {err}")
            else:
                st.info(f"Ditemukan **{count}** mahasiswa **{prodi_up}** untuk tahun **{tahun_up}**.")
                existing = get_row(tahun_up)
                if existing:
                    inf_val = count if prodi_up == "Informatika" else safe_int(existing[1])
                    si_val  = count if prodi_up == "Sistem Informasi" else safe_int(existing[2])
                    bk, ak, kb, jp = safe_int(existing[3]), safe_int(existing[4]), safe_int(existing[5]), safe_int(existing[6])
                else:
                    inf_val = count if prodi_up == "Informatika" else 0
                    si_val  = count if prodi_up == "Sistem Informasi" else 0
                    bk, ak, kb, jp = 0, 2, 0, 2

                st.markdown("**Lengkapi data institusi:**")
                c1, c2 = st.columns(2)
                with c1:
                    bk = st.number_input("Biaya Kuliah (Rp)", value=bk, step=50000, key="up_bk")
                    ak = st.selectbox("Akreditasi", [1,2,3,4],
                                      index=[1,2,3,4].index(ak) if ak in [1,2,3,4] else 1,
                                      format_func=lambda x: {1:"1-Kurang",2:"2-Baik",3:"3-Baik Sekali",4:"4-Unggul"}[x],
                                      key="up_ak")
                with c2:
                    kb = st.number_input("Kuota Beasiswa", value=kb, step=1, key="up_kb")
                    jp = st.number_input("Jumlah Program Studi", value=jp if jp > 0 else 2, step=1, key="up_jp")

                if st.button("💾 Simpan", key="up_simpan", type="primary"):
                    upsert_row(tahun_up, inf_val, si_val, bk, ak, kb, jp)
                    st.success(f"Data tahun {tahun_up} berhasil disimpan!")
                    back()

        if st.button("✕ Batal", key="up_batal"):
            back()

    # ── Tambah Manual ──
    elif current_mode == "tambah":
        st.markdown('<p class="form-header">✏️ Tambahkan Data Manual</p>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            tahun_m = st.number_input("Tahun", min_value=2000, max_value=2100, value=2025, key="tm_tahun")
            inf_m   = st.number_input("Jumlah Mahasiswa Informatika", min_value=0, value=0, key="tm_inf")
            si_m    = st.number_input("Jumlah Mahasiswa Sistem Informasi", min_value=0, value=0, key="tm_si")
            bk_m    = st.number_input("Biaya Kuliah (Rp)", min_value=0, value=0, step=50000, key="tm_bk")
        with c2:
            ak_m = st.selectbox("Akreditasi", [1,2,3,4],
                                format_func=lambda x: {1:"1-Kurang",2:"2-Baik",3:"3-Baik Sekali",4:"4-Unggul"}[x],
                                index=1, key="tm_ak")
            kb_m = st.number_input("Kuota Beasiswa", min_value=0, value=0, key="tm_kb")
            jp_m = st.number_input("Jumlah Program Studi", min_value=1, value=2, key="tm_jp")

        st.info(f"Total mahasiswa: **{inf_m + si_m}**")
        col_s, col_b, _ = st.columns([1, 1, 5])
        with col_s:
            if st.button("💾 Simpan", key="tm_simpan", type="primary"):
                upsert_row(tahun_m, inf_m, si_m, bk_m, ak_m, kb_m, jp_m)
                st.success(f"Data tahun {tahun_m} berhasil ditambahkan!")
                back()
        with col_b:
            if st.button("✕ Batal", key="tm_batal"):
                back()

    # ── Edit ──
    elif current_mode == "edit" and st.session_state.dh_edit_tahun:
        tahun_ed = st.session_state.dh_edit_tahun
        row = get_row(tahun_ed)
        if row:
            st.markdown(f'<p class="form-header">✏️ Edit Data Tahun {tahun_ed}</p>', unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            with c1:
                inf_ed = st.number_input("Jumlah Mahasiswa Informatika", min_value=0, value=safe_int(row[1]), key="ed_inf")
                si_ed  = st.number_input("Jumlah Mahasiswa Sistem Informasi", min_value=0, value=safe_int(row[2]), key="ed_si")
                bk_ed  = st.number_input("Biaya Kuliah (Rp)", min_value=0, value=safe_int(row[3]), step=50000, key="ed_bk")
            with c2:
                ak_val = safe_int(row[4])
                ak_ed = st.selectbox("Akreditasi", [1,2,3,4],
                                     format_func=lambda x: {1:"1-Kurang",2:"2-Baik",3:"3-Baik Sekali",4:"4-Unggul"}[x],
                                     index=[1,2,3,4].index(ak_val) if ak_val in [1,2,3,4] else 1,
                                     key="ed_ak")
                kb_ed = st.number_input("Kuota Beasiswa", min_value=0, value=safe_int(row[5]), key="ed_kb")
                jp_ed = st.number_input("Jumlah Program Studi", min_value=1, value=max(1, safe_int(row[6])), key="ed_jp")

            st.info(f"Total mahasiswa: **{inf_ed + si_ed}**")
            col_s, col_b, _ = st.columns([1, 1, 5])
            with col_s:
                if st.button("💾 Simpan Perubahan", key="ed_simpan", type="primary"):
                    upsert_row(tahun_ed, inf_ed, si_ed, bk_ed, ak_ed, kb_ed, jp_ed)
                    st.success(f"Data tahun {tahun_ed} berhasil diperbarui!")
                    back()
            with col_b:
                if st.button("✕ Batal", key="ed_batal"):
                    back()

    # ── Hapus ──
    elif current_mode == "hapus" and st.session_state.dh_edit_tahun:
        tahun_hp = st.session_state.dh_edit_tahun
        st.markdown(f'<p class="form-header">🗑️ Hapus Data Tahun {tahun_hp}</p>', unsafe_allow_html=True)
        st.warning(f"Yakin ingin menghapus data tahun **{tahun_hp}**? Tindakan ini tidak bisa dibatalkan.")
        col_y, col_n, _ = st.columns([1, 1, 5])
        with col_y:
            if st.button("🗑️ Ya, Hapus", key="hp_ya", type="primary"):
                delete_row(tahun_hp)
                st.success(f"Data tahun {tahun_hp} berhasil dihapus!")
                back()
        with col_n:
            if st.button("✕ Batal", key="hp_batal"):
                back()
