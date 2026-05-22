import streamlit as st
import requests
import pandas as pd
import sqlite3
import hashlib
import os
import json
import logging
from logging.handlers import RotatingFileHandler
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
from datetime import datetime, timedelta

# Configure Enterprise Page Environment
st.set_page_config(page_title="Climate Financial Risk Intelligence Platform (V3.5 Pro)", layout="wide")

# ==========================================
# 🛑 LAYER 0: PRODUCTION ROTATING LOGGING SYSTEM
# ==========================================
def initialize_production_logger():
    logger = logging.getLogger("CRIP_PROD_ENGINE")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        file_handler = RotatingFileHandler(
            "crip_production.log", 
            maxBytes=5 * 1024 * 1024, 
            backupCount=3,
            encoding="utf-8"
        )
        log_format = logging.Formatter(
            '[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(log_format)
        logger.addHandler(file_handler)
    return logger

system_logger = initialize_production_logger()

# ==========================================
# 💾 LAYER 1: HARDENED THREAD-SAFE PERSISTENCE INTERFACES
# ==========================================
class DatabaseWorkspaceManager:
    """Provides automated context management and thread-safe connection pooling parameters."""
    def __init__(self, db_path="climate_risk_vault.db"):
        self.db_path = db_path
        self.conn = None

    def __enter__(self):
        # FIX: check_same_thread=False prevents Streamlit multi-session context exceptions
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=15.0)
        return self.conn.cursor()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.conn.rollback()
            system_logger.error(f"Database Transaction Rolled Back. Exception: {str(exc_val)}")
        else:
            self.conn.commit()
        self.conn.close()

def generate_dynamic_salt():
    return os.urandom(16).hex()

def secure_hash_pbkdf2(password, salt_hex):
    salt = bytes.fromhex(salt_hex)
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000).hex()

