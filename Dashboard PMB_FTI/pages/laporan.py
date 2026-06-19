import base64
import html
import io
import pickle
import sqlite3
from pathlib import Path
from textwrap import dedent
import time

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH    = BASE_DIR / "database.db"
MODEL_PATH = BASE_DIR / "model_rfr.pkl"
TARGET_COLUMN = "total_mahasiswa"

AKREDITASI_MAP = {1: "Kurang", 2: "Baik", 3: "Baik Sekali", 4: "Unggul"}


# ── helpers ───────────────────────────────────────────────────────────────────

def load_data():
    empty = pd.DataFrame(columns=[
        "tahun", "informatika", "sistem_informasi", TARGET_COLUMN,
        "biaya_kuliah", "akreditasi", "kuota_beasiswa", "jumlah_prodi",
    ])
    if not DB_PATH.exists():
        return empty
    try:
        with sqlite3.connect(DB_PATH) as conn:
            df = pd.read_sql_query("""
                SELECT tahun, informatika, sistem_informasi,
                       (informatika + sistem_informasi) AS total_mahasiswa,
                       biaya_kuliah, akreditasi, kuota_beasiswa, jumlah_prodi
                FROM data_historis ORDER BY tahun
            """, conn)
        return df.sort_values("tahun").reset_index(drop=True)
    except Exception:
        return empty


def load_riwayat_prediksi():
    """Ambil prediksi yang sudah dijalankan dari page Prediksi Mahasiswa Baru."""
    if not DB_PATH.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            df = pd.read_sql_query("""
                SELECT tahun, prediksi, biaya_kuliah, akreditasi,
                       kuota_beasiswa, jumlah_prodi, dibuat_pada
                FROM riwayat_prediksi
                ORDER BY tahun, dibuat_pada DESC
            """, conn)
        # Ambil prediksi terbaru per tahun
        df = df.drop_duplicates(subset=["tahun"], keep="first")
        return df.sort_values("tahun").reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


@st.cache_resource
def load_model():
    if not MODEL_PATH.exists():
        return None
    with MODEL_PATH.open("rb") as f:
        return pickle.load(f)


def fmt_num(v):
    return f"{int(round(v)):,}".replace(",", ".")


def fmt_currency(v):
    return f"Rp {int(round(v)):,}".replace(",", ".")


def svg_to_img(svg_str: str) -> str:
    b64 = base64.b64encode(svg_str.strip().encode("utf-8")).decode()
    return f'<img src="data:image/svg+xml;base64,{b64}" style="width:100%;height:auto;display:block;">'


def icon_b64(name):
    paths = {
        "dashboard": "assets/dashboard_utama.png",
        "database":  "assets/datahistoris_sidebar.png",
        "chart":     "assets/prediksi_sidebar.png",
        "list":      "assets/evaluasi_sidebar.png",
        "account":   "assets/akun_sidebar.png",
        "report":    "assets/dokumen_sidebar.png",
        "logout":    "assets/logout.png",
    }
    p = BASE_DIR / paths.get(name, "")
    if not p.is_file():
        return ""
    return f'<img src="data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}" alt="{name}">'


def safe_growth(df):
    chg = df[TARGET_COLUMN].pct_change().dropna()
    if chg.empty:
        return 0.0
    val = chg.mean() * 100
    return 0.0 if pd.isna(val) else float(val)


def build_pred_series(df, riwayat):
    """
    Gabungkan data historis dengan prediksi dari riwayat_prediksi.
    Jika riwayat kosong, fallback ke perhitungan rule-based.
    """
    results = [(int(r["tahun"]), int(r[TARGET_COLUMN])) for _, r in df.iterrows()]
    latest_yr = int(df.iloc[-1]["tahun"])

    if not riwayat.empty:
        pred_rows = riwayat[riwayat["tahun"] == latest_yr + 1]
        if not pred_rows.empty:
            for _, r in pred_rows.iterrows():
                results.append((int(r["tahun"]), int(r["prediksi"])))
            # Hapus paksaan minimal 2 tahun agar prediksi bisa realtime
            return results

    # Fallback: rule-based
    model  = load_model()
    latest = df.iloc[-1]
    feat = {
        "biaya_kuliah":   float(latest["biaya_kuliah"]),
        "akreditasi":     float(latest["akreditasi"]),
        "kuota_beasiswa": float(latest["kuota_beasiswa"]),
        "jumlah_prodi":   float(latest["jumlah_prodi"]),
    }
    for i in range(1, 2):  # Hanya 1 tahun ke depan secara default
        yr = latest_yr + i
        if model:
            inp = pd.DataFrame([feat])
            val = int(round(model.predict(inp.to_numpy())[0]))
        else:
            pct = df[TARGET_COLUMN].pct_change().dropna().mean()
            pct = 0.0 if pd.isna(pct) else float(pct)
            val = int(round(results[-1][1] * (1 + pct)))
        results.append((yr, max(0, val)))
        feat["biaya_kuliah"] *= 1.05
    return results


