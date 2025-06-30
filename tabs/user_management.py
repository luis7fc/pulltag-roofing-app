import streamlit as st
import bcrypt
import os
from supabase import create_client, Client
from field_tracker import tracked_input, tracked_text_area, tracked_selectbox

def run():
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    st.title("👤 User Management")

    tab = "user_management"

    @st.cache_data(ttl=60)
    def load_users():
        result = supabase.table("users").select("*").execute()
        return result.data if result.data else []

    users = load_users()
    usernames = [u["username"] for u in users]

    with st.expander("🔍 View Current Users"):
        st.dataframe(
            [{k: u[k] for k in ["username", "role"]} for u in users],
            use_container_width=True
        )

    action = st.radio("Select Action", ["➕ Add New User", "🔧 Update User", "❌ Delete User"])
    st.markdown("---")

    if action == "➕ Add New User":
        st.subheader("Add New User")
        new_username = tracked_input("New Username", key="new_username", username=st.session_state.get("username", "admin"), tab=tab).strip()
        new_password = tracked_input("New Password", key="new_password", username=st.session_state.get("username", "admin"), tab=tab, type="password")
        new_role = tracked_selectbox("Role", ["admin", "super", "warehouse", "exec"], key="new_user_role", username=st.session_state.get("username", "admin"), tab=tab)

        if st.button("Create User"):
            if not new_username or not new_password:
                st.warning("Please enter a username and password.")
            elif new_username in usernames:
                st.error("Username already exists.")
            elif len(new_password) < 6:
                st.warning("Password must be at least 6 characters.")
            else:
                hashed_pw = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
                try:
                    supabase.table("users").insert({
                        "username": new_username,
                        "password": hashed_pw,
                        "role": new_role
                    }).execute()
                    st.success(f"User '{new_username}' added.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to create user: {str(e)}")

    elif action == "🔧 Update User":
        st.subheader("Update User Password / Role")
        if not usernames:
            st.info("No users available to update.")
        else:
            edit_user = tracked_selectbox("Select user to update", usernames, key="edit_user", username=st.session_state.get("username", "admin"), tab=tab)
            new_pw = tracked_input("New Password", key="edit_user_pw", username=st.session_state.get("username", "admin"), tab=tab, type="password")
            new_role_update = tracked_selectbox("New Role", ["admin", "super", "warehouse", "exec"], key="edit_user_role", username=st.session_state.get("username", "admin"), tab=tab)

            if st.button("Update User"):
                updates = {}
                if new_pw:
                    if len(new_pw) < 6:
                        st.warning("Password must be at least 6 characters.")
                    else:
                        updates["password"] = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
                if new_role_update:
                    updates["role"] = new_role_update

                if updates:
                    try:
                        supabase.table("users").update(updates).eq("username", edit_user).execute()
                        st.success(f"User '{edit_user}' updated.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Update failed: {str(e)}")
                else:
                    st.info("No changes submitted.")

    elif action == "❌ Delete User":
        st.subheader("Delete User")
        if not usernames:
            st.info("No users available to delete.")
        else:
            user_to_delete = tracked_selectbox("Select user to delete", usernames, key="delete_user", username=st.session_state.get("username", "admin"), tab=tab)
            current_username = st.session_state.get("username")

            if user_to_delete == current_username:
                st.warning("You cannot delete your own account while logged in.")
            else:
                if st.button("Confirm Delete"):
                    try:
                        supabase.table("users").delete().eq("username", user_to_delete).execute()
                        st.success(f"User '{user_to_delete}' deleted.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to delete user: {str(e)}")
