import streamlit as st
import psutil
import os

def show_system_metrics(user_role):
    if user_role != "exec":
        return

    process = psutil.Process(os.getpid())
    mem_bytes = process.memory_info().rss
    mem_mb = mem_bytes / (1024 * 1024)
    cpu_percent = process.cpu_percent(interval=0.5)

    st.sidebar.markdown("## 🔒 Exec System Monitor")
    st.sidebar.markdown(f"🧠 **Memory Usage:** {mem_mb:.2f} MB")
    st.sidebar.markdown(f"🧮 **CPU Usage:** {cpu_percent:.2f}%")