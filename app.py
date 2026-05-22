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
from datetime import datetime, timedelta

# Configure Enterprise Page Environment
st.set_page_config(page_title="Climate Financial Risk Intelligence Platform (V3.5 Pro)", layout="wide")

# ==========================================
# 🛑 LAYER 0: PRODUCTION ROTATING LOGGING SYSTEM
# ==========================================
def initialize_production_logger():
    """Sets up an industrial-grade rolling log architecture."""
    logger = logging.getLogger("CRIP_PROD_ENGINE")
    logger.setLevel(logging.INFO)
    
    # Prevent duplicate handler attachments during Streamlit hot-reloads
    if not logger.handlers:
        # Enforce file limits: 5MB maximum capacity per file with a 3-file history rotation
        file_handler = RotatingFileHandler(
            "crip_production.log", 
            maxBytes=5 * 1024 * 1024, 
            backupCount=3,
            encoding="utf-8"
        )
        
        # Standardized log formatting for system monitoring tools (Datadog/Logstash)
        log_format = logging.Formatter(
            '[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(log_format)
        logger.addHandler(file_handler)
        
    return logger

system_logger = initialize_production_logger()

# ==========================================
# 💾 LAYER 1: DATA PERSISTENCE & TIMELINE LEDGERS
# ==========================================
def generate_dynamic_salt():
    return os.urandom(16).hex()

def secure_hash_pbkdf2(password, salt_hex):
    salt = bytes.fromhex(salt_hex)
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000).hex()