def model_metrics(df):
    model = load_model()
    if model is None or len(df) < 3:
        return None, None
    X = df[["biaya_kuliah", "akreditasi", "kuota_beasiswa", "jumlah_prodi"]].to_numpy()
    y = df[TARGET_COLUMN].to_numpy()
    preds = model.predict(X)
    ss_res = ((y - preds) ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2   = 1 - ss_res / ss_tot if ss_tot != 0 else 0
    mape = (abs((y - preds) / y)).mean() * 100
    return round(r2 * 100, 1), round(mape, 1)


# ── ringkasan eksekutif ───────────────────────────────────────────────────────

def generate_ringkasan(df, pred_series):
    if df.empty:
        return [], []

    latest       = df.iloc[-1]
    first        = df.iloc[0]
    growth_avg   = safe_growth(df)
    biaya_delta  = latest["biaya_kuliah"] - first["biaya_kuliah"]
    beasiswa_chg = latest["kuota_beasiswa"] - first["kuota_beasiswa"]
    preds_only   = [v for y, v in pred_series if y > int(latest["tahun"])]
    pred_next    = preds_only[0] if len(preds_only) > 0 else 0
    pred_next2   = preds_only[1] if len(preds_only) > 1 else 0
    latest_yr    = int(latest["tahun"])
    akr_lbl      = AKREDITASI_MAP.get(int(latest["akreditasi"]), str(int(latest["akreditasi"])))

    temuan = []
    rekomendasi = []

    if growth_avg < 0:
        temuan.append(
            f"Tren Penurunan: Terdeteksi penurunan rata-rata sebesar "
            f"{abs(growth_avg):.1f}% per tahun sejak periode {int(first['tahun'])} hingga {latest_yr}."
        )
    else:
        temuan.append(
            f"Tren Positif: Pertumbuhan rata-rata sebesar {growth_avg:.1f}% per tahun "
            f"sejak {int(first['tahun'])} hingga {latest_yr}."
        )

    if biaya_delta > 0:
        temuan.append(
            f"Dinamika Biaya Kuliah: Terjadi kenaikan biaya kuliah dari "
            f"{fmt_currency(first['biaya_kuliah'])} ({int(first['tahun'])}) menjadi "
            f"{fmt_currency(latest['biaya_kuliah'])} ({latest_yr})."
        )

    if beasiswa_chg < 0:
        temuan.append(
            f"Korelasi Beasiswa: Penurunan kuota beasiswa dari "
            f"{fmt_num(first['kuota_beasiswa'])} menjadi {fmt_num(latest['kuota_beasiswa'])} "
            f"berkorelasi dengan penurunan jumlah mahasiswa di tahun yang sama."
        )
    else:
        temuan.append(
            f"Korelasi Beasiswa: Kuota beasiswa meningkat dari "
            f"{fmt_num(first['kuota_beasiswa'])} menjadi {fmt_num(latest['kuota_beasiswa'])}."
        )

    temuan.append(
        f"Pencapaian Akreditasi: Berhasil mencapai Akreditasi {akr_lbl} "
        f"di tahun {latest_yr} sebagai modal untuk strategi rekrutmen mendatang."
    )

    if len(preds_only) == 1:
        temuan.append(
            f"Proyeksi Recovery ({latest_yr+1}): Berdasarkan model Random Forest, "
            f"diprediksi estimasi {fmt_num(preds_only[0])} mahasiswa baru "
            f"jika variabel pendukung dioptimalkan."
        )
    elif len(preds_only) > 1:
        temuan.append(
            f"Proyeksi Recovery ({latest_yr+1}–{latest_yr+len(preds_only)}): Berdasarkan model Random Forest, "
            f"diprediksi estimasi {fmt_num(preds_only[0])} dan {fmt_num(preds_only[1])} mahasiswa baru "
            f"jika variabel pendukung dioptimalkan."
        )

    max_bea = df['kuota_beasiswa'].max() if not df.empty else 200
    if beasiswa_chg <= 0 or growth_avg < 0:
        rekomendasi.append(
            "URGENT – Optimasi Beasiswa: Mengembalikan atau meningkatkan kuota beasiswa "
            f"ke angka minimal {int(max_bea)}+ untuk menarik minat calon mahasiswa di tahun akademik berikutnya."
        )

    if biaya_delta > 0:
        rekomendasi.append(
            "Kebijakan Finansial: Melakukan evaluasi kebijakan biaya kuliah atau "
            "mempertimbangkan skema pembayaran cicilan/bertahap guna mengurangi beban finansial calon pendaftar."
        )

    rekomendasi.append(
        f"Marketing Berbasis Kualitas: Memanfaatkan status Akreditasi {akr_lbl} "
        "secara masif dalam konten promosi untuk meningkatkan kepercayaan masyarakat terhadap mutu pendidikan FTI."
    )

    if int(latest["jumlah_prodi"]) < 4:
        rekomendasi.append(
            "Ekspansi Akademik: Mempertimbangkan pembukaan program studi baru yang "
            "memiliki relevansi tinggi dengan kebutuhan industri saat ini."
        )

    rekomendasi.append(
        "Monitoring Adaptif: Melakukan pengawasan data pendaftaran secara bulanan agar "
        "strategi pemasaran dapat disesuaikan secara real-time dengan tren pasar."
    )

    return temuan, rekomendasi


# ── chart builders ────────────────────────────────────────────────────────────

def build_trend_chart(pred_series, latest_yr):
    years  = [str(y) for y, _ in pred_series]
    values = [v for _, v in pred_series]
    mn, mx = min(values), max(values)
    span   = max(mx - mn, 1)

    W, H = 560, 240
    pad_l, pad_r, pad_t, pad_b = 55, 20, 35, 40
    cw = W - pad_l - pad_r
    ch = H - pad_t - pad_b
    n  = len(values)

    coords = []
    for i, v in enumerate(values):
        x = pad_l + (i / (n - 1)) * cw if n > 1 else pad_l + cw / 2
        y = pad_t + ch - ((v - mn) / span) * ch
        coords.append((x, y))

    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(coords))
    area_path = (
        f"M{coords[0][0]:.1f},{pad_t+ch} " +
        " ".join(f"L{x:.1f},{y:.1f}" for x, y in coords) +
        f" L{coords[-1][0]:.1f},{pad_t+ch} Z"
    )

    gridlines = ""
    for step in [0, 0.5, 1.0]:
        gy = pad_t + ch - step * ch
        gv = int(mn + step * span)
        gridlines += (
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{pad_l+cw}" y2="{gy:.1f}" '
            f'stroke="#e0e8ea" stroke-width="1" stroke-dasharray="4,3"/>'
            f'<text x="{pad_l-6}" y="{gy+4:.1f}" text-anchor="end" font-size="10" fill="#8aa0a6">{fmt_num(gv)}</text>'
        )

    dots = labels = x_labels = ""
    for i, ((x, y), yr, val) in enumerate(zip(coords, years, values)):
        is_pred = int(yr) > latest_yr
        color = "#e9a800" if is_pred else "#2e7d82"
        dots   += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{color}" stroke="white" stroke-width="2"/>'
        labels += f'<text x="{x:.1f}" y="{y-12:.1f}" text-anchor="middle" font-size="11" fill="{color}" font-weight="700">{fmt_num(val)}</text>'
        x_labels += f'<text x="{x:.1f}" y="{H-6}" text-anchor="middle" font-size="11" fill="#4a6670">{yr}</text>'

    # Legend — lebih besar
    legend = (
        f'<rect x="{pad_l+cw-130}" y="6" width="14" height="14" fill="#2e7d82" rx="3"/>'
        f'<text x="{pad_l+cw-112}" y="18" font-size="13" font-weight="700" fill="#2e7d82">Aktual</text>'
        f'<rect x="{pad_l+cw-55}" y="6" width="14" height="14" fill="#e9a800" rx="3"/>'
        f'<text x="{pad_l+cw-37}" y="18" font-size="13" font-weight="700" fill="#e9a800">Prediksi</text>'
    )

    svg = f"""<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="ag" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#4a9498" stop-opacity="0.3"/>
      <stop offset="100%" stop-color="#4a9498" stop-opacity="0"/>
    </linearGradient>
  </defs>
  {gridlines}
  <line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t+ch}" stroke="#c4ced4" stroke-width="1.5"/>
  <line x1="{pad_l}" y1="{pad_t+ch}" x2="{pad_l+cw}" y2="{pad_t+ch}" stroke="#c4ced4" stroke-width="1.5"/>
  <path d="{area_path}" fill="url(#ag)"/>
  <path d="{path}" fill="none" stroke="#4a9498" stroke-width="2.5" stroke-linejoin="round"/>
  {dots}{labels}{x_labels}{legend}
</svg>"""
    return svg


