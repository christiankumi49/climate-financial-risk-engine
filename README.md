# 🌍 Climate Financial Risk Intelligence Platform (CRIP v3.5 Pro)

An enterprise-grade risk intelligence architecture that translates real-time meteorological telemetry into predictive asset exposure modeling, automated operational directives, and error-driven calibration matrices for commercial agriculture across West Africa.

## 🔗 Live Demo

Access the deployed platform here: [Insert Link]

**Demo Credentials:**
- Executive: `executive_lead` / `gh_exec_2026`

---

## 💼 The Business Problem & Solution

Traditional weather dashboards display baseline historical or forecast weather, but they fail to translate atmospheric data into financial risk metrics. For corporate agricultural lenders, commodity investors, and farm managers, a spike in temperature or a sudden deluge is a direct threat to capital.

**CRIP v3.5 Pro** bridges this gap. The platform continuously ingests live environmental telemetry and processes it through localized, crop-specific vulnerability coefficients. Instead of seeing raw environmental values, leadership is given an explicit **Value at Risk (GHS)**, an actionable **Tactical Field Response**, and a **Strategic ROI Recommendation** to insulate their financial exposure before a climate crisis hits.

---

## 🧠 Technical System Architecture

The core framework is built with **Python** and **Streamlit**, structurally decoupled across five production-grade operational layers to maximize reliability, security, and precision:

1. **Layer 1: Data Persistence & Cryptographic Vault**
   * Uses high-entropy **PBKDF2-HMAC-SHA256** hashing utilizing unique, unpredictable **16-byte per-user cryptographic salts** to eliminate rainbow table vulnerabilities and secure the local user registries.
2. **Layer 2: Meteorological Caching & Telemetry Stream**
   * Integrates an asynchronous telemetry data ingestion pipeline pulling 14-day micro-grid coordinates via remote weather APIs, backed by a **1,800-second TTL (Time-To-Live) cache layer** to optimize performance and prevent API throttling.
3. **Layer 3: Enterprise Security Gateway**
   * Implements strict role-based access control (RBAC) separating administrative, executive, and operational clearances. Sessions are validated against internal database tokens.
4. **Layer 4: Predictive Financial Logic & Adaptive Machine Learning**
   * Features a closed-loop, error-driven **Rolling ML Calibration Engine**. As actual field outcomes are logged into the ledger, the platform evaluates the *Mean Absolute Percentage Error (MAPE)* and automatically tunes the high-boundary risk coefficients, maintaining a live **Model Prediction Confidence Score**.
5. **Layer 5: Safe Degraded Operation Fail-Safe (Continuity Layer)**
   * Built with defensive coding boundaries. If external API streams drop, the platform triggers an automated hardlock, freezing all financial calculations to insulate corporate executives from faulty data while maintaining full access to historical ledger logs.

---

## 💻 Technical Stack

* **Frontend & Dashboard Engine:** Streamlit
* **Core Language & Processing:** Python 3.10+ (Pandas, Requests)
* **Storage & Integrity Layer:** SQLite (Local Prototyping) / PostgreSQL Ready
* **Cryptographic Stack:** Hashlib (PBKDF2-SHA256 Engine), OS (urandom entropy sources)
* **API Telemetry:** Open-Meteo Global Meteorological Engine (Africa/Accra Timezone Synchronized)

---

## 🚀 Phase 2 Production Migration Roadmap

This system was explicitly engineered as a stateful Minimum Viable Product (MVP) to validate mathematical risk variables and UI workflows. The architecture is ready for enterprise cloud scale via our Phase 2 manifest:
* **Storage Layer Migration:** Swapping the file-based SQLite database for a cloud-managed, high-concurrency **PostgreSQL database (hosted via AWS RDS or Supabase)**.
* **Cryptographic Session Hardening:** Transitioning from simulated login tokens to real, signed **JSON Web Tokens (PyJWT)** enforcing row-level security boundaries at the database query level.
* **API Redundancy Multi-Pool:** Expanding the weather ingestion bridge into a multi-source fallback array, linking concurrently with alternative enterprise data lines and **GMet (Ghana Meteorological Agency)** telemetry.
* **Operational Telemetry Layer:** Introducing early monitoring pipelines to actively track API failure rates, model drift anomalies, and authentication security spikes.

---

## 🛠️ Local Deployment Guide

To run this platform locally on your machine for auditing or testing:

1. Clone this repository to your local directory.
2. Ensure you have Python 3.10+ installed.
3. Install the required external third-party dependencies:
   ```bash
   pip install -r requirements.txt
   streamlit run app.py

Walkthrough Access Credentials:
System Admin Profile: User: system_admin_kumi | Pass: gh_admin_2026

Executive Lead Profile: User: executive_lead | Pass: gh_exec_2026

Field Manager Profile: User: field_manager_osei | Pass: gh_farm_2026

Developed by Christian Kumi — Meteorology, Climate Science & Software Architecture at KNUST.
