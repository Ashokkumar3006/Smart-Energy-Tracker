"""Enhanced backend_app.py with device-specific monitoring and AI suggestions (updated to categorical efficiency)"""
from __future__ import annotations
from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from datetime import datetime
import os
import random
import json
import threading
import time
from typing import Optional
import sqlite3
from contextlib import contextmanager
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Global DataFrame
df: pd.DataFrame | None = None

# Ensure data folder exists if needed
if not os.path.exists('static'):
    os.makedirs('static')

# Database setup
DATABASE_PATH = 'energy_alerts.db'

def init_database():
    """Initialize the SQLite database"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Alert settings (supports optional device_name-specific thresholds)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alert_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setting_name TEXT NOT NULL,
            device_name TEXT,
            threshold_value REAL NOT NULL,
            threshold_type TEXT NOT NULL,
            is_enabled BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(setting_name, device_name)
        )
    ''')
    
    # Email recipients
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS email_recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            alert_types TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Alert history
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT NOT NULL,
            device_name TEXT,
            threshold_value REAL,
            actual_value REAL,
            message TEXT,
            recipients_sent TEXT,
            status TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# Optional improved EmailService (if available)
try:
    from email_service_improved import EmailService
    email_service = EmailService()
except Exception:
    print("Warning: EmailService not available. Email functionality will be disabled.")
    email_service = None

# ---------------------- Anomaly Detector ----------------------
class AnomalyDetector:
    def __init__(self):
        self.baseline_data = None
        
    def train_model(self, data):
        """Train the anomaly detection model with baseline data"""
        self.baseline_data = data
        
    def _calculate_severity(self, actual, threshold):
        ratio = (actual / threshold) if threshold else 0
        if ratio < 1.2:
            return 'low'
        elif ratio < 1.5:
            return 'medium'
        elif ratio < 2.0:
            return 'high'
        else:
            return 'critical'
    
    def _calculate_severity_spike(self, percentage):
        if percentage < 75:
            return 'low'
        elif percentage < 150:
            return 'medium'
        elif percentage < 300:
            return 'high'
        else:
            return 'critical'

    def detect_device_specific_anomalies(self, recent_data, device_thresholds, global_thresholds):
        """Detect anomalies using device-specific thresholds where available"""
        anomalies = []
        for idx, reading in enumerate(recent_data):
            device_name = reading.get('device_name', reading.get('device', 'Unknown'))
            power = reading.get('power', 0.0)

            # Peak power thresholds (device overrides global)
            device_peak = device_thresholds.get(device_name, {}).get('peak_power')
            global_peak = global_thresholds.get('peak_power')
            peak_threshold = device_peak if device_peak is not None else global_peak

            if peak_threshold is not None and power > peak_threshold:
                anomalies.append({
                    'anomaly_type': 'peak_power',
                    'device': device_name,
                    'actual_value': power,
                    'threshold_value': peak_threshold,
                    'exceeded_by': power - peak_threshold,
                    'percentage_exceeded': ((power - peak_threshold) / peak_threshold) * 100 if peak_threshold else 0,
                    'severity': self._calculate_severity(power, peak_threshold),
                    'unit': 'W',
                    'description': f"Peak power {power:.1f}W exceeded {peak_threshold:.1f}W"
                })

            # Energy spike thresholds (compare to previous reading)
            device_spike = device_thresholds.get(device_name, {}).get('energy_spike')
            global_spike = global_thresholds.get('energy_spike')
            spike_threshold = device_spike if device_spike is not None else global_spike

            if idx > 0 and spike_threshold is not None:
                prev_power = recent_data[idx - 1].get('power', 0.0)
                if prev_power > 0:
                    increase_pct = ((power - prev_power) / prev_power) * 100
                    if increase_pct > spike_threshold:
                        anomalies.append({
                            'anomaly_type': 'energy_spike',
                            'device': device_name,
                            'actual_value': power,
                            'threshold_value': prev_power * (1 + spike_threshold / 100),
                            'exceeded_by': power - prev_power,
                            'percentage_exceeded': increase_pct,
                            'severity': self._calculate_severity_spike(increase_pct),
                            'unit': 'W',
                            'description': f"Energy spike {increase_pct:.1f}% detected"
                        })

        return anomalies

# Initialize detector
anomaly_detector = AnomalyDetector()

# Device categories and typical power ranges (used for classification, not % efficiency)
DEVICE_CATEGORIES = {
    'AC': {'min_power': 150, 'max_power': 2000},
    'Fridge': {'min_power': 80, 'max_power': 300},
    'Television': {'min_power': 50, 'max_power': 200},
    'Washing Machine': {'min_power': 300, 'max_power': 800},
    'Light': {'min_power': 5, 'max_power': 60},
    'Fan': {'min_power': 30, 'max_power': 100}
}

# ---------------------- Data Processing ----------------------
def load_data_from_json(json_data: list[dict]):
    """Convert JSON data into DataFrame."""
    global df
    rows = []
    print(f"DEBUG: load_data_from_json received {len(json_data)} items.")
    
    for item in json_data:
        # Variant A: payload with result wrapper
        if "result" in item and item.get("success", False):
            res = item["result"]
            device_name = res.get("device_name", "Unknown")
            power = float(res.get("power", 0.0))
            voltage = float(res.get("voltage", 0.0))
            current = float(res.get("current", 0.0))
            electricity = float(res.get("electricity", 0.0))
            switch_status = bool(res.get("switch", False))
            ts_iso = res.get("update_time")
            try:
                ts = datetime.strptime(ts_iso, "%Y-%m-%dT%H:%M:%SZ") if ts_iso else datetime.now()
            except Exception:
                ts = datetime.now()
        else:
            # Variant B: direct reading dict
            device_name = item.get("device_name", item.get("device", "Unknown"))
            power = float(item.get("power", 0.0))
            voltage = float(item.get("voltage", 0.0))
            current = float(item.get("current", 0.0))
            electricity = float(item.get("electricity", item.get("energy", 0.0)))
            switch_status = bool(item.get("switch_status", item.get("switch", False)))
            ts_iso = item.get("timestamp", item.get("update_time"))
            try:
                if ts_iso:
                    ts = datetime.fromisoformat(ts_iso.replace('Z', '+00:00')) if 'T' in ts_iso else datetime.strptime(ts_iso, "%Y-%m-%d %H:%M:%S")
                else:
                    ts = datetime.now()
            except Exception:
                ts = datetime.now()

        rows.append({
            "timestamp": ts,
            "device_name": device_name,
            "power": power,
            "voltage": voltage,
            "current": current,
            "electricity": electricity,
            "switch_status": switch_status
        })
    
    if not rows:
        print("DEBUG: No valid rows extracted from payload.")
        raise ValueError("No valid rows in payload")
    
    df = pd.DataFrame(rows)
    df["hour"] = df["timestamp"].dt.hour
    df["date"] = df["timestamp"].dt.date
    print(f"DEBUG: DataFrame loaded with {len(df)} rows.")
    
    # Train anomaly detector with new data snapshot
    anomaly_detector.train_model(json_data)
    return df

def calculate_device_efficiency(device_df: pd.DataFrame, device_name: str) -> str:
    """
    Classify device behavior as 'proper' or 'improper' (no percentage).
    Heuristics:
    - Power consistency when ON (std/mean) should be reasonably stable.
    - Mean ON power should be within a slack-adjusted expected range for the device type (if known).
    - If device is rarely ON, avoid false 'improper' unless range is clearly violated.
    """
    if device_df.empty:
        return "proper"

    on_ratio = float(device_df["switch_status"].sum()) / float(len(device_df))
    on_power = device_df[device_df["switch_status"] == True]["power"]
    if len(on_power) >= 5:
        mean_p = float(on_power.mean())
        std_p = float(on_power.std())
        power_consistency = (100.0 - (std_p / mean_p * 100.0)) if mean_p > 0 else 0.0
    else:
        # Not enough ON samples: assume acceptable stability with low confidence
        power_consistency = 80.0
        mean_p = float(on_power.mean()) if len(on_power) > 0 else 0.0

    # Expected range check (with slack)
    dev_info = DEVICE_CATEGORIES.get(device_name)
    within_range = True
    if dev_info and mean_p > 0:
        min_p = float(dev_info.get("min_power", 0))
        max_p = float(dev_info.get("max_power", 1e9))
        lower = 0.8 * min_p if min_p > 0 else 0
        upper = 1.1 * max_p
        within_range = (mean_p >= lower) and (mean_p <= upper)

    is_proper = (power_consistency >= 50.0) and within_range
    if on_ratio < 0.05 and within_range:
        is_proper = True

    return "proper" if is_proper else "improper"

def generate_device_suggestions(device_name: str, current_power: float, efficiency_status: str, is_active: bool) -> list[str]:
    """
    Suggestions based on categorical efficiency_status ('proper' | 'improper'),
    current power, and whether the device is active.
    """
    suggestions: list[str] = []

    device_strategies = {
        'AC': {
            'improper': [
                "AC behavior appears improper. Clean filters, check refrigerant, or schedule service to stabilize draw.",
                "Use off-peak pre-cooling and raise thermostat by 2°C at peak to reduce spikes."
            ],
            'optimization': [
                "Automate schedules or consider inverter/VRF for smoother, lower peaks."
            ],
            'standby': [f"AC standby ~{current_power:.1f}W detected. Use a smart switch to cut phantom load."]
        },
        'Fridge': {
            'improper': [
                "Fridge pattern looks improper. Check door seals, clean condenser coils, and verify thermostat.",
            ],
            'optimization': [
                "Ensure ventilation clearance and add temperature alerts for proactive upkeep."
            ]
        },
        'Television': {
            'improper': ["TV draw is irregular. Reduce brightness and disable background services."],
            'optimization': ["Enable auto-shutdown after inactivity for steadier usage."],
            'standby': [f"TV standby ~{current_power:.1f}W. Smart strips eliminate phantom load."]
        },
        'Light': {
            'improper': ["Lighting usage inconsistent. Standardize bulbs and apply dimming profiles."],
            'optimization': ["Use quality LEDs and occupancy/daylight sensors for stability."]
        },
        'Fan': {
            'improper': ["Fan load unstable. Check bearings/balance; consider BLDC for smoother control."],
            'optimization': ["Temperature-based automation yields steadier speeds and fewer peaks."]
        },
        'Washing Machine': {
            'improper': ["Irregular draw. Balance loads; inspect for drum friction or clogged filters."],
            'optimization': ["Prefer full loads and cold water cycles for predictable usage."]
        }
    }

    tips = device_strategies.get(device_name, {})
    if efficiency_status == "improper":
        suggestions.extend(tips.get('improper', [
            f"{device_name} behavior appears improper. Do a quick maintenance check and standardize usage."
        ]))
    else:
        suggestions.extend(tips.get('optimization', [
            f"{device_name} looks proper. Add smart automation to smooth peaks and reduce costs."
        ]))

    if not is_active and current_power > 5:
        suggestions.extend(tips.get('standby', [
            f"{device_name} shows standby draw (~{current_power:.1f}W). Automate cut-off to eliminate phantom load."
        ]))

    if len(suggestions) < 3:
        extras = [
            f"IoT monitoring can keep {device_name} stable and alert on drift.",
            f"Link {device_name} schedules to tariff periods to avoid peaks.",
            f"Use anomaly alerts to plan maintenance before performance drops."
        ]
        suggestions.append(extras[hash(device_name) % len(extras)])

    return suggestions[:3]

def generate_device_data() -> dict:
    """Aggregate per-device metrics and analysis for /api/devices"""
    if df is None or df.empty:
        return {}
    
    device_data: dict[str, dict] = {}
    for device_name in df['device_name'].unique():
        device_df = df[df['device_name'] == device_name]
        if device_df.empty:
            continue

        latest = device_df.iloc[-1]
        current_power = float(latest['power'])
        is_active = bool(latest['switch_status'])
        total_energy = float(device_df['electricity'].sum())
        peak_usage = float(device_df['power'].max())
        avg_power = float(device_df['power'].mean())

        efficiency_status = calculate_device_efficiency(device_df, device_name)
        suggestions = generate_device_suggestions(device_name, current_power, efficiency_status, is_active)

        hourly_usage = {int(h): float(v) for h, v in device_df.groupby('hour')['power'].mean().to_dict().items()}

        device_data[device_name] = {
            'currentPower': current_power,
            'totalEnergy': total_energy,
            'peakUsage': peak_usage,
            'averagePower': avg_power,
            'isActive': is_active,
            'efficiencyStatus': efficiency_status,  # categorical
            'suggestions': suggestions,
            'hourlyUsage': hourly_usage,
            'dataPoints': len(device_df)
        }

    return device_data

# ---------------------- Analytics / Helpers ----------------------
SLABS_UPTO_500 = [(100, 0), (200, 2.35), (400, 4.7), (500, 6.3)]
SLABS_ABOVE_500 = [
    (100, 0), (400, 4.7), (500, 6.3), (600, 8.4),
    (800, 9.45), (1000, 10.5), (float("inf"), 11.55)
]

def calculate_bill(units: float) -> dict:
    """Compute slab-based bill"""
    units_int = int(np.ceil(units))
    slabs = SLABS_UPTO_500 if units_int <= 500 else SLABS_ABOVE_500
    
    prev_limit = 0
    details = []
    total = 0.0
    remaining = units_int
    
    for upper, rate in slabs:
        slab_units = min(remaining, upper - prev_limit)
        if slab_units <= 0:
            prev_limit = upper
            continue
        cost = slab_units * rate
        details.append({
            "from": prev_limit + 1,
            "to": upper if upper != float("inf") else "Above",
            "units": slab_units,
            "rate": rate,
            "amount": round(cost, 2)
        })
        total += cost
        remaining -= slab_units
        prev_limit = upper
        if remaining <= 0:
            break
    
    return {"units": units_int, "total_amount": round(total, 2), "breakup": details}

def _period(hour: int) -> str:
    if 5 <= hour <= 10:
        return "morning"
    if 11 <= hour <= 16:
        return "afternoon"
    if 17 <= hour <= 21:
        return "evening"
    return "night"

def compute_peak_period() -> dict[str, float | dict]:
    if df is None:
        return {"error": "data_not_loaded"}
    tot = df.groupby(df["hour"].apply(_period))["electricity"].sum()
    if tot.empty:
        return {"error": "no_energy_column"}
    return {"peak_period": tot.idxmax(), "period_kwh": tot.round(2).to_dict()}

def _train_regressor(data_frame: pd.DataFrame):
    if data_frame.empty:
        return None, None
    data_frame = data_frame.copy()
    data_frame['timestamp'] = pd.to_datetime(data_frame['timestamp'])
    data_frame['electricity'] = pd.to_numeric(data_frame['electricity'])
    daily = data_frame.groupby(data_frame["timestamp"].dt.date)["electricity"].sum().reset_index()
    daily["day_num"] = np.arange(len(daily))
    if len(daily) < 2:
        print("DEBUG: Not enough unique days for prediction model training.")
        return None, None
    model = LinearRegression().fit(daily[["day_num"]], daily["electricity"])
    return model, daily

def predict_energy_consumption(days: int) -> dict:
    """Predict energy consumption for specified number of days"""
    if df is None:
        return {"error": "data_not_loaded"}
    model, daily = _train_regressor(df)
    if model is None:
        return {"error": "not_enough_data_for_prediction"}
    last_day = daily["day_num"].max()
    future_days = np.arange(last_day + 1, last_day + days + 1).reshape(-1, 1)
    predicted_daily = model.predict(future_days)
    total_predicted_kwh = float(predicted_daily.sum())
    bill = calculate_bill(total_predicted_kwh)
    daily_avg_kwh = total_predicted_kwh / days
    daily_avg_cost = bill['total_amount'] / days
    # Rough uncertainty
    if len(daily) > 1:
        historical_std = daily['electricity'].std()
        uncertainty_factor = min(0.15, historical_std / (daily['electricity'].mean() or 1))
        total_predicted_kwh *= (1 + random.uniform(-uncertainty_factor, uncertainty_factor))
        bill = calculate_bill(total_predicted_kwh)
    return {
        "predicted_kwh": round(total_predicted_kwh, 2),
        "bill": bill,
        "daily_avg_kwh": round(daily_avg_kwh, 2),
        "daily_avg_cost": round(daily_avg_cost, 2),
        "prediction_period_days": days,
        "confidence": "high" if len(daily) > 7 else "medium" if len(daily) > 3 else "low"
    }

# ---------------------- Background Monitor ----------------------
def check_for_anomalies():
    """Background task to check for anomalies"""
    while True:
        try:
            if df is not None and len(df) > 0:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM alert_settings WHERE is_enabled = 1")
                    settings = cursor.fetchall()

                    # Build threshold maps
                    device_thresholds: dict[str, dict] = {}
                    global_thresholds: dict[str, float] = {}
                    for setting in settings:
                        s_name = setting['setting_name']
                        d_name = setting['device_name']
                        s_value = setting['threshold_value']
                        if d_name:
                            device_thresholds.setdefault(d_name, {})[s_name] = s_value
                        else:
                            global_thresholds[s_name] = s_value

                    # Prepare recent data window
                    recent_data = []
                    recent_df = df.tail(10)
                    for _, row in recent_df.iterrows():
                        recent_data.append({
                            'device_name': row['device_name'],
                            'device': row['device_name'],
                            'power': float(row['power']),
                            'timestamp': row['timestamp'].isoformat()
                        })

                    anomalies = anomaly_detector.detect_device_specific_anomalies(recent_data, device_thresholds, global_thresholds)

                    if anomalies and email_service:
                        cursor.execute("SELECT * FROM email_recipients WHERE is_active = 1")
                        recipients = cursor.fetchall()
                        for anomaly in anomalies:
                            relevant = []
                            for r in recipients:
                                types = json.loads(r['alert_types']) if r['alert_types'] else []
                                if anomaly['anomaly_type'] in types:
                                    relevant.append(r['email'])

                            if relevant:
                                alert_data = {
                                    'alert_type': anomaly['anomaly_type'],
                                    'device_name': anomaly['device'],
                                    'threshold_value': anomaly['threshold_value'],
                                    'actual_value': anomaly['actual_value'],
                                    'severity': anomaly['severity'],
                                    'unit': anomaly['unit'],
                                    'message': anomaly['description']
                                }
                                result = email_service.send_alert_email(alert_data, relevant)

                                cursor.execute("""
                                    INSERT INTO alert_history 
                                    (alert_type, device_name, threshold_value, actual_value, message, recipients_sent, status)
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    anomaly['anomaly_type'],
                                    anomaly['device'],
                                    anomaly['threshold_value'],
                                    anomaly['actual_value'],
                                    anomaly['description'],
                                    json.dumps(result.get('sent_to', [])),
                                    'sent' if result.get('success') else 'failed'
                                ))
                                conn.commit()
        except Exception as e:
            print(f"Error in anomaly checking: {str(e)}")
        time.sleep(60)