def build_bar_comparison(df):
    if df.empty:
        return ""
    years = df["tahun"].tolist()
    bea   = df["kuota_beasiswa"].tolist()
    mhs   = df[TARGET_COLUMN].tolist()
    mx    = max(max(bea), max(mhs), 1)

    W, H  = 500, 240
    pad_l, pad_b = 45, 40
    cw, ch = W - pad_l - 10, H - pad_b - 15
    n     = len(years)
    grp_w = cw / n
    bar_w = grp_w * 0.32

    gridlines = ""
    for step in [0, 0.5, 1.0]:
        gy = 15 + ch - step * ch
        gv = int(step * mx)
        gridlines += (
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{pad_l+cw}" y2="{gy:.1f}" '
            f'stroke="#e0e8ea" stroke-width="1" stroke-dasharray="4,3"/>'
            f'<text x="{pad_l-4}" y="{gy+3:.1f}" text-anchor="end" font-size="9" fill="#8aa0a6">{fmt_num(gv)}</text>'
        )

    bars = x_labels = ""
    for i, (yr, b, m) in enumerate(zip(years, bea, mhs)):
        x0 = pad_l + i * grp_w + grp_w * 0.1
        bh = max((b / mx) * ch, 2)
        mh = max((m / mx) * ch, 2)
        by = 15 + ch - bh
        my = 15 + ch - mh
        bars += (
            f'<rect x="{x0:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" fill="#4a9498" rx="2"/>'
            f'<text x="{x0+bar_w/2:.1f}" y="{by-3:.1f}" text-anchor="middle" font-size="9" fill="#2e7d82" font-weight="700">{fmt_num(b)}</text>'
            f'<rect x="{x0+bar_w+3:.1f}" y="{my:.1f}" width="{bar_w:.1f}" height="{mh:.1f}" fill="#e9a800" rx="2"/>'
            f'<text x="{x0+bar_w*1.5+3:.1f}" y="{my-3:.1f}" text-anchor="middle" font-size="9" fill="#b07000" font-weight="700">{fmt_num(m)}</text>'
        )
        x_labels += f'<text x="{x0+bar_w:.1f}" y="{H-6}" text-anchor="middle" font-size="10" fill="#4a6670">{int(yr)}</text>'

    # Legend — lebih besar
    legend = (
        f'<rect x="{pad_l}" y="{H-32}" width="13" height="13" fill="#4a9498" rx="2"/>'
        f'<text x="{pad_l+17}" y="{H-22}" font-size="12" font-weight="700" fill="#4a9498">Kuota Beasiswa</text>'
        f'<rect x="{pad_l+130}" y="{H-32}" width="13" height="13" fill="#e9a800" rx="2"/>'
        f'<text x="{pad_l+147}" y="{H-22}" font-size="12" font-weight="700" fill="#b07000">Jumlah Mahasiswa</text>'
    )

    svg = f"""<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">
  {gridlines}
  <line x1="{pad_l}" y1="15" x2="{pad_l}" y2="{15+ch}" stroke="#c4ced4" stroke-width="1.5"/>
  <line x1="{pad_l}" y1="{15+ch}" x2="{W-10}" y2="{15+ch}" stroke="#c4ced4" stroke-width="1.5"/>
  {bars}{x_labels}{legend}
</svg>"""
    return svg


