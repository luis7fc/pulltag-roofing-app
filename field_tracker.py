import streamlit as st

# === LOAD ===
def _load_from_supabase(supabase, username, tab, key):
    response = supabase.table("drafts").select("value")\
        .eq("username", username).eq("tab", tab).eq("key", key)\
        .limit(1).execute()
    return response.data[0]["value"] if response.data else ""

# === SAVE ===
def _save_to_supabase(supabase, username, tab, key, value):
    supabase.table("drafts").upsert({
        "username": username,
        "tab": tab,
        "key": key,
        "value": value
    }).execute()

# === TRACKED INPUT ===
def tracked_input(label, key, username, tab, supabase, default="", **kwargs):
    if key not in st.session_state:
        st.session_state[key] = _load_from_supabase(supabase, username, tab, key) or default

    value = st.text_input(label, value=st.session_state[key], key=key, **kwargs)

    if value != st.session_state[key]:
        st.session_state[key] = value
        _save_to_supabase(supabase, username, tab, key, value)

    return value

# === TRACKED TEXT AREA ===
def tracked_text_area(label, key, username, tab, supabase, default="", **kwargs):
    if key not in st.session_state:
        st.session_state[key] = _load_from_supabase(supabase, username, tab, key) or default

    value = st.text_area(label, value=st.session_state[key], key=key, **kwargs)

    if value != st.session_state[key]:
        st.session_state[key] = value
        _save_to_supabase(supabase, username, tab, key, value)

    return value

# === TRACKED SELECTBOX ===
def tracked_selectbox(label, options, key, username, tab, supabase, default=None, **kwargs):
    if key not in st.session_state:
        stored = _load_from_supabase(supabase, username, tab, key)
        st.session_state[key] = stored if stored in options else default or options[0]

    value = st.selectbox(label, options, index=options.index(st.session_state[key]), key=key, **kwargs)

    if value != st.session_state[key]:
        st.session_state[key] = value
        _save_to_supabase(supabase, username, tab, key, value)

    return value
