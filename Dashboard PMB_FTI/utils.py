import streamlit as st

# =====================================================
# SIDEBAR MENU
# =====================================================

def sidebar_menu(role):

    with st.sidebar:

        st.title("🎓 PMB FTI")

        st.write("---")

        st.write(
            f"Login sebagai: "
            f"**{st.session_state.nama}**"
        )

        st.write(
            f"Role: **{role.upper()}**"
        )

        st.write("---")

        # =================================================
        # MENU ADMIN
        # =================================================

        if role == "admin":

            menu = st.radio(
                "Navigasi Menu",
                [
                    "Dashboard",
                    "Data Historis",
                    "Prediksi",
                    "Evaluasi",
                    "Laporan",
                    "Manajemen Akun",
                    "Logout"
                ]
            )

        # =================================================
        # MENU USER
        # =================================================

        else:

            menu = st.radio(
                "Navigasi Menu",
                [
                    "Dashboard",
                    "Laporan",
                    "Logout"
                ]
            )

        return menu