def init_hardened_db():
    with DatabaseWorkspaceManager() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY, salt_hex TEXT, password_hash TEXT, role TEXT, org_id TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS farm_clusters (
                id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT, cluster_name TEXT,
                latitude REAL, longitude REAL, crop_type TEXT, acres REAL, expected_yield REAL, market_price REAL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS weather_cache (
                coordinate_key TEXT PRIMARY KEY, timestamp TEXT, json_payload TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_risk_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_date TEXT, org_id TEXT,
                aggregate_exposure REAL, active_threat_count INTEGER, UNIQUE(snapshot_date, org_id)
            )
        """)
        
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            users_to_seed = [
                ("executive_lead", "gh_exec_2026", "Executive / Investor", "ORG_COCOA_CORP"),
                ("field_manager_osei", "gh_farm_2026", "Farm Manager", "ORG_COCOA_CORP"),
                ("system_admin_kumi", "gh_admin_2026", "System Admin", "ORG_KUMI_AGRI_GLOBAL")
            ]
            for username, plain_pass, role, org_id in users_to_seed:
                user_salt = generate_dynamic_salt()
                pwd_hash = secure_hash_pbkdf2(plain_pass, user_salt)
                cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)", (username, user_salt, pwd_hash, role, org_id))
                
        cursor.execute("SELECT COUNT(*) FROM farm_clusters")
        if cursor.fetchone()[0] == 0:
            base_clusters = [
                ("ORG_KUMI_AGRI_GLOBAL", "Kumasi Cluster (Ashanti Region)", 6.69, -1.62, "Maize", 1200.0, 4.5, 450.0),
                ("ORG_KUMI_AGRI_GLOBAL", "Koforidua Cluster (Eastern Region)", 6.09, -0.26, "Rice", 850.0, 3.8, 600.0),
                ("ORG_COCOA_CORP", "Sefwi Wiawso Cluster (Western North)", 6.16, -2.48, "Cocoa", 2500.0, 1.2, 12500.0)
            ]
            cursor.executemany("INSERT INTO farm_clusters (org_id, cluster_name, latitude, longitude, crop_type, acres, expected_yield, market_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", base_clusters)

init_hardened_db()

# ==========================================
# 🛰️ LAYER 2: TELEMETRY INGESTION WITH TRUE MODEL DIVERSITY
# ==========================================
def save_to_local_cache(lat, lon, df):
    coord_key = f"{lat:.2f}_{lon:.2f}"
    json_str = df.to_json(date_format='iso')
    with DatabaseWorkspaceManager() as cursor:
        cursor.execute("""
            INSERT INTO weather_cache (coordinate_key, timestamp, json_payload)
            VALUES (?, ?, ?)
            ON CONFLICT(coordinate_key) DO UPDATE SET timestamp=?, json_payload=?
        """, (coord_key, datetime.now().isoformat(), json_str, datetime.now().isoformat(), json_str))

def fetch_from_local_cache(lat, lon):
    coord_key = f"{lat:.2f}_{lon:.2f}"
    with DatabaseWorkspaceManager() as cursor:
        cursor.execute("SELECT timestamp, json_payload FROM weather_cache WHERE coordinate_key=?", (coord_key,))
        row = cursor.fetchone()
    
    if row:
        cache_time = datetime.fromisoformat(row[0])
        if datetime.now() - cache_time < timedelta(hours=3):
            return pd.read_json(row[1]), True
        return pd.read_json(row[1]), False
    return None, False

def fetch_weather_intelligence(lat, lon):
    # FIX: Redesigned fallback route to parse NOAA GFS model data rather than hitting the same primary endpoints
    primary_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&forecast_days=14&timezone=Africa/Accra"
    secondary_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&forecast_days=14&models=gfs_seamless&timezone=Africa/Accra"

    cached_df, is_fresh = fetch_from_local_cache(lat, lon)
    if cached_df is not None and is_fresh:
        return cached_df, "🟢 MEMORY INSTANCE FRESH (CACHE ACTIVE)"

    # Primary API Call
    try:
        res = requests.get(primary_url, timeout=3)
        if res.status_code == 200:
            daily = res.json()['daily']
            df = pd.DataFrame({
                "Date": daily['time'], "Max Temp (°C)": daily['temperature_2m_max'],
                "Min Temp (°C)": daily['temperature_2m_min'], "Rainfall (mm)": daily['precipitation_sum']
            })
            save_to_local_cache(lat, lon, df)
            return df, "🟢 PRIMARY LIVE TELEMETRY"
    except Exception as e:
        system_logger.error(f"Primary Ingestion Fault at ({lat}, {lon}): {str(e)}")

    # Secondary API Call (True NOAA Infrastructure Fallback)
    try:
        res = requests.get(secondary_url, timeout=3)
        if res.status_code == 200:
            daily = res.json()['daily']
            df = pd.DataFrame({
                "Date": daily['time'], "Max Temp (°C)": daily['temperature_2m_max'],
                "Min Temp (°C)": daily['temperature_2m_min'], "Rainfall (mm)": daily['precipitation_sum']
            })
            save_to_local_cache(lat, lon, df)
            return df, "🟡 BACKUP LIVE TELEMETRY (NOAA GFS)"
    except Exception as e:
        system_logger.error(f"Secondary Model Ingestion Fault at ({lat}, {lon}): {str(e)}")

    if cached_df is not None:
        return cached_df, "🟠 STALE OFFLINE STORAGE ENGINE FALLBACK"
    return None, "🚨 NETWORK DROPOUT CRITICAL"

# ==========================================
# 🚨 LAYER 4: LIVE SECURE ALERTS WITH GRACEFUL DEGRADATION
# ==========================================
def dispatch_twilio_sms_hardened(recipient_phone, message_body):
    """Executes resilient cellular notification loops with clean environment validation."""
    # REFACTOR: Utilize safe fallback getters to achieve graceful degradation bounds
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_phone = os.environ.get("TWILIO_NUMBER")
    
    if not all([account_sid, auth_token, from_phone]):
        system_logger.error("SMS Infrastructure unmapped. Graceful platform degradation active.")
        return False

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    payload = {"To": recipient_phone, "From": from_phone, "Body": message_body}
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            res = requests.post(url, data=payload, auth=(account_sid, auth_token), timeout=5)
            if res.status_code in [200, 201]:
                system_logger.info(f"Twilio message successfully broadcast on attempt {attempt + 1}")
                return True
        except requests.RequestException as network_error:
            system_logger.error(f"SMS retry loop exception active ({attempt + 1}/{max_retries}): {str(network_error)}")
        if attempt < max_retries - 1:
            time.sleep(2 ** (attempt + 1))
            
    return False

def dispatch_smtp_email_hardened(target_email, subject, body_content):
    """Transmits encrypted briefings through an automated, resilient SMTP tunnel connection."""
    smtp_server = os.environ.get("SMTP_HOST")
    smtp_port = os.environ.get("SMTP_PORT")
    sender_email = os.environ.get("SMTP_USER")
    sender_password = os.environ.get("SMTP_PASSWORD")

    if not all([smtp_server, smtp_port, sender_email, sender_password]):
        system_logger.error("SMTP Infrastructure unmapped. Graceful platform degradation active.")
        return False

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = target_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body_content, 'html'))

    max_retries = 3
    for attempt in range(max_retries):
        try:
            with smtplib.SMTP(smtp_server, int(smtp_port), timeout=6) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.send_message(msg)
                return True
        except Exception as relay_error:
            system_logger.error(f"Email retry loop exception active ({attempt + 1}/{max_retries}): {str(relay_error)}")
        if attempt < max_retries - 1:
            time.sleep(2 ** (attempt + 1))
            
    return False

def route_emergency_broadcast(org_id, target_exposure, primary_threat):
    system_logger.critical(f"Risk Threshold Breached for {org_id}. Value At Risk: GH₵ {target_exposure:,.2f}")
    sms_alert_text = f"[CRIP ALERT] Space {org_id} Exposure Cap Breached: GH₵ {target_exposure:,.2f} under threat by {primary_threat}."
    
    sms_sent = dispatch_twilio_sms_hardened("+233200000000", sms_alert_text)
    
    html_bulletin = f"<html><body><h2 style='color:#991B1B;'>⚠️ Exposure Alert</h2><p>Tenant <strong>{org_id}</strong> value at risk: GH₵ {target_exposure:,.2f}</p></body></html>"
    email_sent = dispatch_smtp_email_hardened("risk-manager@agricorp.com", f"🚨 CRIP RISK NOTICE: {org_id}", html_bulletin)

    # Inform front-end operator regarding channel delivery performance status
    if not sms_sent and not email_sent:
        st.sidebar.warning("⚠️ Alerts deactivated (Environment links unmapped or unreached).")
    else:
        st.sidebar.error("📢 Resilient communication broadcasts successfully dispatched.")

# ==========================================
# 🔒 LAYER 5: ACCESS CONTROLS GATEWAY
# ==========================================
st.sidebar.image("https://img.icons8.com/fluency/96/shield.png", width=45)
st.sidebar.title("CRIP Gateway v3.5 Pro")

if "auth_token" not in st.session_state: st.session_state.auth_token = None
if "account_tier" not in st.session_state: st.session_state.account_tier = "Standard Demo"

if not st.session_state.auth_token:
    st.sidebar.subheader("🔒 Authentication Pool")
    input_user = st.sidebar.text_input("User ID Tag")
    input_pass = st.sidebar.text_input("Key Sequence Token", type="password")
    
    if st.sidebar.button("Initialize Platform Engine", use_container_width=True):
        with DatabaseWorkspaceManager() as cursor:
            cursor.execute("SELECT salt_hex, password_hash, role, org_id FROM users WHERE username=?", (input_user.strip(),))
            user_record = cursor.fetchone()
        
        if user_record and secure_hash_pbkdf2(input_pass.strip(), user_record[0]) == user_record[1]:
            st.session_state.auth_token = f"JWT_SECURE_{hashlib.md5(input_user.encode()).hexdigest()[:6]}"
            st.session_state.user_role = user_record[2]
            st.session_state.user_display = input_user.strip()
            st.session_state.org_id = user_record[3]
            st.session_state.account_tier = "Enterprise Agribusiness Plan" if input_user.strip() == "system_admin_kumi" else "Standard Demo"
            st.rerun()
        else:
            st.sidebar.error("Verification Token Mismatch.")
    st.stop()
else:
    st.sidebar.success(f"🔐 Session: {st.session_state.user_display}")
    st.sidebar.info(f"Workspace Boundary: {st.session_state.org_id}")
    if st.sidebar.button("Kill Process Loop", use_container_width=True):
        st.session_state.auth_token = None
        st.rerun()

# ==========================================
# 📊 LAYER 6: CORE PREDICTIVE COMPUTATION LOOP
# ==========================================
with DatabaseWorkspaceManager() as cursor:
    cursor.execute("SELECT * FROM farm_clusters WHERE org_id=?", (st.session_state.org_id,))
    columns = [col[0] for col in cursor.description]
    tenant_clusters_df = pd.DataFrame(cursor.fetchall(), columns=columns)

active_usage_count = len(tenant_clusters_df)
portfolio_alerts = []
global_total_valuation = 0.0
global_exposure_max = 0.0
cluster_rankings = []
map_coordinates_list = []
active_threat_types = []

if not tenant_clusters_df.empty:
    processing_df = tenant_clusters_df.head(3) if st.session_state.account_tier == "Standard Demo" else tenant_clusters_df
    
    for _, row in processing_df.iterrows():
        name = row["cluster_name"]
        lat = row["latitude"]
        lon = row["longitude"]
        crop = row["crop_type"]
        asset_val = row["acres"] * row["expected_yield"] * row["market_price"]
        global_total_valuation += asset_val
        
        weather_df, stream_tag = fetch_weather_intelligence(lat, lon)
        if weather_df is None: continue
            
        cluster_max_exposure = 0.0
        total_rainfall_14days = weather_df["Rainfall (mm)"].sum()
        max_observed_temp = weather_df["Max Temp (°C)"].max()
        
        if total_rainfall_14days > 45.0:
            loss_max = asset_val * 0.35 * min(1.0, total_rainfall_14days / 100.0)
            global_exposure_max += loss_max
            cluster_max_exposure = max(cluster_max_exposure, loss_max)
            active_threat_types.append("Flooding / Excess Rain")
            
        if max_observed_temp > 33.0:
            loss_max = asset_val * 0.25 * min(1.0, (max_observed_temp - 30) / 10)
            global_exposure_max += loss_max
            cluster_max_exposure = max(cluster_max_exposure, loss_max)
            active_threat_types.append("Thermal Heat Stress")

        cluster_rankings.append({
            "Farm Node Cluster Name": name, "Crop Type": crop, "Valuation (GHS)": asset_val, "Value At Risk (GHS)": cluster_max_exposure, "Network Stream": stream_tag
        })
        map_coordinates_list.append({"latitude": lat, "longitude": lon, "size": float(max(20.0, min(180.0, (cluster_max_exposure / 20000.0))))})

unique_threat_count = len(list(set(active_threat_types)))

if not tenant_clusters_df.empty:
    today_str = datetime.now().strftime("%Y-%m-%d")
    with DatabaseWorkspaceManager() as cursor:
        cursor.execute("""
            INSERT INTO daily_risk_ledger (snapshot_date, org_id, aggregate_exposure, active_threat_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(snapshot_date, org_id) DO UPDATE SET aggregate_exposure=?, active_threat_count=?
        """, (today_str, st.session_state.org_id, global_exposure_max, unique_threat_count, global_exposure_max, unique_threat_count))

with DatabaseWorkspaceManager() as cursor:
    cursor.execute("SELECT aggregate_exposure FROM daily_risk_ledger WHERE org_id=? AND snapshot_date != date('now') ORDER BY snapshot_date DESC LIMIT 7", (st.session_state.org_id,))
    records = cursor.fetchall()

if not records:
    trend_percentage, trend_narrative_label = 0.0, "⚖️ Baseline Establishing"
else:
    historic_values = [r[0] for r in records]
    avg_historic_exposure = sum(historic_values) / len(historic_values)
    if avg_historic_exposure == 0:
        trend_percentage, trend_narrative_label = 0.0, "⚖️ Baseline Stable"
    else:
        trend_percentage = ((global_exposure_max - avg_historic_exposure) / avg_historic_exposure) * 100
        trend_narrative_label = f"📈 +{trend_percentage:.1f}% Risk" if trend_percentage > 5.0 else f"📉 {trend_percentage:.1f}% Risk" if trend_percentage < -5.0 else "🔄 Volatility Stable"

# ==========================================
# 🖥️ LAYER 7: PRESENTATION GRAPHICS ENVIRONMENT
# ==========================================
st.title("🌍 Climate Financial Risk Intelligence Platform")

if not tenant_clusters_df.empty:
    dominant_threat_profile = ", ".join(list(set(active_threat_types))) if active_threat_types else "None"
    st.markdown(f"""
    <div style="background-color:#0F172A; padding:26px; border-radius:8px; border-left:8px solid #B91C1C; color:#FFFFFF">
        <h3>GH₵ {global_exposure_max:,.2f}</h3>
        <p>{trend_narrative_label} | Threat Vectors: {dominant_threat_profile} (Count: {unique_threat_count})</p>
    </div>
    """, unsafe_allow_html=True)

    if global_exposure_max > 100000:
        route_emergency_broadcast(st.session_state.org_id, global_exposure_max, dominant_threat_profile)

st.markdown("### 📊 Operational Real-Time Telemetry Mapping Matrix")
col_map, col_table = st.columns([4, 3])
with col_map:
    if map_coordinates_list: st.map(pd.DataFrame(map_coordinates_list), size="size")
with col_table:
    if cluster_rankings: st.dataframe(pd.DataFrame(cluster_rankings), use_container_width=True, hide_index=True)
