import base64
from pathlib import Path

import streamlit as st


def image_to_base64(path):
    with open(path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode()


def show_landing():
    logo_path = Path(__file__).parent.parent / "logo_fti.png"
    logo_base64 = image_to_base64(logo_path)

    st.html(f"""
<style>
.stApp {{
    background: linear-gradient(135deg, #4A8E93, #C4C96B);
}}

[data-testid="stHeader"] {{
    display: none;
}}

.block-container {{
    padding-top: 0 !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
    max-width: 100% !important;
}}

.navbar {{
    width: 100%;
    background: white;
    padding: 22px 56px;
    border-radius: 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-sizing: border-box;
}}

.logo-area {{
    display: flex;
    align-items: center;
    gap: 22px;
}}

.logo-area img {{
    width: 80px;
    height: 80px;
    object-fit: contain;
}}

.logo-area h1 {{
    margin: 0;
    color: #0f172a;
    font-size: 32px;
    font-weight: 800;
}}

.login-btn {{
    background: #FFC107;
    padding: 16px 38px;
    border-radius: 14px;
    text-decoration: none;
    color: white !important;
    font-weight: 800;
    font-size: 18px;
}}

.landing-content {{
    padding: 90px 5rem 0 5rem;
}}

.hero-title {{
    color: white;
    font-size: 86px;
    font-weight: 800;
    line-height: 1.2;
}}

.hero-subtitle {{
    margin-top: 36px;
    color: white;
    font-size: 28px;
    line-height: 1.9;
    width: 72%;
}}

.stats {{
    margin-top: 90px;
    display: flex;
    gap: 24px;
}}

.stat-card {{
    flex: 1;
    background: rgba(255, 255, 255, 0.15);
    border-radius: 20px;
    padding: 34px 38px;
    color: white;
    backdrop-filter: blur(10px);
}}

.stat-card h2 {{
    font-size: 40px;
    margin: 0 0 12px 0;
    font-weight: 800;
}}

.stat-card p {{
    font-size: 20px;
    margin: 0;
}}
</style>

<div class="navbar">
    <div class="logo-area">
        <img src="data:image/png;base64,{logo_base64}">
        <h1>SISTEM PREDIKSI PMB FTI UNSAP</h1>
    </div>

    <a class="login-btn" href="/?page=Login" target="_self">LOGIN</a>
</div>

<div class="landing-content">
    <div class="hero-title">
        SISTEM PREDIKSI<br>
        PMB FTI UNSAP
    </div>

    <div class="hero-subtitle">
        Sistem pendukung keputusan berbasis Machine Learning menggunakan algoritma Random Forest Regressor untuk
        membantu manajemen FTI memproyeksikan tren pendaftar di masa depan.
    </div>

    <div class="stats">
        <div class="stat-card">
            <h2>99.87%</h2>
            <p>Akurasi Model</p>
        </div>

        <div class="stat-card">
            <h2>5 Tahun</h2>
            <p>Data Historis</p>
        </div>

        <div class="stat-card">
            <h2>4 Variabel</h2>
            <p>Prediktor</p>
        </div>

        <div class="stat-card">
            <h2>Random Forest</h2>
            <p>Algoritma</p>
        </div>
    </div>
</div>
""")