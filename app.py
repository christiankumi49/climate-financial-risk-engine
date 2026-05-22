import streamlit as st
import sqlite3
import os
import hashlib
from datetime import datetime

DB_PATH = os.path.abspath("climate_risk_vault.db")

# =========================
# 🔒 DATABASE MANAGER
# =========================
class DatabaseWorkspaceManager:
    def __enter__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        return self.conn.cursor()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()

# =========================
# 🔐 SECURITY
# =========================
def generate_salt():
    return os.urandom(16).hex()

def hash_password(password, salt):
    return hashlib.pbkdf2_hmac(
        'sha256', password.encode(), bytes.fromhex(salt), 100000
    ).hex()

# =========================
# 🏗️ INIT DB
# =========================
def init_db():
    with DatabaseWorkspaceManager() as cursor:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            salt TEXT,
            password_hash TEXT,
            role TEXT,
            org_id TEXT
        )
        """)

        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            salt = generate_salt()
            cursor.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?)",
                (
                    "admin",
                    salt,
                    hash_password("admin123", salt),
                    "Admin",
                    "ORG_1"
                )
            )

# =========================
# 🔑 AUTH FUNCTION (FIXED)
# =========================
def process_user_authentication(username, password):
    if not username or not password:
        return None

    with DatabaseWorkspaceManager() as cursor:
        cursor.execute(
            "SELECT salt, password_hash, role, org_id FROM users WHERE username=?",
            (username.strip(),)
        )
        user = cursor.fetchone()

    if not user:
        return None

    salt, stored_hash, role, org_id = user
    if hash_password(password.strip(), salt) == stored_hash:
        return {"role": role, "org_id": org_id}

    return None

# =========================
# 🚀 APP START
# =========================
init_db()

st.title("Climate Risk Platform")

if "user" not in st.session_state:
    st.session_state.user = None

if not st.session_state.user:
    st.subheader("Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        user = process_user_authentication(username, password)

        if user:
            st.session_state.user = user
            st.success("Login successful")
            st.rerun()
        else:
            st.error("Invalid credentials")

else:
    st.success(f"Logged in as {st.session_state.user['role']}")
    
    if st.button("Logout"):
        st.session_state.user = None
        st.rerun()

    st.write("🚀 System running stable")