# ── export helpers ────────────────────────────────────────────────────────────

def export_excel(df, pred_series, temuan, rekomendasi):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Data Historis", index=False)
        pred_df = pd.DataFrame(pred_series, columns=["Tahun", "Prediksi Mahasiswa"])
        pred_df.to_excel(writer, sheet_name="Prediksi", index=False)
        rows = (
            [["TEMUAN UTAMA", ""]] +
            [[f"{i+1}.", t] for i, t in enumerate(temuan)] +
            [["", ""], ["REKOMENDASI STRATEGIS", ""]] +
            [[f"{i+1}.", r] for i, r in enumerate(rekomendasi)]
        )
        pd.DataFrame(rows, columns=["No", "Keterangan"]).to_excel(
            writer, sheet_name="Ringkasan Eksekutif", index=False
        )
    buf.seek(0)
    return buf.getvalue()


def export_pdf_html(df, pred_series, temuan, rekomendasi, jenis, mape,
                    growth_avg, latest_yr, pred_next, trend_svg_raw, bar_svg_raw):
    temuan_rows = "".join(f"<li>{html.escape(t)}</li>" for t in temuan)
    rek_rows    = "".join(f"<li>{html.escape(r)}</li>" for r in rekomendasi)
    hist_rows   = "".join(
        f"<tr><td>{int(r['tahun'])}</td><td>{fmt_num(r[TARGET_COLUMN])}</td>"
        f"<td>{fmt_currency(r['biaya_kuliah'])}</td><td>{int(r['kuota_beasiswa'])}</td>"
        f"<td>{AKREDITASI_MAP.get(int(r['akreditasi']), str(int(r['akreditasi'])))}</td>"
        f"<td>{int(r['jumlah_prodi'])}</td></tr>"
        for _, r in df.iterrows()
    )
    pred_rows = "".join(
        f"<tr><td>{yr}</td><td>{fmt_num(v)}</td>"
        f"<td>{'Prediksi' if yr > latest_yr else 'Aktual'}</td></tr>"
        for yr, v in pred_series
    )
    chart_section = ""
    if jenis != "Ringkasan":
        chart_section = f"""
        <h2>Tren Mahasiswa Baru &amp; Prediksi</h2>{trend_svg_raw}
        <h2>Perbandingan Beasiswa &amp; Mahasiswa</h2>{bar_svg_raw}
        """

    mape_str = f"MAPE: {mape}%" if mape is not None else ""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Laporan {html.escape(jenis)} – PMB FTI UNSAP</title>
