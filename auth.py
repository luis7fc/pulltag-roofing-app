import streamlit as st
import requests
import os
import bcrypt

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def login():
    if "user" in st.session_state:
        return st.session_state["user"]

    st.title("🔐 Start Session")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    login_btn = st.button("Enter")

    if login_btn and username and password:
        # Only fetch user by username
        url = f"{SUPABASE_URL}/rest/v1/users?username=eq.{username}&select=username,password,role"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        r = requests.get(url, headers=headers)

        if r.status_code == 200 and r.json():
            user = r.json()[0]
            stored_hash = user["password"]

            if bcrypt.checkpw(password.encode(), stored_hash.encode()):
                st.session_state["user"] = user
                return user
            else:
                st.error("Wrong Password.")
        else:
            st.error("Invalid username.")
    return None