# ---------------------- API Routes ----------------------
@app.route("/api/upload", methods=["POST"])
def r_upload():
    print("DEBUG: /api/upload endpoint hit.")
    try:
        # Support JSON payloads and file uploads (JSON/CSV)
        if request.files and 'file' in request.files:
            file = request.files['file']
            if not file or file.filename == '':
                return jsonify({"error": "No file selected", "status": "error"}), 400
            if file.filename.endswith('.json'):
                payload = json.load(file)
            elif file.filename.endswith('.csv'):
                df_temp = pd.read_csv(file)
                payload = df_temp.to_dict('records')
            else:
                return jsonify({"error": "Unsupported file format. Use JSON or CSV.", "status": "error"}), 400
        else:
            payload = request.get_json(force=True)
            if not payload:
                return jsonify({"error": "No JSON data provided", "status": "error"}), 400

        print(f"DEBUG: Received payload with {len(payload)} items.")
        load_data_from_json(payload)
        print(f"DEBUG: Data loaded. Total rows in df: {len(df) if df is not None else 0}")
        return jsonify({"rows_loaded": len(df), "status": "success"})
    except Exception as e:
        print(f"ERROR: Upload failed: {e}")
        return jsonify({"error": str(e), "status": "error"}), 400

@app.route("/api/peak")
def r_peak():
    return jsonify(compute_peak_period())

