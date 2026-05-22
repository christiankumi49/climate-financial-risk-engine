import streamlit as st
import requests
import pandas as pd
import sqlite3
import hashlib
import os
import time
from datetime import datetime, timedelta

# =========================
# ⚙️ CONFIG
# =========================
DB_PATH = os.path.abspath("climate_risk_vault.db")
st.set_page_config(page_title="Climate Risk Platform", layout="wide")

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
# 🏗️ INIT DB (SAFE)
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

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS farm_clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT,
            cluster_name TEXT,
            latitude REAL,
            longitude REAL,
            crop_type TEXT,
            acres REAL,
            expected_yield REAL,
            market_price REAL
        )
        """)

        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            users = [
                ("admin", "admin123", "Admin", "ORG_1"),
                ("manager", "manager123", "Manager", "ORG_1")
            ]
            for u, p, r, o in users:
                salt = generate_salt()
                cursor.execute(
                    "INSERT INTO users VALUES (?, ?, ?, ?, ?)",
                    (u, salt, hash_password(p, salt), r, o)
                )

init_db()

# =========================
# 🔑 AUTH (FIXED)
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
        return {"username": username, "role": role, "org_id": org_id}

    return None

# =========================
# 🌦️ WEATHER ENGINE
# =========================
def fetch_weather(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,precipitation_sum&forecast_days=7"
    try:
        res = requests.get(url, timeout=5)
        data = res.json()["daily"]
        return pd.DataFrame({
            "temp": data["temperature_2m_max"],
            "rain": data["precipitation_sum"]
        })
    except:
        return None

# =========================
# 📊 RISK ENGINE
# =========================
def compute_risk(df, asset_value):
    if df is None:
        return 0

    rain = df["rain"].sum()
    temp = df["temp"].max()

    risk = 0
    if rain > 40:
        risk += asset_value * 0.3
    if temp > 33:
        risk += asset_value * 0.2

    return risk

# =========================
# 🚀 APP
# =========================
st.title("🌍 Climate Financial Risk Intelligence")

if "user" not in st.session_state:
    st.session_state.user = None

# ---------- LOGIN ----------
if not st.session_state.user:
    st.subheader("Login")

    u = st.text_input("Username")
    p = st.text_input("Password", type="password")

    if st.button("Login"):
        user = process_user_authentication(u, p)
        if user:
            st.session_state.user = user
            st.rerun()
        else:
            st.error("Invalid credentials")

# ---------- DASHBOARD ----------
else:
    st.success(f"Logged in as {st.session_state.user['username']}")

    if st.button("Logout"):
        st.session_state.user = None
        st.rerun()

    # Load clusters
    with DatabaseWorkspaceManager() as cursor:
        cursor.execute("SELECT * FROM farm_clusters WHERE org_id=?", (st.session_state.user["org_id"],))
        df = pd.DataFrame(cursor.fetchall(), columns=[c[0] for c in cursor.description])

    total_risk = 0

    if not df.empty:
        for _, row in df.iterrows():
            asset = row["acres"] * row["expected_yield"] * row["market_price"]
            weather = fetch_weather(row["latitude"], row["longitude"])
            risk = compute_risk(weather, asset)
            total_risk += risk

        st.metric("💰 Total Risk Exposure", f"GHS {total_risk:,.2f}")

        st.map(df[["latitude", "longitude"]])

    else:
        st.info("No farm data available.")