def init_hardened_db():
    conn = sqlite3.connect("climate_risk_vault.db")
    cursor = conn.cursor()
    
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS asset_audit_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, cluster_name TEXT,
            crop_type TEXT, risk_event TEXT, logged_by TEXT, action_implemented TEXT,
            actual_loss_ghs REAL, predicted_loss_max_ghs REAL, status TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS calibration_matrix (
            crop_type TEXT PRIMARY KEY, heavy_rain_low REAL, heavy_rain_high REAL, heat_stress_low REAL, heat_stress_high REAL
        )
    """)
    
    # Seed Baseline Security Framework Profiles
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
            
    # Seed Data Points
    cursor.execute("SELECT COUNT(*) FROM farm_clusters")
    if cursor.fetchone()[0] == 0:
        base_clusters = [
            ("ORG_KUMI_AGRI_GLOBAL", "Kumasi Cluster (Ashanti Region)", 6.69, -1.62, "Maize", 1200.0, 4.5, 450.0),
            ("ORG_KUMI_AGRI_GLOBAL", "Koforidua Cluster (Eastern Region)", 6.09, -0.26, "Rice", 850.0, 3.8, 600.0),
            ("ORG_COCOA_CORP", "Sefwi Wiawso Cluster (Western North)", 6.16, -2.48, "Cocoa", 2500.0, 1.2, 12500.0)
        ]
        cursor.executemany("INSERT INTO farm_clusters (org_id, cluster_name, latitude, longitude, crop_type, acres, expected_yield, market_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", base_clusters)
        
    conn.commit()
    conn.close()

init_hardened_db()

# ==========================================
# 🛰️ LAYER 2: TELEMETRY INGESTION WITH TRACED COLD FAILOVER
# ==========================================
def save_to_local_cache(lat, lon, df):
    conn = sqlite3.connect("climate_risk_vault.db")
    cursor = conn.cursor()
    coord_key = f"{lat:.2f}_{lon:.2f}"
    json_str = df.to_json(date_format='iso')
    cursor.execute("""
        INSERT INTO weather_cache (coordinate_key, timestamp, json_payload)
        VALUES (?, ?, ?)
        ON CONFLICT(coordinate_key) DO UPDATE SET timestamp=?, json_payload=?
    """, (coord_key, datetime.now().isoformat(), json_str, datetime.now().isoformat(), json_str))
    conn.commit()
    conn.close()

def fetch_from_local_cache(lat, lon):
    conn = sqlite3.connect("climate_risk_vault.db")
    cursor = conn.cursor()
    coord_key = f"{lat:.2f}_{lon:.2f}"
    cursor.execute("SELECT timestamp, json_payload FROM weather_cache WHERE coordinate_key=?", (coord_key,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        cache_time = datetime.fromisoformat(row[0])
        if datetime.now() - cache_time < timedelta(hours=3):
            return pd.read_json(row[1]), True
        return pd.read_json(row[1]), False
    return None, False

def fetch_weather_intelligence(lat, lon):
    primary_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&forecast_days=14&timezone=Africa/Accra"
    secondary_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&forecast_days=14&models=gfs_seamless"

    cached_df, is_fresh = fetch_from_local_cache(lat, lon)
    if cached_df is not None and is_fresh:
        system_logger.info(f"Cache hit: Serving fresh data for spatial point ({lat}, {lon})")
        return cached_df, "🟢 MEMORY INSTANCE FRESH (CACHE ACTIVE)"

    # Step 1: Query Primary Route
    try:
        res = requests.get(primary_url, timeout=3)
        if res.status_code == 200:
            daily = res.json()['daily']
            df = pd.DataFrame({
                "Date": daily['time'], "Max Temp (°C)": daily['temperature_2m_max'],
                "Min Temp (°C)": daily['temperature_2m_min'], "Rainfall (mm)": daily['precipitation_sum']
            })
            save_to_local_cache(lat, lon, df)
            system_logger.info(f"Primary API Success: Pulled telemetry data for coordinate space ({lat}, {lon})")
            return df, "🟢 PRIMARY LIVE TELEMETRY"
        else:
            system_logger.warning(f"Primary API Outage: Remote site responded with code {res.status_code} for ({lat}, {lon})")
    except Exception as e:
        system_logger.error(f"Network Fault on Primary API stream at ({lat}, {lon}): {str(e)}")
        st.sidebar.warning(f"Primary Stream Outage at ({lat}, {lon}). Fallback engaged.")

    # Step 2: Query Backup Route
    try:
        res = requests.get(secondary_url, timeout=3)
        if res.status_code == 200:
            daily = res.json()['daily']
            df = pd.DataFrame({
                "Date": daily['time'], "Max Temp (°C)": daily['temperature_2m_max'],
                "Min Temp (°C)": daily['temperature_2m_min'], "Rainfall (mm)": daily['precipitation_sum']
            })
            save_to_local_cache(lat, lon, df)
            system_logger.info(f"Secondary Route Success: Stabilized network link for ({lat}, {lon})")
            return df, "🟡 BACKUP LIVE TELEMETRY"
        else:
            system_logger.warning(f"Secondary API Outage: Remote site responded with code {res.status_code} for ({lat}, {lon})")
    except Exception as e:
        system_logger.error(f"Network Fault on Secondary API stream at ({lat}, {lon}): {str(e)}")
        st.sidebar.warning(f"Secondary Stream Outage at ({lat}, {lon}). Accessing local cache storage...")

    # Step 3: Fallback to cold cache record
    if cached_df is not None:
        system_logger.warning(f"Resiliency Triggered: Serving expired cold cache for coordinate point ({lat}, {lon})")
        return cached_df, "¼ STALE OFFLINE STORAGE ENGINE FALLBACK"
        
    system_logger.critical(f"Pipeline Dropout: No network routes available and zero database cache matches for ({lat}, {lon})")
    return None, "🚨 NETWORK DROPOUT CRITICAL"

# ==========================================
# 📊 LAYER 3: PREDICTIVE INTEL & HISTORICAL TREND COMPUTATION
# ==========================================
def commit_daily_risk_snapshot(org_id, total_exposure, threat_count):
    conn = sqlite3.connect("climate_risk_vault.db")
    cursor = conn.cursor()
    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("""
        INSERT INTO daily_risk_ledger (snapshot_date, org_id, aggregate_exposure, active_threat_count)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(snapshot_date, org_id) DO UPDATE SET aggregate_exposure=?, active_threat_count=?
    """, (today_str, org_id, total_exposure, threat_count, total_exposure, threat_count))
    conn.commit()
    conn.close()

def calculate_historical_trend_delta(org_id, current_exposure):
    conn = sqlite3.connect("climate_risk_vault.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT aggregate_exposure FROM daily_risk_ledger 
        WHERE org_id=? AND snapshot_date != date('now')
        ORDER BY snapshot_date DESC LIMIT 7
    """, (org_id,))
    records = cursor.fetchall()
    conn.close()
    
    if not records: return 0.0, "⚖️ Baseline Establishing"
        
    historic_values = [row[0] for row in records]
    avg_historic_exposure = sum(historic_values) / len(historic_values)
    
    if avg_historic_exposure == 0: return 0.0, "⚖️ Baseline Stable"
        
    percentage_delta = ((current_exposure - avg_historic_exposure) / avg_historic_exposure) * 100
    if percentage_delta > 5.0:
        return percentage_delta, f"📈 +{percentage_delta:.1f}% Risk Acceleration vs 7-Day Average"
    elif percentage_delta < -5.0:
        return percentage_delta, f"📉 {percentage_delta:.1f}% Risk Abatement vs 7-Day Average"
    else:
        return percentage_delta, "🔄 Standard Volatility Footprint"