@app.route("/api/bill")
def r_bill():
    units = request.args.get("units", type=float)
    if units is None:
        return jsonify({"error": "units query-param missing"}), 400
    return jsonify(calculate_bill(units))

@app.route("/api/predict")
def r_predict():
    """Enhanced prediction endpoint with support for different time periods"""
    days = request.args.get("days", default=30, type=int)
    if days < 1 or days > 365:
        return jsonify({"error": "Days must be between 1 and 365"}), 400
    result = predict_energy_consumption(days)
    return jsonify(result)

@app.route("/api/suggestions")
def r_suggestions():
    if df is None or df.empty:
        return jsonify({"suggestions": [
            "Upload device data to unlock stability checks and actionable insights.",
            "Use schedules to avoid peak periods and smooth out loads.",
            "Enable alerts to catch abnormal draw early and prevent failures."
        ]})
    
    suggestions: list[str] = []

    # Peak usage analysis
    peak_data = compute_peak_period()
    if "peak_period" in peak_data:
        peak = peak_data["peak_period"]
        kwh = peak_data.get("period_kwh", {})
        total = sum(kwh.values()) or 1.0
        if peak == "evening":
            share = (kwh.get("evening", 0) / total) * 100
            suggestions.append(f"Evening peak detected: {share:.1f}% of usage. Shift flexible loads earlier to avoid premiums.")
        elif peak == "afternoon":
            share = (kwh.get("afternoon", 0) / total) * 100
            suggestions.append(f"Afternoon peak: {share:.1f}% of usage. Align with solar where possible to level the load.")
        elif peak == "morning":
            suggestions.append("Morning peak observed. Stagger water heating and heavy appliances to reduce spikes.")

    # Device analytics and stability status
    device_map = generate_device_data()
    total_power = sum(d['currentPower'] for d in device_map.values()) or 1.0
    top = [(name, d) for name, d in device_map.items() if d['currentPower'] > 0.2 * total_power]

    for name, data in top[:2]:
        status = data.get('efficiencyStatus', 'proper')
        power = data['currentPower']
        if status == "improper":
            suggestions.append(f"{name} is a top consumer (~{power:.0f}W) and shows improper behavior. Prioritize maintenance and scheduling.")
        else:
            suggestions.append(f"{name} is a top consumer (~{power:.0f}W) with proper behavior. Consider automation to smooth peaks.")

    # System-wide stability summary
    total_devices = len(device_map)
    improper = [n for n, d in device_map.items() if d.get('efficiencyStatus') == 'improper']
    if total_devices > 0:
        if improper:
            suggestions.append(f"System stability: {len(improper)}/{total_devices} devices flagged as improper. Inspect: {', '.join(improper[:3])}.")
        else:
            suggestions.append("System stability: all observed devices appear proper. Maintain schedules and continue monitoring.")

    if not suggestions:
        suggestions.extend([
            "Devices appear stable. Use automation and schedules to avoid peak tariffs.",
            "Enable email alerts to get notified about abnormal patterns.",
            "Review top consumers and consider staggering their usage."
        ])

    return jsonify({"suggestions": suggestions[:5]})

