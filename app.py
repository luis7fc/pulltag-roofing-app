import streamlit as st
from auth import login
from system_monitor import show_system_metrics

from tabs import (
    community_creation,
    budget_upload,
    reporting,
    super_request,
    warehouse_kitting,
    backorder_kitting,
    user_management,
    items_editor,
    roof_editor,
)

TABS_BY_ROLE = {
    "admin": {
        "🏘️ Community Creation": community_creation.show,
        "📄 Budget Upload": budget_upload.show,
        "📊 Reporting & Sage Export": reporting.show,
    },
    "super": {
        "📦 Super Request": super_request.show,
    },
    "warehouse": {
        "🛠️ Warehouse Kitting": warehouse_kitting.show,
        "🔁 Backorder Kitting": backorder_kitting.show,
    },
    "exec": {
        "🏘️ Community Creation": community_creation.show,
        "📄 Budget Upload": budget_upload.show,
        "📊 Reporting & Sage Export": reporting.show,
        "📦 Super Request": super_request.show,
        "🛠️ Warehouse Kitting": warehouse_kitting.show,
        "🔁 Backorder Kitting": backorder_kitting.show,
        "👤 User Management": user_management.show,
        "🧾 Items Master Editor": items_editor.show,
        "🏠 Roof Types Editor": roof_editor.show,
    }
}

def main():
    user = login()
    if not user:
        st.stop()

    st.sidebar.markdown(f"**Logged in as:** `{user['username']}` ({user['role']})")

    tab_map = TABS_BY_ROLE.get(user['role'], {})
    tab_names = list(tab_map.keys())
    show_system_metrics(user['role'])
    selected_tab = st.sidebar.radio("Navegación", tab_names)
    tab_map[selected_tab]()

if __name__ == "__main__":
    main()