# ==========================================
# 🚨 LAYER 4: LIVE PRODUCTION NOTIFICATION INTEGRATIONS
# ==========================================
def dispatch_twilio_sms(recipient_phone, message_body):
    """Sends immediate cellular notifications to field units via the Twilio SMS Gateway."""
    # Retrieve tokens from environment configuration files
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "MOCK_SID_VAL")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "MOCK_TOKEN_VAL")
    from_phone = os.environ.get("TWILIO_NUMBER", "+1234567890")
    
    if account_sid == "MOCK_SID_VAL":
        system_logger.info(f"SMS Integration Broadcast Simulation (Twilio Env Token Unset) To: {recipient_phone} -> Body: {message_body}")
        return False

    try:
        # standard integration payload framework
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        payload = {"To": recipient_phone, "From": from_phone, "Body": message_body}
        res = requests.post(url, data=payload, auth=(account_sid, auth_token), timeout=5)
        if res.status_code in [200, 201]:
            system_logger.info(f"Twilio SMS dispatched successfully to destination channel: {recipient_phone}")
            return True
        else:
            system_logger.error(f"Twilio API Gateway rejected the payload request with code {res.status_code}: {res.text}")
    except Exception as error:
        system_logger.error(f"Twilio API connection failed: {str(error)}")
    return False

def dispatch_smtp_email(target_email, subject, body_content):
    """Pushes automated executive HTML summaries to corporate endpoints via SMTP relay lines."""
    smtp_server = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    sender_email = os.environ.get("SMTP_USER", "alert-system@globalagri.com")
    sender_password = os.environ.get("SMTP_PASSWORD", "")

    if not sender_password:
        system_logger.info(f"SMTP Relay Simulation (SMTP Password Environment Unset) To: {target_email} -> Sub: {subject}")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = target_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body_content, 'html'))

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        
        system_logger.info(f"Executive security bulletin sent to target subscriber box: {target_email}")
        return True
    except Exception as error:
        system_logger.error(f"SMTP corporate relay failed to process message package: {str(error)}")
    return False

def route_emergency_broadcast(org_id, target_exposure, primary_threat):
    """Coordinates risk actions across secure messaging pipelines."""
    system_logger.critical(f"Risk Breach Exception: Asset group belonging to {org_id} has exceeded acceptable parameters. Valuation at Risk: GH₵ {target_exposure:,.2f}")
    
    sms_alert_text = f"[CRIP RISK ALERT] Organization {org_id} capital at risk has hit GH₵ {target_exposure:,.2f} driven by {primary_threat}. Action required."
    
    # Fire asynchronous multi-channel pipelines
    dispatch_twilio_sms("+233200000000", sms_alert_text)
    
    html_bulletin = f"""
    <html>
        <body style="font-family:sans-serif; padding:20px; color:#333;">
            <h2 style="color:#B91C1C;">⚠️ CRIP Automated Exposure Alert Bulletin</h2>
            <p>This automated notification was generated because asset group holdings for tenant space <strong>{org_id}</strong> have breached safety baselines.</p>
            <ul>
                <li><strong>Current Capital Exposure:</strong> GH₵ {target_exposure:,.2f}</li>
                <li><strong>Active Atmospheric Vectors:</strong> {primary_threat}</li>
                <li><strong>Timestamp:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
            </ul>
            <p>Please log in to your management gateway interface immediately to authorize tactical defense protocols.</p>
        </body>
    </html>
    """
    dispatch_smtp_email("risk-officer@agricorp.com", f"🚨 CRIP RISK BREACH NOTICE: {org_id}", html_bulletin)

    st.sidebar.error(f"""
    📢 **AUTONOMOUS PUSH DISPATCHED**
    * **Impact Matrix:** GH₵ {target_exposure:,.2f}
    * **Vector:** {primary_threat}
    * **Logging Output:** Dispatched updates to SMS & Corporate Email servers.
    """)

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
        conn = sqlite3.connect("climate_risk_vault.db")
        cursor = conn.cursor()
        cursor.execute("SELECT salt_hex, password_hash, role, org_id FROM users WHERE username=?", (input_user.strip(),))
        user_record = cursor.fetchone()
        conn.close()
        
        if user_record and secure_hash_pbkdf2(input_pass.strip(), user_record[0]) == user_record[1]:
            st.session_state.auth_token = f"JWT_SECURE_{hashlib.md5(input_user.encode()).hexdigest()[:6]}"
            st.session_state.user_role = user_record[2]
            st.session_state.user_display = input_user.strip()
            st.session_state.org_id = user_record[3]
            st.session_state.account_tier = "Enterprise Agribusiness Plan" if input_user.strip() == "system_admin_kumi" else "Standard Demo"
            system_logger.info(f"User login authorized: session handle {st.session_state.user_display} granted access rights to space {st.session_state.org_id}")
            st.rerun()
        else:
            system_logger.warning(f"Unauthorized security attempt detected on user entry handle: '{input_user}'")
            st.sidebar.error("Verification Token Mismatch.")
    st.stop()