@app.route("/api/devices")
def r_devices():
    """Get device-specific data and analysis."""
    data = generate_device_data()
    try:
        return app.response_class(
            response=json.dumps(data),
            status=200,
            mimetype='application/json'
        )
    except TypeError as e:
        print(f"ERROR: JSON serialization failed in r_devices: {e}")
        return jsonify({"error": f"Serialization error: {e}", "status": "error"}), 500

@app.route("/api/device/<device_name>")
def r_device_details(device_name):
    """Get detailed analysis for a specific device."""
    if df is None:
        return jsonify({"error": "data_not_loaded"}), 400
    
    device_df = df[df['device_name'] == device_name]
    if device_df.empty:
        return jsonify({"error": f"No data found for device: {device_name}"}), 404
    
    latest = device_df.iloc[-1]
    current_power = float(latest['power'])
    total_energy = float(device_df['electricity'].sum())
    peak_usage = float(device_df['power'].max())
    avg_power = float(device_df['power'].mean())
    efficiency_status = calculate_device_efficiency(device_df, device_name)
    is_active = bool(latest['switch_status'])

    hourly_usage = {int(h): float(v) for h, v in device_df.groupby('hour')['power'].mean().to_dict().items()}
    daily_usage = device_df.groupby(device_df["timestamp"].dt.date)['electricity'].sum().to_dict()
    daily_usage_str = {str(k): float(v) for k, v in daily_usage.items()}

    suggestions = generate_device_suggestions(device_name, current_power, efficiency_status, is_active)

    predicted_kwh = 0.0
    predicted_bill = None
    model, daily_device = _train_regressor(device_df)
    if model is not None and daily_device is not None:
        last_day = daily_device["day_num"].max()
        future = np.arange(last_day + 1, last_day + 31).reshape(-1, 1)
        predicted_kwh = float(model.predict(future).sum())
        predicted_bill = calculate_bill(predicted_kwh)
    
    return jsonify({
        "device_name": device_name,
        "current_power": current_power,
        "total_energy": total_energy,
        "peak_usage": peak_usage,
        "average_power": avg_power,
        "efficiency_status": efficiency_status,  # categorical
        "is_active": is_active,
        "hourly_usage": hourly_usage,
        "daily_usage": daily_usage_str,
        "suggestions": suggestions,
        "data_points": len(device_df),
        "predicted_kwh": round(predicted_kwh, 2),
        "predicted_bill": predicted_bill
    })

