# logs.py
import streamlit as st
from datetime import datetime
import json
import os

# Initialize session state for logs
if "logs" not in st.session_state:
    st.session_state["logs"] = []

# Maximum number of logs to keep in memory
MAX_LOGS = 1000

# File for persistent logs
LOG_FILE = "app_logs.json"

def load_logs_from_file():
    """Load logs from a file if it exists"""
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r") as f:
                logs = json.load(f)
                return logs[-MAX_LOGS:] if logs else []
    except Exception:
        # If there's an error loading logs, start fresh
        pass
    return []

def save_logs_to_file():
    """Save current logs to a file"""
    try:
        with open(LOG_FILE, "w") as f:
            json.dump(st.session_state["logs"], f)
    except Exception as e:
        # If we can't save logs, just continue
        print(f"Error saving logs: {str(e)}")
        pass

def log_message(message, level="INFO"):
    """Add a log message with timestamp and level"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Add an emoji based on the log level
    if level == "ERROR":
        emoji = "❌"
    elif level == "WARNING":
        emoji = "⚠️"
    elif level == "SUCCESS":
        emoji = "✅"
    else:
        emoji = "ℹ️"
    
    full_msg = f"[{timestamp}] {emoji} {message}"
    
    # Insert at the beginning to show newest logs first
    st.session_state["logs"].insert(0, full_msg)
    
    # Keep logs under the limit
    if len(st.session_state["logs"]) > MAX_LOGS:
        st.session_state["logs"] = st.session_state["logs"][:MAX_LOGS]
    
    # Attempt to save logs to file
    save_logs_to_file()

def get_logs():
    """Get all current logs as a string"""
    if not st.session_state["logs"]:
        return "No logs yet."
    return "\n".join(st.session_state["logs"])

def clear_logs():
    """Clear all logs"""
    st.session_state["logs"] = []
    
    # Also clear the log file
    try:
        if os.path.exists(LOG_FILE):
            os.remove(LOG_FILE)
    except Exception:
        pass

# Load logs from file when module is imported
if not st.session_state["logs"]:
    st.session_state["logs"] = load_logs_from_file()