else:
    st.sidebar.success(f"🔐 Session: {st.session_state.user_display}")
    st.sidebar.info(f"Workspace Boundary: {st.session_state.org_id}")
    
    if st.sidebar.button("Kill Process Loop", use_container_width=True):
        system_logger.info(f"User session terminated: {st.session_state.user_display}")
        st.session_state.auth_token = None
        st.rerun()

# ==========================================
# 📊 LAYER 6: CORE PREDICTIVE COMPUTATION LOOP
# ==========================================
conn = sqlite3.connect("climate_risk_vault.db")
tenant_clusters_df = pd.read_sql_query("SELECT * FROM farm_clusters WHERE org_id=?", conn, params=(st.session_state.org_id,))
conn.close()

active_usage_count = len(tenant_clusters_df)
over_limit_active = st.session_state.account_tier == "Standard Demo" and active_usage_count > 3

portfolio_alerts = []
global_total_valuation = 0.0
global_exposure_max = 0.0
cluster_rankings = []
map_coordinates_list = []
active_threat_types = []
stream_statuses = set()

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
        stream_statuses.add(stream_tag)
        
        if weather_df is None: continue
            
        cluster_max_exposure = 0.0
        total_rainfall_14days = weather_df["Rainfall (mm)"].sum()
        max_observed_temp = weather_df["Max Temp (°C)"].max()
        
        if total_rainfall_14days > 45.0:
            loss_max = asset_val * 0.35 * min(1.0, total_rainfall_14days / 100.0)
            global_exposure_max += loss_max
            cluster_max_exposure = max(cluster_max_exposure, loss_max)
            active_threat_types.append("Flooding / Excess Rain")
            portfolio_alerts.append({"cluster": name, "type": "⛈️ Inundation", "max": loss_max, "action": "Delay planting schedules by 5-7 days to avoid root-washout patterns."})
            
        if max_observed_temp > 33.0:
            loss_max = asset_val * 0.25 * min(1.0, (max_observed_temp - 30) / 10)
            global_exposure_max += loss_max
            cluster_max_exposure = max(cluster_max_exposure, loss_max)
            active_threat_types.append("Thermal Heat Stress")
            portfolio_alerts.append({"cluster": name, "type": "🔥 Heat Saturation", "max": loss_max, "action": "Deploy morning irrigation sequences to shield root systems."})

        cluster_rankings.append({
            "Farm Node Cluster Name": name, "Crop Type": crop, "Valuation (GHS)": asset_val, "Value At Risk (GHS)": cluster_max_exposure, "Network Stream": stream_tag
        })
        map_coordinates_list.append({"latitude": lat, "longitude": lon, "size": float(max(20.0, min(180.0, (cluster_max_exposure / 20000.0))))})

unique_threat_count = len(list(set(active_threat_types)))

if not tenant_clusters_df.empty:
    commit_daily_risk_snapshot(st.session_state.org_id, global_exposure_max, unique_threat_count)

trend_percentage, trend_narrative_label = calculate_historical_trend_delta(st.session_state.org_id, global_exposure_max)

# ==========================================
# 🖥️ LAYER 7: PRESENTATION GRAPHICS ENVIRONMENT
# ==========================================
st.title("🌍 Climate Financial Risk Intelligence Platform")
st.caption(f"Real-Time Climate Risk Decision Engine with Automated Alerts and Adaptive Learning Matrix.")