@app.route("/api/health")
def health_check():
    try:
        total_records = len(df) if df is not None else 0
        devices_detected = len(generate_device_data()) if df is not None else 0
        return jsonify({
            "status": "healthy",
            "data_loaded": df is not None,
            "total_records": total_records,
            "devices_detected": devices_detected
        })
    except Exception as e:
        app.logger.error(f"Error in health_check: {e}")
        return jsonify({
            "status": "unhealthy",
            "data_loaded": False,
            "error": str(e)
        }), 500

# -------- Alert settings / recipients / history (unchanged logic) --------
@app.route("/api/alert-settings", methods=["GET"])
def get_alert_settings():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM alert_settings ORDER BY device_name, created_at DESC")
            settings = cursor.fetchall()
            return jsonify([{
                "id": s["id"],
                "setting_name": s["setting_name"],
                "device_name": s["device_name"],
                "threshold_value": s["threshold_value"],
                "threshold_type": s["threshold_type"],
                "is_enabled": bool(s["is_enabled"]),
                "created_at": s["created_at"],
                "updated_at": s["updated_at"]
            } for s in settings])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/alert-settings", methods=["POST"])
def create_alert_setting():
    try:
        data = request.get_json()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if data.get('device_name'):
                cursor.execute("SELECT id FROM alert_settings WHERE setting_name = ? AND device_name = ?", 
                               (data['setting_name'], data['device_name']))
            else:
                cursor.execute("SELECT id FROM alert_settings WHERE setting_name = ? AND device_name IS NULL", 
                               (data['setting_name'],))
            existing = cursor.fetchone()
            if existing:
                cursor.execute("""
                    UPDATE alert_settings 
                    SET threshold_value = ?, threshold_type = ?, is_enabled = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (data['threshold_value'], data['threshold_type'], data.get('is_enabled', True), existing['id']))
            else:
                cursor.execute("""
                    INSERT INTO alert_settings (setting_name, device_name, threshold_value, threshold_type, is_enabled)
                    VALUES (?, ?, ?, ?, ?)
                """, (data['setting_name'], data.get('device_name'), data['threshold_value'], data['threshold_type'], data.get('is_enabled', True)))
            conn.commit()
            return jsonify({
                "message": "Alert setting saved successfully",
                "setting_name": data['setting_name'],
                "device_name": data.get('device_name'),
                "threshold_value": data['threshold_value'],
                "threshold_type": data['threshold_type'],
                "is_enabled": data.get('is_enabled', True)
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/alert-settings/<int:setting_id>", methods=["DELETE"])
def delete_alert_setting(setting_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM alert_settings WHERE id = ?", (setting_id,))
            conn.commit()
            if cursor.rowcount == 0:
                return jsonify({"error": "Alert setting not found"}), 404
            return jsonify({"message": "Alert setting deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/email-recipients", methods=["GET"])
def get_email_recipients():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM email_recipients ORDER BY created_at DESC")
            recipients = cursor.fetchall()
            return jsonify([{
                "id": r["id"],
                "email": r["email"],
                "name": r["name"],
                "is_active": bool(r["is_active"]),
                "alert_types": json.loads(r["alert_types"]) if r["alert_types"] else [],
                "created_at": r["created_at"]
            } for r in recipients])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/email-recipients", methods=["POST"])
def add_email_recipient():
    try:
        data = request.get_json()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM email_recipients WHERE email = ?", (data['email'],))
            existing = cursor.fetchone()
            if existing:
                return jsonify({"error": "Email already exists"}), 400
            cursor.execute("""
                INSERT INTO email_recipients (email, name, is_active, alert_types)
                VALUES (?, ?, ?, ?)
            """, (data['email'], data.get('name', ''), data.get('is_active', True),
                  json.dumps(data.get('alert_types', ['peak_power', 'energy_spike', 'device_anomaly']))))
            conn.commit()
            return jsonify({
                "message": "Email recipient added successfully",
                "email": data['email'],
                "name": data.get('name', ''),
                "is_active": data.get('is_active', True)
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/email-recipients/<int:recipient_id>", methods=["PUT"])
def update_email_recipient(recipient_id):
    try:
        data = request.get_json()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE email_recipients 
                SET email = ?, name = ?, is_active = ?, alert_types = ?
                WHERE id = ?
            """, (data.get('email'), data.get('name', ''), data.get('is_active', True),
                  json.dumps(data.get('alert_types', [])), recipient_id))
            conn.commit()
            if cursor.rowcount == 0:
                return jsonify({"error": "Recipient not found"}), 404
            return jsonify({"message": "Email recipient updated successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/email-recipients/<int:recipient_id>", methods=["DELETE"])
def delete_email_recipient(recipient_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM email_recipients WHERE id = ?", (recipient_id,))
            conn.commit()
            if cursor.rowcount == 0:
                return jsonify({"error": "Recipient not found"}), 404
            return jsonify({"message": "Email recipient deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/alert-history", methods=["GET"])
def get_alert_history():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        offset = (page - 1) * per_page
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM alert_history")
            total = cursor.fetchone()["total"]
            cursor.execute("""
                SELECT * FROM alert_history 
                ORDER BY sent_at DESC 
                LIMIT ? OFFSET ?
            """, (per_page, offset))
            alerts = cursor.fetchall()
            return jsonify({
                "alerts": [{
                    "id": a["id"],
                    "alert_type": a["alert_type"],
                    "device_name": a["device_name"],
                    "threshold_value": a["threshold_value"],
                    "actual_value": a["actual_value"],
                    "message": a["message"],
                    "recipients_sent": json.loads(a["recipients_sent"]) if a["recipients_sent"] else [],
                    "sent_at": a["sent_at"],
                    "status": a["status"]
                } for a in alerts],
                "total": total,
                "page": page,
                "per_page": per_page
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/test-alert", methods=["POST"])
def test_alert():
    try:
        data = request.get_json()
        test_email = data.get('email')
        if not test_email:
            return jsonify({"error": "Email address required"}), 400
        if not email_service:
            return jsonify({"error": "Email service not configured"}), 500
        result = email_service.send_test_email(test_email)
        if result.get('success'):
            return jsonify({"message": "Test alert sent successfully", "result": result})
        else:
            return jsonify({"error": "Failed to send test alert", "result": result}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/test-email-connection", methods=["POST"])
def test_email_connection():
    try:
        if not email_service:
            return jsonify({"success": False, "error": "Email service not configured"}), 500
        result = email_service.test_connection()
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/available-devices", methods=["GET"])
def get_available_devices():
    try:
        if df is None or df.empty:
            return jsonify({"devices": []})
        devices = df['device_name'].unique().tolist()
        info = []
        for device in devices:
            device_df = df[df['device_name'] == device]
            latest = device_df.iloc[-1]
            info.append({
                "name": device,
                "current_power": float(latest['power']),
                "is_active": bool(latest['switch_status']),
                "data_points": len(device_df)
            })
        return jsonify({"devices": info})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/device-thresholds", methods=["GET"])
def get_device_thresholds():
    if df is None:
        return jsonify({"error": "No data loaded"}), 400
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT device_name, setting_name, threshold_value, threshold_type, is_enabled
                FROM alert_settings 
                WHERE device_name IS NOT NULL AND is_enabled = 1
            ''')
            device_thresholds = {}
            for row in cursor.fetchall():
                device_name = row[0]
                device_thresholds.setdefault(device_name, []).append({
                    'setting_name': row[1],
                    'threshold_value': row[2],
                    'threshold_type': row[3],
                    'is_enabled': bool(row[4])
                })
            result = {}
            for device in df['device_name'].unique():
                device_data = df[df['device_name'] == device]
                current_power = float(device_data['power'].iloc[-1]) if len(device_data) > 0 else 0
                current_energy = float(device_data['electricity'].iloc[-1]) if len(device_data) > 0 else 0
                thresholds = device_thresholds.get(device, [])
                alerts = []
                for t in thresholds:
                    if t['setting_name'] == 'peak_power':
                        current_value = current_power
                    elif t['setting_name'] == 'energy_spike':
                        current_value = current_power
                    else:
                        current_value = current_energy
                    is_exceeded = (
                        (t['threshold_type'] == 'greater_than' and current_value > t['threshold_value']) or
                        (t['threshold_type'] == 'less_than' and current_value < t['threshold_value']) or
                        (t['threshold_type'] == 'equal_to' and abs(current_value - t['threshold_value']) < 0.01)
                    )
                    if is_exceeded:
                        alerts.append({
                            'type': t['setting_name'],
                            'threshold': t['threshold_value'],
                            'current': current_value
                        })
                result[device] = {
                    'current_power': current_power,
                    'current_energy': current_energy,
                    'thresholds': thresholds,
                    'alerts': alerts,
                    'is_active': current_power > 0
                }
            return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------------- Main ----------------------
if __name__ == "__main__":
    init_database()
    # Start anomaly detection in background
    anomaly_thread = threading.Thread(target=check_for_anomalies, daemon=True)
    anomaly_thread.start()

    print("🚀 Smart Energy Tracker Backend Starting...")
    port = int(os.environ.get("PORT", 5000))
    print(f"📊 API available at: http://0.0.0.0:{port}/api/")
    print("🤖 Device monitoring and suggestions enabled")
    if email_service and getattr(email_service, "config_valid", False):
        print("✅ Email service configured and ready")
    else:
        print("⚠️  Email service not configured or invalid")
    app.run(host="0.0.0.0", port=port)