<style>
  body{{font-family:Arial,sans-serif;margin:32px;color:#123047;font-size:13px;}}
  h1{{color:#4a9498;}} h2{{color:#4a9498;border-bottom:2px solid #4a9498;padding-bottom:4px;margin-top:24px;}}
  table{{border-collapse:collapse;width:100%;margin-bottom:20px;}}
  th{{background:#4a9498;color:white;padding:6px 10px;text-align:left;}}
  td{{padding:5px 10px;border-bottom:1px solid #dde;}}
  li{{margin-bottom:6px;}}
  .kpi{{display:inline-block;background:#4a9498;color:white;padding:10px 18px;margin:6px;border-radius:6px;}}
  svg{{max-width:100%;}}
  @media print{{button{{display:none;}}}}
</style></head><body>
<h1>Laporan {html.escape(jenis)} – PMB FTI UNSAP</h1>
<p>Digenerate otomatis oleh Sistem Prediksi Mahasiswa FTI UNSAP</p>
<div>
  <span class="kpi">Rata-rata Pertumbuhan: {growth_avg:+.1f}%</span>
  <span class="kpi">Prediksi {latest_yr+1}: {fmt_num(pred_next)} Mhs</span>
  {f'<span class="kpi">{mape_str}</span>' if mape_str else ""}
</div>
{chart_section}
<h2>Data Historis</h2>
<table><tr><th>Tahun</th><th>Total Mahasiswa</th><th>Biaya Kuliah</th>
<th>Kuota Beasiswa</th><th>Akreditasi</th><th>Jml Prodi</th></tr>
{hist_rows}</table>
<h2>Prediksi</h2>
<table><tr><th>Tahun</th><th>Jumlah Mahasiswa</th><th>Status</th></tr>
{pred_rows}</table>
<h2>Temuan Utama</h2><ul>{temuan_rows}</ul>
<h2>Rekomendasi Strategis</h2><ul>{rek_rows}</ul>
<br><button onclick="window.print()">&#128438; Print / Save as PDF</button>
</body></html>"""


# ── main page ─────────────────────────────────────────────────────────────────

def show_visualisasi_laporan():
    if st.query_params.get("logout") == "true":
        st.session_state.logged_in = False
        st.session_state.role = None
        st.query_params.clear()
        st.rerun()

    role        = st.query_params.get("role", "admin")
    role_label  = "Administrator" if role == "admin" else "Internal FTI"
    active_name = "Admin BAAK FTI" if role == "admin" else "Internal FTI"

    # ── load data fresh ───────────────────────────────────────────────────────
    df       = load_data()
    riwayat  = load_riwayat_prediksi()

    # sidebar
    if role == "admin":
        extra_menu = f"""
    <a class="side-item" href="/?logged_in=true&role={role}&page=Histori&_t={int(time.time())}" target="_self">
       <span class="side-icon">{icon_b64("database")}</span> Data Historis</a>
    <a class="side-item" href="/?logged_in=true&role={role}&page=Prediksi&_t={int(time.time())}" target="_self">
       <span class="side-icon">{icon_b64("chart")}</span> Prediksi Mahasiswa Baru</a>
    <a class="side-item" href="/?logged_in=true&role={role}&page=Evaluasi&_t={int(time.time())}" target="_self">
       <span class="side-icon">{icon_b64("list")}</span> Evaluasi Model</a>
    <a class="side-item" href="/?logged_in=true&role={role}&page=Akun&_t={int(time.time())}" target="_self">
       <span class="side-icon">{icon_b64("account")}</span> Manajemen Akun</a>"""
    else:
        extra_menu = ""

    # ── compute ───────────────────────────────────────────────────────────────
    if not df.empty:
        pred_series  = build_pred_series(df, riwayat)
        temuan, rek  = generate_ringkasan(df, pred_series)
        _, mape      = model_metrics(df)
        latest       = df.iloc[-1]
        latest_yr    = int(latest["tahun"])
        growth_avg   = safe_growth(df)
        preds_only   = [v for y, v in pred_series if y > latest_yr]
        pred_next    = preds_only[0] if len(preds_only) > 0 else 0
        pred_next2   = preds_only[1] if len(preds_only) > 1 else 0
        trend_svg_raw = build_trend_chart(pred_series, latest_yr)
        bar_svg_raw   = build_bar_comparison(df)
        trend_img     = svg_to_img(trend_svg_raw)
        bar_img       = svg_to_img(bar_svg_raw)
    else:
        pred_series = temuan = rek = []
        mape = None
        latest_yr = 0
        growth_avg = pred_next = pred_next2 = 0
        trend_svg_raw = bar_svg_raw = trend_img = bar_img = ""
        latest = None

    jenis = st.query_params.get("jenis", "Komprehensif")
    if jenis not in ["Komprehensif", "Ringkasan", "Prediksi Saja"]:
        jenis = "Komprehensif"

    def control_panel():
        if df.empty: return ""
        xl_bytes = export_excel(df, pred_series, temuan, rek)
        xl_b64 = base64.b64encode(xl_bytes).decode()
        excel_href = f"data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{xl_b64}"
        
        opts = ""
        for opt in ["Komprehensif", "Ringkasan", "Prediksi Saja"]:
            sel = "selected" if opt == jenis else ""
            opts += f'<option value="{opt}" {sel}>{opt}</option>'
            
        return f"""
        <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
        <script>
        window.doDownloadExcel = function() {{
            const link = document.createElement('a');
            link.href = "data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{xl_b64}";
            link.download = "laporan_fti.xlsx";
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }};
        
        window.doDownloadPdf = function() {{
            const element = document.querySelector('.vis-content');
            if (!element) return;
            
            // Sembunyikan panel kontrol sementara
            const ctrl = element.querySelector('.ctrl-panel');
            if (ctrl) ctrl.style.display = 'none';
            
            const opt = {{
              margin:       0.3,
              filename:     'Laporan_Prediksi_Mahasiswa_FTI.pdf',
              image:        {{ type: 'jpeg', quality: 0.98 }},
              html2canvas:  {{ scale: 2, useCORS: true, letterRendering: true }},
              jsPDF:        {{ unit: 'in', format: 'a4', orientation: 'portrait' }}
            }};
            
            // Ganti background ke putih untuk hasil PDF
            const oldBg = element.style.background;
            element.style.background = '#ffffff';
            element.style.padding = '10px';
            
            html2pdf().set(opt).from(element).save().then(() => {{
                // Kembalikan seperti semula
                if (ctrl) ctrl.style.display = 'flex';
                element.style.background = oldBg;
                element.style.padding = '28px 40px 52px';
            }});
        }};
        
        if (!window.__laporanJsInjected) {{
            // Listen for clicks on PDF and Excel buttons
            document.addEventListener('click', function(e) {{
                let btnPdf = e.target.closest('.btn-pdf');
                if (btnPdf) {{
                    e.preventDefault();
                    e.stopPropagation();
                    window.doDownloadPdf();
                    return;
                }}
                let btnExcel = e.target.closest('.btn-excel');
                if (btnExcel) {{
                    e.preventDefault();
                    e.stopPropagation();
                    window.doDownloadExcel();
                    return;
                }}
            }}, true);
            
            // Listen for changes on the Jenis Laporan dropdown
            document.addEventListener('change', function(e) {{
                let select = e.target.closest('.ctrl-select');
                if (select) {{
                    e.stopPropagation();
                    // Fix sandbox CORS blocking target=_top by using direct window.location.href
                    window.location.href = '/?logged_in=true&role={role}&page=Laporan&jenis=' + encodeURIComponent(select.value);
                }}
            }}, true);
            
            window.__laporanJsInjected = true;
        }}
        </script>
        <div class="ctrl-panel">
          <div class="ctrl-left">
            <label class="ctrl-label">Jenis Laporan</label>
            <select class="ctrl-select">
              {opts}
            </select>
          </div>
          <div class="ctrl-right">
            <button class="btn-pdf">&#128438; Download PDF</button>
            <button class="btn-excel">&#11123; Excel</button>
          </div>
        </div>
        """

    # ── section builders ──────────────────────────────────────────────────────
    def kpi_cards():
        if df.empty or latest is None:
            return ""
        chg_color = "#c0392b" if growth_avg < 0 else "#27ae60"
        proj_pct  = ((pred_next / int(latest[TARGET_COLUMN])) - 1) * 100 if int(latest[TARGET_COLUMN]) else 0
        growth_val = f"{growth_avg:+.1f}%" if growth_avg != 0 else "0.0%"
        return f"""
        <div class="kpi-grid">
          <div class="kpi-card kpi-blue">
            <div class="kpi-top">Total Mahasiswa {latest_yr}</div>
            <div class="kpi-val">{fmt_num(int(latest[TARGET_COLUMN]))}</div>
            <div class="kpi-sub">{growth_avg:+.1f}% dari {latest_yr-1}</div>
          </div>
          <div class="kpi-card kpi-orange">
            <div class="kpi-top">Prediksi {latest_yr+1}</div>
            <div class="kpi-val">{fmt_num(pred_next)}</div>
            <div class="kpi-sub">{proj_pct:+.1f}% proyeksi</div>
          </div>
          <div class="kpi-card kpi-red" style="grid-column:span 2;">
            <div class="kpi-top">Rata-Rata Pertumbuhan Per Tahun ({int(df['tahun'].min())}–{latest_yr})</div>
            <div class="kpi-val" style="color:white;font-size:32px;">{growth_val}</div>
            <div class="kpi-sub">{"Tren menurun" if growth_avg < 0 else "Tren positif"} berdasarkan data historis</div>
          </div>
        </div>"""

    def ringkasan_variabel():
        if df.empty or latest is None:
            return ""
        akr_lbl = AKREDITASI_MAP.get(int(latest["akreditasi"]), str(int(latest["akreditasi"])))
        rows = [
            ("Biaya Kuliah", fmt_currency(latest["biaya_kuliah"])),
            ("Kuota Beasiswa", fmt_num(latest["kuota_beasiswa"])),
            ("Akreditasi", akr_lbl),
            ("Jumlah Prodi", str(int(latest["jumlah_prodi"]))),
        ]
        cards = "".join(
            f'<div class="var-card"><div class="var-label">{html.escape(l)}</div>'
            f'<div class="var-val">{html.escape(v)}</div></div>'
            for l, v in rows
        )
        return f'<div class="var-grid">{cards}</div>'

    def eksekutif_section():
        if not temuan:
            return ""
        # Semua temuan pakai checklist ✔
        t_items = "".join(
            f'<div class="eks-item eks-temuan"><span class="eks-dot">&#10004;</span>'
            f'<span>{html.escape(t)}</span></div>'
            for t in temuan
        )
        r_items = "".join(
            f'<div class="eks-item eks-rek"><span class="eks-dot">&#9658;</span>'
            f'<span>{html.escape(r)}</span></div>'
            for r in rek
        )
        return f"""
        <div class="eks-panel">
          <div class="panel-title">Ringkasan Eksekutif</div>
          <div class="eks-grid">
            <div>
              <div class="eks-head">Temuan Utama</div>{t_items}
            </div>
            <div>
              <div class="eks-head">Rekomendasi Strategis</div>{r_items}
            </div>
          </div>
        </div>"""

    # ── konten per jenis ──────────────────────────────────────────────────────
    if df.empty:
        content = "<div class='empty-msg'>Data historis belum tersedia.</div>"

    elif jenis == "Komprehensif":
        content = f"""
        {control_panel()}
        {kpi_cards()}
        <div class="mid-grid">
          <div class="panel">
            <div class="panel-title">Tren Mahasiswa Baru &amp; Prediksi</div>
            {trend_img}
          </div>
          <div class="panel">
            <div class="panel-title">Ringkasan Variabel {latest_yr}</div>
            {ringkasan_variabel()}
          </div>
          <div class="panel">
            <div class="panel-title">Perbandingan Beasiswa &amp; Mahasiswa</div>
            {bar_img}
          </div>
        </div>
        {eksekutif_section()}"""

    elif jenis == "Ringkasan":
        content = f"""
        {control_panel()}
        {kpi_cards()}
        {eksekutif_section()}"""

    else:  # Prediksi Saja
        rows_html = "".join(
            f"<tr><td>{yr}</td><td>{fmt_num(v)}</td>"
            f"<td class='{'pred-tag' if yr > latest_yr else 'aktual-tag'}'>{'Prediksi' if yr > latest_yr else 'Aktual'}</td></tr>"
            for yr, v in pred_series
        )
        kpi_pred2 = ""
        if pred_next2 > 0:
            kpi_pred2 = f"""
          <div class="kpi-card kpi-blue">
            <div class="kpi-top">Prediksi {latest_yr+2}</div>
            <div class="kpi-val">{fmt_num(pred_next2)}</div>
            <div class="kpi-sub">2 tahun ke depan</div>
          </div>
            """
        
        content = f"""
        {control_panel()}
        <div class="kpi-grid">
          <div class="kpi-card kpi-orange">
            <div class="kpi-top">Prediksi {latest_yr+1}</div>
            <div class="kpi-val">{fmt_num(pred_next)}</div>
            <div class="kpi-sub">Tahun depan</div>
          </div>
          {kpi_pred2}
        </div>
        <div class="mid-grid">
          <div class="panel" style="grid-column:1/-1;">
            <div class="panel-title">Tren Mahasiswa Baru &amp; Prediksi</div>
            {trend_img}
          </div>
        </div>
        <div class="panel" style="margin-bottom:24px;">
          <div class="panel-title">Tabel Prediksi Mahasiswa Baru</div>
          <table class="pred-table">
            <tr><th>Tahun</th><th>Jumlah Mahasiswa</th><th>Status</th></tr>
            {rows_html}
          </table>
        </div>
        {eksekutif_section()}"""

    # ── full HTML ─────────────────────────────────────────────────────────────
    page_html = dedent(f"""
    <style>
    @media print {{
        .vis-sidebar, .vis-header, .ctrl-panel, [data-testid="stSidebar"], [data-testid="stHeader"], button {{ display: none !important; }}
        .vis-shell {{ grid-template-columns: 1fr !important; position: static !important; overflow: visible !important; height: auto !important; }}
        .vis-content {{ padding: 0 !important; }}
        .kpi-grid, .mid-grid, .eks-grid {{ page-break-inside: avoid; }}
        body, .stApp, [data-testid="stAppViewContainer"] {{ background: white !important; }}
    }}
    [data-testid="stHeader"],[data-testid="stSidebar"]{{display:none;}}
    html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{{margin:0!important;padding:0!important;}}
    .stApp{{background:#e3e7eb;}}
    .block-container{{max-width:100%!important;padding:0!important;margin:0!important;}}

    .vis-shell{{
      position:fixed;inset:0;z-index:999;height:100vh;overflow-y:auto;
      display:grid;grid-template-columns:280px 1fr;
      background:#e3e7eb;color:#123047;font-family:Arial,sans-serif;
    }}
    .vis-sidebar{{background:#4a9498;color:white;padding:36px 22px 28px;display:flex;flex-direction:column;min-height:100vh;}}
    .brand-title{{font-size:21px;font-weight:800;line-height:1.2;}}
    .brand-subtitle{{font-size:13px;font-weight:700;margin-top:6px;padding-bottom:18px;border-bottom:1px solid rgba(255,255,255,.25);}}
    .side-menu{{margin-top:24px;display:grid;gap:16px;}}
    .side-item{{color:white;text-decoration:none;display:flex;align-items:center;gap:13px;padding:11px 10px;border-radius:4px;font-size:16px;}}
    .side-item.active{{background:#e9c91d;}}
    .side-icon{{width:24px;height:24px;flex:0 0 24px;display:inline-flex;align-items:center;justify-content:center;}}
    .side-icon img{{width:23px;height:23px;object-fit:contain;}}
    .sidebar-user{{margin-top:auto;padding:16px 8px 0;border-top:1px solid rgba(255,255,255,.25);color:rgba(255,255,255,.6);font-size:16px;line-height:1.35;}}
    .logout-link{{margin-top:220px;color:white;text-decoration:none;display:flex;align-items:center;gap:12px;font-size:16px;}}

    .vis-header{{height:84px;background:white;display:flex;align-items:center;padding:0 28px;box-shadow:0 2px 6px rgba(0,0,0,.25);}}
    .vis-header h1{{margin:0;color:#4a9498;font-size:28px;line-height:1.05;}}
    .vis-header h1 span{{display:block;font-size:17px;margin-top:5px;font-weight:800;}}
    .vis-content{{padding:28px 40px 52px;}}

    .ctrl-panel {{ background:#f2f5f7; border:1px solid #e0e8ea; padding:14px 20px; border-radius:6px; display:flex; justify-content:space-between; align-items:flex-end; margin-bottom:24px; }}
    .ctrl-left {{ display:flex; flex-direction:column; gap:6px; flex:1; max-width:350px; }}
    .ctrl-label {{ font-size:13px; font-weight:700; color:#52666d; }}
    .ctrl-select {{ padding:9px 12px; border:1px solid #cfd8dc; border-radius:4px; font-size:14px; color:#123047; outline:none; cursor:pointer; background:white; font-weight:600; box-shadow:0 1px 2px rgba(0,0,0,.05); }}
    .ctrl-right {{ display:flex; gap:12px; align-items:center; }}
    .btn-pdf {{ background:#e74c3c; color:white; border:none; padding:10px 20px; border-radius:4px; font-size:14px; font-weight:700; cursor:pointer; display:flex; align-items:center; gap:8px; box-shadow:0 2px 4px rgba(231,76,60,.3); transition:background 0.2s; }}
    .btn-pdf:hover {{ background:#c0392b; }}
    .btn-excel {{ background:#4a9498; color:white; text-decoration:none; padding:10px 20px; border-radius:4px; font-size:14px; font-weight:700; display:flex; align-items:center; gap:8px; box-shadow:0 2px 4px rgba(74,148,152,.3); transition:background 0.2s; }}
    .btn-excel:hover {{ background:#3a7d80; }}

    .kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin-bottom:24px;}}
    .kpi-card{{padding:16px 18px;border-radius:6px;color:white;box-shadow:0 3px 8px rgba(0,0,0,.2);}}
    .kpi-blue{{background:#2980b9;}}.kpi-orange{{background:#e67e22;}}.kpi-teal{{background:#4a9498;}}.kpi-red{{background:#c0392b;}}
    .kpi-top{{font-size:13px;font-weight:700;opacity:.9;margin-bottom:6px;}}
    .kpi-val{{font-size:28px;font-weight:800;line-height:1;}}
    .kpi-sub{{font-size:11px;margin-top:5px;opacity:.8;}}

    .mid-grid{{display:grid;grid-template-columns:1.5fr 0.8fr 1.5fr;gap:20px;margin-bottom:24px;}}
    .panel{{background:white;box-shadow:0 3px 8px rgba(0,0,0,.2);padding:16px 18px 20px;border-radius:4px;overflow-x:auto;}}
    .panel-title{{color:#4a9498;font-size:16px;font-weight:800;margin-bottom:12px;}}

    .var-grid{{display:grid;grid-template-columns:1fr;gap:10px;}}
    .var-card{{background:#60aeb4;color:white;padding:10px 14px;border-radius:4px;box-shadow:0 2px 5px rgba(0,0,0,.2);}}
    .var-label{{font-size:12px;opacity:.85;font-weight:700;}}
    .var-val{{font-size:18px;font-weight:800;margin-top:2px;}}

    .eks-panel{{background:white;box-shadow:0 3px 8px rgba(0,0,0,.2);padding:20px 24px 28px;border-radius:4px;overflow-x:auto;}}
    .eks-grid{{display:grid;grid-template-columns:1fr 1fr;gap:32px;margin-top:12px;}}
    .eks-head{{font-size:14px;font-weight:800;color:#4a9498;margin-bottom:10px;border-bottom:2px solid #4a9498;padding-bottom:4px;}}
    .eks-item{{display:flex;gap:10px;margin-bottom:10px;font-size:13px;line-height:1.5;}}
    .eks-dot{{flex:0 0 18px;font-size:15px;}}
    .eks-temuan .eks-dot{{color:#27ae60;}}.eks-rek .eks-dot{{color:#4a9498;}}

    .pred-table{{width:100%;border-collapse:collapse;font-size:13px;}}
    .pred-table th{{background:#4a9498;color:white;padding:8px 12px;text-align:left;}}
    .pred-table td{{padding:7px 12px;border-bottom:1px solid #dde;}}
    .pred-tag{{color:#e67e22;font-weight:700;}}.aktual-tag{{color:#4a9498;font-weight:700;}}
    .empty-msg{{background:white;padding:28px;color:#52666d;font-size:15px;font-weight:700;border-radius:4px;}}

    @media (max-width: 768px) {{
        .vis-shell {{ grid-template-columns: 1fr; display: flex; flex-direction: column; }}
        .vis-sidebar {{ min-height: auto; padding: 20px; }}
        .logout-link {{ margin-top: 40px; }}
        .vis-content {{ padding: 20px; }}
        .kpi-grid, .mid-grid, .eks-grid {{ grid-template-columns: 1fr; gap: 16px; }}
        .ctrl-panel {{ flex-direction: column; align-items: flex-start; gap: 16px; }}
        .pred-table {{ display: block; overflow-x: auto; white-space: nowrap; }}
    }}
    </style>

    <div class="vis-shell">
      <aside class="vis-sidebar">
        <div class="brand-title">Prediksi Mahasiswa</div>
        <div class="brand-subtitle">Fakultas Teknologi Informasi</div>
        <nav class="side-menu">
          <a class="side-item" href="/?logged_in=true&role={role}&page=Dashboard&_t={int(time.time())}" target="_self">
            <span class="side-icon">{icon_b64("dashboard")}</span> Dashboard Utama</a>
          {extra_menu}
          <a class="side-item active" href="/?logged_in=true&role={role}&page=Laporan&_t={int(time.time())}" target="_self">
            <span class="side-icon">{icon_b64("report")}</span> Visualisasi dan Laporan</a>
        </nav>
        <div class="sidebar-user">{html.escape(active_name)}<br>{html.escape(role_label)}</div>
        <a class="logout-link" href="/?logout=true" target="_self">
          <span class="side-icon">{icon_b64("logout")}</span> Log out</a>
      </aside>

      <main>
        <header class="vis-header">
          <h1>Visualisasi dan Laporan<span>FTI UNSAP</span></h1>
        </header>
        <section class="vis-content">
          {content}
        </section>
      </main>
    </div>
    """)

    st.html(page_html, unsafe_allow_javascript=True)