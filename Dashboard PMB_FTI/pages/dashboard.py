import base64
import html
import pickle
import sqlite3
from pathlib import Path
from textwrap import dedent

import pandas as pd
import streamlit as st


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "database.db"
MODEL_PATH = BASE_DIR / "model_rfr.pkl"
TARGET_COLUMN = "total_mahasiswa"

MODEL_FEATURE_COLUMNS = [
    ("Biaya Kuliah (X1)", "biaya_kuliah", "Pengaruh dominan"),
    ("Akreditasi (X2)", "akreditasi", "Pengaruh kecil"),
    ("Kuota Beasiswa (X3)", "kuota_beasiswa", "Pengaruh signifikan"),
    ("Jumlah Program Studi (X4)", "jumlah_prodi", "Nilai konstan"),
]


def load_dashboard_data():
    empty_df = pd.DataFrame(
        columns=[
            "tahun",
            "informatika",
            "sistem_informasi",
            TARGET_COLUMN,
            "biaya_kuliah",
            "akreditasi",
            "kuota_beasiswa",
            "jumlah_prodi",
        ]
    )

    if not DB_PATH.exists():
        return empty_df

    if DB_PATH.exists():
        try:
            with sqlite3.connect(DB_PATH) as conn:
                df = pd.read_sql_query(
                    """
                    SELECT tahun,
                           informatika,
                           sistem_informasi,
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
            return df.sort_values("tahun")
        except Exception:
            return empty_df


@st.cache_resource
def load_prediction_model():
    if not MODEL_PATH.exists():
        return None

    with MODEL_PATH.open("rb") as model_file:
        return pickle.load(model_file)


def format_number(value):
    return f"{int(round(value)):,}".replace(",", ".")


def format_currency(value):
    return f"Rp {int(round(value)):,}".replace(",", ".")


def icon_svg(name):
    icon_paths = {
        "dashboard": "assets/dashboard_utama.png",
        "database": "assets/datahistoris_sidebar.png",
        "chart": "assets/prediksi_sidebar.png",
        "list": "assets/evaluasi_sidebar.png",
        "account": "assets/akun_sidebar.png",
        "report": "assets/dokumen_sidebar.png",
        "logout": "assets/logout.png",
        "users": "assets/person_dashboard.png",
        "trend": "assets/prediksi_dashboard.png",
        "percent": "assets/persen.png",
    }

    path = BASE_DIR / icon_paths[name]
    if not path.is_file():
        return ""

    image_base64 = base64.b64encode(path.read_bytes()).decode()

    return f'<img src="data:image/png;base64,{image_base64}" alt="{name}">'


def predict_next_year(df):
    model = load_prediction_model()
    latest_row = df.iloc[-1]

    next_input = pd.DataFrame(
        [
            {
                "biaya_kuliah": latest_row["biaya_kuliah"],
                "akreditasi": latest_row["akreditasi"],
                "kuota_beasiswa": latest_row["kuota_beasiswa"],
                "jumlah_prodi": latest_row["jumlah_prodi"],
            }
        ]
    )

    if model is None:
        recent_growth = df[TARGET_COLUMN].pct_change().dropna()
        average_growth = recent_growth.mean() if not recent_growth.empty else 0
        prediction = latest_row[TARGET_COLUMN] * (1 + average_growth)
        return max(0, round(prediction)), "Estimasi Tren"

    prediction = model.predict(next_input.to_numpy())[0]
    return max(0, round(prediction)), "Random Forest"


def build_line_chart(df):
    years = df["tahun"].tolist()
    values = df[TARGET_COLUMN].tolist()

    min_value = min(values)
    max_value = max(values)
    span = max(max_value - min_value, 1)

    bars = []

    for year, value in zip(years, values):
        height_percent = 20 + ((value - min_value) / span) * 72

        bars.append(
            f"""
            <div class="chart-column">
                <div class="chart-value">{format_number(value)}</div>
                <div class="chart-bar-wrap">
                    <div class="chart-bar" style="height: {height_percent:.2f}%;"></div>
                </div>
                <div class="chart-year">{year}</div>
            </div>
            """
        )

    return f'<div class="trend-chart">{"".join(bars)}</div>'


def build_summary_rows(df):
    first_year = int(df["tahun"].min())
    last_year = int(df["tahun"].max())

    max_row = df.loc[df[TARGET_COLUMN].idxmax()]
    min_row = df.loc[df[TARGET_COLUMN].idxmin()]
    latest_row = df.iloc[-1]

    rows = [
        ("Periode Data", f"{first_year} - {last_year}", False),
        ("Total Observasi", f"{len(df)} tahun", False),
        ("Variabel Bebas", "4 (X1, X2, X3, X4)", False),
        ("Total Mahasiswa", f"{format_number(df[TARGET_COLUMN].sum())} ({first_year} - {last_year})", False),
        ("Maks Mahasiswa", f"{format_number(max_row[TARGET_COLUMN])} (tahun {int(max_row['tahun'])})", True),
        ("Min Mahasiswa", f"{format_number(min_row[TARGET_COLUMN])} (tahun {int(min_row['tahun'])})", True),
        ("Biaya Kuliah Terbaru", format_currency(latest_row["biaya_kuliah"]), False),
    ]

    return "".join(
        f"""
        <div class="summary-row">
            <span>{html.escape(label)}</span>
            <strong class="{'summary-highlight' if highlight else ''}">{html.escape(value)}</strong>
        </div>
        """
        for label, value, highlight in rows
    )


def build_feature_importance_rows():
    model = load_prediction_model()

    if model is not None and hasattr(model, "feature_importances_"):
        values = model.feature_importances_
    else:
        values = [0, 0, 0, 0]

    items = list(zip(MODEL_FEATURE_COLUMNS, values))
    items = sorted(items, key=lambda item: item[1], reverse=True)

    rows = []

    for (label, _, description), importance in items:
        percent = importance * 100

        if importance >= 0.5:
            color = "#0000FF"
        elif importance >= 0.1:
            color = "#ff7a00"
        elif importance > 0:
             color = "#ffc400"
        else:
            color = "#FF0000"

        width = max(4, percent)

        rows.append(
            f"""
            <div class="correlation-row">
                <div class="correlation-label">
                    {html.escape(label)}
                    <small>{html.escape(description)}</small>
                </div>
                <div class="correlation-meter">
                    <span style="width: {width:.2f}%; background: {color};"></span>
                </div>
                <div class="correlation-value" style="color: {color};">{percent:.2f}%</div>
            </div>
            """
        )

    return "".join(rows)


def show_dashboard():
    if st.query_params.get("logout") == "true":
        st.session_state.logged_in = False
        st.session_state.role = None
        st.query_params.clear()
        st.rerun()

    try:
        df = load_dashboard_data()
    except Exception as error:
        st.error(f"Dataset belum bisa dibaca: {error}")
        return

    role = st.query_params.get("role", "admin")
    role_label = "Administrator" if role == "admin" else "Internal FTI"
    active_name = "Admin BAAK FTI" if role == "admin" else "Internal FTI"

    # Bangun sidebar menu berdasarkan role
    if role == "admin":
        extra_menu = f"""
    <a class="side-item"
       href="/?logged_in=true&role={role}&page=Histori"
       target="_self">
       <span class="side-icon">{icon_svg("database")}</span>
       Data Historis
    </a>

    <a class="side-item"
       href="/?logged_in=true&role={role}&page=Prediksi"
       target="_self">
       <span class="side-icon">{icon_svg("chart")}</span>
       Prediksi Mahasiswa Baru
    </a>

    <a class="side-item"
       href="/?logged_in=true&role={role}&page=Evaluasi"
       target="_self">
       <span class="side-icon">{icon_svg("list")}</span>
       Evaluasi Model
    </a>

    <a class="side-item"
       href="/?logged_in=true&role={role}&page=Akun"
       target="_self">
       <span class="side-icon">{icon_svg("account")}</span>
       Manajemen Akun
    </a>
        """
    else:
        extra_menu = ""

    if df.empty:
        chart_column_count = 1
        dashboard_content = f"""
                <div class="empty-panel">
                    <div class="empty-title">Data historis belum tersedia</div>
                    <div class="empty-text">
                        Tambahkan data pada halaman Data Historis agar informasi dashboard dapat ditampilkan.
                    </div>
                    <a class="empty-action" href="/?logged_in=true&role={role}&page=Histori" target="_self">
                        Buka Data Historis
                    </a>
                </div>
        """
    else:
        latest_row = df.iloc[-1]
        latest_year = int(latest_row["tahun"])
        latest_total = int(latest_row[TARGET_COLUMN])

        next_year = latest_year + 1
        predicted_total, prediction_source = predict_next_year(df)

        growth_series = df[TARGET_COLUMN].pct_change().dropna()
        average_growth = growth_series.mean() * 100 if not growth_series.empty else 0
        chart_column_count = len(df)
        dashboard_content = f"""
                <div class="kpi-grid">
                    <div class="kpi-card">
                        <div class="kpi-icon">{icon_svg("users")}</div>
                        <div>
                            <div class="kpi-label">Mahasiswa Baru FTI<br>{latest_year}</div>
                            <div class="kpi-value">{format_number(latest_total)}<span>Mhs</span></div>
                        </div>
                    </div>

                    <div class="kpi-card">
                        <div class="kpi-icon">{icon_svg("trend")}</div>
                        <div>
                            <div class="kpi-label">Prediksi {next_year}<br>{prediction_source}</div>
                            <div class="kpi-value">{format_number(predicted_total)}<span>Mhs</span></div>
                        </div>
                    </div>

                    <div class="kpi-card">
                        <div class="kpi-icon">{icon_svg("percent")}</div>
                        <div>
                            <div class="kpi-label">Rata-rata<br>Pertumbuhan</div>
                            <div class="kpi-value">{average_growth:.2f}<span>%</span></div>
                        </div>
                    </div>
                </div>

                <div class="middle-grid">
                    <div class="panel">
                        <div class="panel-title">Jumlah Mahasiswa FTI ({int(df["tahun"].min())} - {latest_year})</div>
                        {build_line_chart(df)}
                    </div>

                    <div class="panel">
                        <div class="panel-title">Ringkasan Dataset</div>
                        {build_summary_rows(df)}
                    </div>
                </div>

                <div class="panel correlation-panel">
                    <div class="panel-title">Feature Importance Random Forest</div>
                    {build_feature_importance_rows()}
                </div>
        """

    dashboard_html = dedent(f"""
    <style>
    [data-testid="stHeader"],
    [data-testid="stSidebar"] {{
        display: none;
    }}

    html,
    body,
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"] {{
        margin: 0 !important;
        padding: 0 !important;
    }}

    .stApp {{
        background: #e3e7eb;
    }}

    .block-container {{
        max-width: 100% !important;
        padding: 0 !important;
        margin: 0 !important;
    }}

    .dashboard-shell {{
        position: fixed;
        inset: 0;
        z-index: 999;
        height: 100vh;
        overflow-y: auto;
        display: grid;
        grid-template-columns: 280px 1fr;
        background: #e3e7eb;
        color: #123047;
        font-family: Arial, sans-serif;
    }}

    .dashboard-sidebar {{
        background: #4a9498;
        color: white;
        padding: 36px 22px 28px;
        display: flex;
        flex-direction: column;
        min-height: 100vh;
    }}

    .brand-title {{
        font-size: 21px;
        font-weight: 800;
        line-height: 1.2;
    }}

    .brand-subtitle {{
        font-size: 13px;
        font-weight: 700;
        margin-top: 6px;
        padding-bottom: 18px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.25);
    }}

    .side-menu {{
        margin-top: 24px;
        display: grid;
        gap: 16px;
    }}

    .side-item {{
        color: white;
        text-decoration: none;
        display: flex;
        align-items: center;
        gap: 13px;
        padding: 11px 10px;
        border-radius: 4px;
        font-size: 16px;
    }}

    .side-item.active {{
        background: #e9c91d;
    }}

    .side-icon {{
        width: 24px;
        height: 24px;
        flex: 0 0 24px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
    }}

    .side-icon img {{
        width: 23px;
        height: 23px;
        object-fit: contain;
    }}

    .sidebar-user {{
        margin-top: auto;
        padding: 16px 8px 0;
        border-top: 1px solid rgba(255, 255, 255, 0.25);
        color: rgba(255, 255, 255, 0.6);
        line-height: 1.35;
        font-size: 16px;
    }}

    .logout-link {{
        margin-top: 220px;
        color: white;
        text-decoration: none;
        display: flex;
        align-items: center;
        gap: 12px;
        font-size: 16px;
    }}

    .dashboard-header {{
        height: 84px;
        background: white;
        display: flex;
        align-items: center;
        padding: 0 28px;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25);
    }}

    .dashboard-header h1 {{
        margin: 0;
        color: #4a9498;
        font-size: 28px;
        line-height: 1.05;
    }}

    .dashboard-header span {{
        display: block;
        font-size: 17px;
        margin-top: 5px;
        font-weight: 800;
    }}

    .dashboard-content {{
        padding: 34px 52px 52px;
    }}

    .empty-panel {{
        background: white;
        box-shadow: 0 3px 8px rgba(0, 0, 0, 0.25);
        padding: 24px 28px 28px;
        color: #123047;
    }}

    .empty-title {{
        color: #4a9498;
        font-size: 20px;
        font-weight: 800;
        margin-bottom: 8px;
    }}

    .empty-text {{
        color: #52666d;
        font-size: 15px;
        font-weight: 700;
        margin-bottom: 18px;
    }}

    .empty-action {{
        background: #4a9498;
        color: white;
        text-decoration: none;
        display: inline-flex;
        align-items: center;
        padding: 9px 18px;
        border-radius: 4px;
        font-size: 14px;
        font-weight: 800;
    }}

    .kpi-grid {{
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 58px;
        margin-bottom: 24px;
    }}

    .kpi-card,
    .panel {{
        background: white;
        box-shadow: 0 3px 8px rgba(0, 0, 0, 0.25);
    }}

    .kpi-card {{
        min-height: 122px;
        padding: 20px 26px;
        display: grid;
        grid-template-columns: 58px 1fr;
        align-items: center;
        column-gap: 12px;
    }}

    .kpi-icon {{
        width: 58px;
        height: 58px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #4a9498;
        border-radius: 50%;
    }}

    .kpi-icon img {{
        width: 38px;
        height: 38px;
        object-fit: contain;
    }}

    .kpi-label {{
        color: #4a9498;
        font-weight: 800;
        font-size: 17px;
        line-height: 1.2;
    }}

    .kpi-value {{
        margin-top: 8px;
        color: #4a9498;
        font-size: 34px;
        font-weight: 800;
    }}

    .kpi-value span {{
        font-size: 19px;
        margin-left: 8px;
    }}

    .middle-grid {{
        display: grid;
        grid-template-columns: 1fr 1.05fr;
        gap: 24px;
        margin-bottom: 34px;
    }}

    .panel {{
        padding: 16px 18px 20px;
    }}

    .panel-title {{
        color: #4a9498;
        font-size: 17px;
        font-weight: 800;
        margin-bottom: 10px;
    }}

    .trend-chart {{
        width: 100%;
        height: 255px;
        display: grid;
        grid-template-columns: repeat({chart_column_count}, minmax(42px, 1fr));
        gap: 18px;
        align-items: end;
        padding: 18px 24px 8px;
        border-left: 1px solid #c4ced4;
        border-bottom: 1px solid #c4ced4;
        background:
            linear-gradient(to bottom, transparent 0, transparent 32%, #e2e8ec 33%, transparent 34%),
            linear-gradient(to bottom, transparent 0, transparent 65%, #e2e8ec 66%, transparent 67%);
        box-sizing: border-box;
    }}

    .chart-column {{
        height: 100%;
        display: grid;
        grid-template-rows: 22px 1fr 20px;
        align-items: end;
        justify-items: center;
        color: #60757c;
        font-size: 11px;
        font-weight: 700;
    }}

    .chart-value {{
        align-self: start;
        color: #4a9498;
        font-size: 12px;
    }}

    .chart-bar-wrap {{
        width: 100%;
        height: 100%;
        display: flex;
        align-items: end;
        justify-content: center;
    }}

    .chart-bar {{
        width: 34px;
        min-height: 8px;
        background: #4a9498;
        border-radius: 6px 6px 0 0;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
    }}

    .chart-year {{
        align-self: end;
    }}

    .summary-row {{
        min-height: 28px;
        background: #60aeb4;
        color: white;
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 15px;
        margin: 10px 0;
        border-radius: 4px;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.22);
        font-size: 14px;
        font-weight: 800;
    }}

    .summary-highlight {{
        color: #ff7a00;
    }}

    .correlation-panel {{
        padding: 16px 18px 26px;
    }}

    .correlation-row {{
        min-height: 48px;
        background: #60aeb4;
        color: white;
        display: grid;
        grid-template-columns: 1fr 180px 86px;
        align-items: center;
        gap: 18px;
        padding: 8px 14px;
        margin-top: 16px;
        border-radius: 4px;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.22);
        font-size: 14px;
        font-weight: 800;
    }}

    .correlation-label small {{
        display: block;
        font-size: 11px;
        opacity: 0.82;
        margin-top: 2px;
        font-weight: 700;
    }}

    .correlation-meter {{
        height: 5px;
        background: rgba(255, 255, 255, 0.25);
        border-radius: 999px;
        overflow: hidden;
    }}

    .correlation-meter span {{
        display: block;
        height: 100%;
        border-radius: 999px;
    }}

    .correlation-value {{
        text-align: right;
    }}

    .summary-highlight {
        color: #4a9498;
        background: rgba(74, 148, 152, 0.1);
        padding: 2px 8px;
        border-radius: 4px;
    }

    @media (max-width: 768px) {
        .dashboard-shell { grid-template-columns: 1fr; display: flex; flex-direction: column; }
        .dashboard-sidebar { min-height: auto; padding: 20px; }
        .logout-link { margin-top: 40px; }
        .dashboard-content { padding: 20px; }
        .kpi-grid, .middle-grid { grid-template-columns: 1fr; gap: 16px; }
    }
    </style>

    <div class="dashboard-shell">
        <aside class="dashboard-sidebar">
            <div class="brand-title">Prediksi Mahasiswa</div>
            <div class="brand-subtitle">Fakultas Teknologi Informasi</div>

            <nav class="side-menu">
                <a class="side-item active"
                   href="/?logged_in=true&role={role}&page=Dashboard"
                   target="_self">
                   <span class="side-icon">{icon_svg("dashboard")}</span>
                   Dashboard Utama
                </a>

                {extra_menu}

                <a class="side-item"
                   href="/?logged_in=true&role={role}&page=Laporan"
                   target="_self">
                   <span class="side-icon">{icon_svg("report")}</span>
                   Visualisasi dan Laporan
                </a>
            </nav>

            <div class="sidebar-user">
                {html.escape(active_name)}<br>
                {html.escape(role_label)}
            </div>

            <a class="logout-link" href="/?logout=true" target="_self">
                <span class="side-icon">{icon_svg("logout")}</span>Log out
            </a>
        </aside>

        <main class="dashboard-main">
            <header class="dashboard-header">
                <h1>Dashboard Utama<span>FTI UNSAP</span></h1>
            </header>

            <section class="dashboard-content">
                {dashboard_content}
            </section>
        </main>
    </div>
    """)

    st.html(dashboard_html)