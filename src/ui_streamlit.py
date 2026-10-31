"""Optional Streamlit UI for quick demo (install streamlit to use).

Run: `streamlit run src/ui_streamlit.py`
"""
import streamlit as st
import requests
import os

API_URL = os.getenv("AGENT_API_URL", "http://localhost:8000/run")

st.title("Personal Task Automation Agent — Demo UI")

cmd = st.text_area("Enter a command", "Find me top 5 internships in Bangalore, summarize them, and email the summary to me.")
email = st.text_input("Optional email to send results to")

if st.button("Run"):
    payload = {"command": cmd, "email": email}
    with st.spinner("Running plan..."):
        resp = requests.post(API_URL, json=payload, timeout=120)
        if resp.status_code == 200:
            data = resp.json()
            st.subheader("Plan")
            st.json(data.get("plan"))
            st.subheader("Logs")
            for ln in data.get("logs", []):
                st.text(ln)
        else:
            st.error(f"API error: {resp.status_code} - {resp.text}")
