# --- Supabase setup ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Fetch and sanitize users
users = supabase.table("users").select("username,password,role").execute().data or []

credentials = {
    "usernames": {
        u["username"]: {
            "name": u["username"],
            "password": (u["password"] or "").replace("\n", "").strip(),
            "role": (u["role"] or "").strip(),
        }
        for u in users
    }
}

st.write("🔐 Loaded credentials:", credentials)

# --- Authenticator setup ---
authenticator = stauth.Authenticate(
    credentials,
    cookie_name="roofing_auth",
    key=os.getenv("AUTH_COOKIE_KEY", "fallback"),
    cookie_expiry_days=30,
)

# Render login form and handle authentication
login_result = authenticator.login("main", "Login")

if login_result is not None:
    name, auth_status, username = login_result
else:
    st.error("Login failed to load. Check credentials format or Supabase response.")
    st.stop()

# Handle result of login
if auth_status is False:
    st.error("Incorrect username or password.")
    st.stop()
elif auth_status is None:
    st.warning("Please enter your credentials.")
    st.stop()