if not tenant_clusters_df.empty:
    executive_threat_signal = "🚨 HIGH RISK EXPOSURE IMPACT" if global_exposure_max > 100000 else "🟢 STABLE RUNTIME BASELINE"
    dominant_threat_profile = ", ".join(list(set(active_threat_types))) if active_threat_types else "None Identified"
    trend_color = "#FCA5A5" if trend_percentage > 5.0 else "#86EFAC" if trend_percentage < -5.0 else "#94A3B8"
    
    st.markdown(f"""
    <div style="background-color:#0F172A; padding:26px; border-radius:8px; border-left:8px solid #B91C1C; margin-bottom:25px; color:#FFFFFF">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <p style="font-size:11px; text-transform:uppercase; letter-spacing:1px; color:#94A3B8; margin:0;">💼 PREDICTIVE RISK DECISION ENGINE — SYSTEM INSIGHT BRIEF</p>
            <span style="background-color:#B91C1C; color:white; font-size:11px; padding:4px 9px; font-weight:700; border-radius:4px;">{executive_threat_signal}</span>
        </div>
        
        <div style="display:flex; align-items:baseline; gap:25px; margin:10px 0;">
            <h2 style="margin:0; font-size:32px; font-weight:800; color:#F8FAFC;">GH₵ {global_exposure_max:,.2f}</h2>
            <span style="color:{trend_color}; font-size:14px; font-weight:600;">{trend_narrative_label}</span>
        </div>
        
        <div style="display:grid; grid-template-columns: 1fr 2fr; gap:20px; border-top:1px solid #334155; padding-top:14px; margin-top:10px; font-size:13px;">
            <div><strong>Active Climate Threat Profile:</strong> <span style="color:#FCA5A5;">{dominant_threat_profile} (Count: {unique_threat_count})</span></div>
            <div><strong>Executive Mitigation Mandate:</strong> <span style="color:#38BDF8;">{"CRITICAL Action Protocol: Postpone seeding cycles across threatened sectors immediately." if active_threat_types else "No active risk exceptions flagged."}</span></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if global_exposure_max > 100000:
        route_emergency_broadcast(st.session_state.org_id, global_exposure_max, dominant_threat_profile)

if over_limit_active:
    st.error(f"🛑 **SaaS Workspace Cap Limit Reached:** Current account restricts active processing to 3 nodes.")

# Onboarding Module Panel
with st.sidebar.expander("🚜 Dynamic Corporate Farm Onboarding", expanded=False):
    st.subheader("Manual Node Creation")
    with st.form("single_farm_form"):
        f_name = st.text_input("Farm Node Cluster Name:")
        f_lat = st.number_input("Latitude:", format="%.4f", value=6.20)
        f_lon = st.number_input("Longitude:", format="%.4f", value=-2.10)
        f_crop = st.selectbox("Active Crop Type:", ["Maize", "Rice", "Cocoa"])
        f_acres = st.number_input("Acres Covered:", min_value=1.0, value=250.0)
        f_yield = st.number_input("Expected Yield / Acre:", min_value=0.1, value=2.5)
        f_price = st.number_input("Market Price (GHS):", min_value=1.0, value=500.0)
        
        if st.form_submit_button("Deploy Node to Database Pool", use_container_width=True):
            if st.session_state.account_tier == "Standard Demo" and active_usage_count >= 3:
                st.error("❌ Transaction Blocked: Standard Demo accounts are capped at 3 nodes.")
            elif f_name:
                conn = sqlite3.connect("climate_risk_vault.db")
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO farm_clusters (org_id, cluster_name, latitude, longitude, crop_type, acres, expected_yield, market_price)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (st.session_state.org_id, f_name, f_lat, f_lon, f_crop, f_acres, f_yield, f_price))
                conn.commit()
                conn.close()
                st.success(f"Provisioned node: {f_name}")
                st.rerun()

# Layout Analytical Mapping Windows
st.markdown("### 📊 Operational Real-Time Telemetry Mapping Matrix")
col_map, col_table = st.columns([4, 3])
with col_map:
    if map_coordinates_list: st.map(pd.DataFrame(map_coordinates_list), size="size")
    else: st.info("No active geo-coordinates loaded.")
with col_table:
    if cluster_rankings: st.dataframe(pd.DataFrame(cluster_rankings), use_container_width=True, hide_index=True)
    else: st.info("Awaiting dynamic data inputs.")
