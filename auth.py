import streamlit as st
import requests
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def login():
    if "user" in st.session_state:
        return st.session_state["user"]

    st.title("🔐 Iniciar sesión")
    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")
    login_btn = st.button("Entrar")

    if login_btn and username and password:
        url = f"{SUPABASE_URL}/rest/v1/users?username=eq.{username}&password=eq.{password}"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        r = requests.get(url, headers=headers)
        if r.status_code == 200 and r.json():
            user = r.json()[0]
            st.session_state["user"] = user
            return user
        else:
            st.error("Invalid credentials.")
    return None
