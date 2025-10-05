# space_alert_bot.py
# FINAL CODE: Fetches NOAA Kp, NASA Flares, and NASA CME data, calculates risk, and sends WhatsApp alerts.

import requests, time, json, os
from datetime import datetime, timezone
from twilio.rest import Client
from dotenv import load_dotenv
import schedule 

# --- Initialization ---
load_dotenv()  # Load keys from the .env file

# --- Configuration (loaded from .env) ---
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM")
TWILIO_TO = os.getenv("TWILIO_TO")

NASA_API_KEY = os.getenv("NASA_API_KEY")
CACHE_FILE = "last_alert_cache.json"

# API Endpoints
NOAA_KP_URL = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
# We define the NASA URLs here, using the variable {NASA_API_KEY} loaded from .env
NASA_FLARE_URL = f"https://api.nasa.gov/DONKI/FLR?api_key={NASA_API_KEY}" 
NASA_CME_URL = f"https://api.nasa.gov/DONKI/CMEAnalysis?api_key={NASA_API_KEY}" 


# --- Localization phrases (for WhatsApp message content) ---
PHRASES = {
    "en": {
        "title_red": "⚠ High Space Risk — Action Needed!",
        "title_yellow": "⚠ Moderate Space Risk — Caution",
        "title_green": "✅ Space weather normal",
        "gps_advice": "GPS & navigation may be inaccurate. Avoid precision machine work (seeding, mapping).",
        "power_advice": "Power or communication disruptions possible — keep pumps/devices charged or on standby.",
        "flare_risk": "Solar Flare/CME Risk: Radio Blackouts & communication loss possible.",
        "when": "Observed at"
    },
    "ml": {  # Malayalam example
        "title_red": "⚠ സൂര്യ പ്രവൃത്തിയൂൻ ഉയർന്നിരിക്കുന്നു — ശ്രദ്ധ വേണം",
        "title_yellow": "⚠ മിതമായ സൂര്യ പ്രവൃത്തി — ജാഗ്രത",
        "title_green": "✅ സാധാരണ സ്ഫേസ് വേതർ",
        "gps_advice": "GPS ശതം കൃത്യമായിരിക്കില്ല. യന്ത്രവലംബ ജോലി മാറ്റിയിടുക.",
        "power_advice": "വൈദ്യുതി/കമ്യൂണിക്കേഷൻ പ്രശ്നം സാധ്യത — പമ്പുകൾ ചാർജ് ചെയ്യുക.",
        "flare_risk": "സോളാർ ഫ്ലെയർ/CME റിസ്ക്: റേഡിയോ തടസ്സങ്ങൾ സാധ്യത.",
        "when": "കണ്ടെടുത്തത്"
    }
}

# --- Utilities ---
def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            return json.load(open(CACHE_FILE, "r"))
        except:
            return {}
    return {}

def save_cache(d):
    json.dump(d, open(CACHE_FILE, "w"), indent=2)

# --- Data Fetching Functions ---

def fetch_latest_kp():
    """Fetches the latest Kp index from NOAA."""
    r = requests.get(NOAA_KP_URL, timeout=15)
    r.raise_for_status()
    arr = r.json()
    if not arr:
        return None
    
    latest = arr[0]
    kp = None
    for key in ("kp_index", "kp", "Kp"):
        if key in latest:
            kp = latest[key]
            break
            
    t = latest.get("time_tag") or latest.get("date_time") or latest.get("timestamp") or latest.get("date")
    return {"kp": float(kp) if kp is not None else None, "time": t, "raw": latest}


def fetch_latest_nasa_flare():
    """Fetches the latest solar flare data from NASA DONKI."""
    url = NASA_FLARE_URL 
    
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        flares = r.json()
        
        if not flares:
            return None 
            
        latest_flare = flares[0] 
        flare_class = latest_flare.get("classType", "B0.0")[0] 
        time_tag = latest_flare.get("beginTime")
        
        return {"class": flare_class, "time": time_tag, "raw": latest_flare}
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching NASA flare data: {e}")
        return None

def fetch_latest_cme():
    """Fetches the latest Coronal Mass Ejection (CME) data from NASA DONKI."""
    url = NASA_CME_URL 
    
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        cme_analyses = r.json()
        
        if not cme_analyses:
            return None 
            
        for analysis in cme_analyses:
            is_most_accurate = analysis.get("isMostAccurate")
            speed = analysis.get("speed")
            
            if is_most_accurate and speed and speed > 600:
                return {"speed": speed, "raw": analysis}
                
        return None # No significant, earth-directed CME found
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching NASA CME data: {e}")
        return None

# --- Risk Scoring ---

def score_risk(kp_value, flare_class=None, cme_speed=None): 
    """Scores overall risk based on Kp, Flare Class, and CME Speed."""
    
    # --- 1. Kp Score (Geomagnetic Storm Risk) ---
    kp_risk = "green"
    if kp_value is not None:
        kp = float(kp_value)
        # --- NORMAL MODE THRESHOLDS ---
        if kp >= 6.0:  # RED alert requires Kp 6.0
            kp_risk = "red"
        elif kp >= 3.0: # YELLOW alert requires Kp 3.0
            kp_risk = "yellow"
        # --- END NORMAL MODE ---

    # --- 2. Flare Score (Radio Blackout/GPS Signal Risk) ---
    flare_risk = "green"
    if flare_class == 'X':
        flare_risk = "red" 
    elif flare_class == 'M':
        flare_risk = "yellow" 
        
    # --- 3. CME Score (Direct Impact Risk) ---
    cme_risk = "green"
    if cme_speed is not None and cme_speed > 1000: 
        cme_risk = "red"
    elif cme_speed is not None and cme_speed > 600: 
        cme_risk = "yellow"
        
    # --- 4. Final Combined Risk (Highest level wins) ---
    if kp_risk == "red" or flare_risk == "red" or cme_risk == "red":
        return "red"
    if kp_risk == "yellow" or flare_risk == "yellow" or cme_risk == "yellow":
        return "yellow"
    
    return "green"

# --- Message Formatting and Sending ---

def format_message(risk, kp_val, time_str, flare_class=None, cme_speed=None, lang="en"): 
    p = PHRASES.get(lang, PHRASES["en"])
    
    if risk == "red":
        title = p["title_red"]
    elif risk == "yellow":
        title = p["title_yellow"]
    else:
        title = p["title_green"]

    body_lines = [
        f"{title}",
        f"{p['when']}: {time_str} (Kp={kp_val})"
    ]
    
    if flare_class and flare_class in ('X', 'M'):
        body_lines[-1] += f" | Flare Class: {flare_class}"
    
    if cme_speed:
        body_lines[-1] += f" | CME Speed: {cme_speed} km/s"
        
    if risk == "red":
        body_lines.append(p["gps_advice"])
        body_lines.append(p["power_advice"])
        body_lines.append(p["flare_risk"]) 
            
    elif risk == "yellow":
        body_lines.append(p["gps_advice"])
        if flare_class == 'M' or cme_speed:
            body_lines.append(p["flare_risk"])
    else:
        body_lines.append("No immediate action needed.")

    return "\n".join(body_lines)

def send_whatsapp(message):
    client = Client(TWILIO_SID, TWILIO_AUTH)
    msg = client.messages.create(
        body=message,
        from_=TWILIO_WHATSAPP_FROM,
        to=TWILIO_TO
    )
    return msg.sid

# --- Main check function ---
def check_and_alert():
    try:
        # 1. Fetch NOAA Kp Data
        kp_data = fetch_latest_kp()
        if not kp_data:
            print("No NOAA Kp data")
            return

        kp = kp_data["kp"]
        t = kp_data["time"] or datetime.now(timezone.utc).isoformat()
        
        # 2. Fetch NASA Flare Data 
        flare_data = fetch_latest_nasa_flare()
        flare_class = flare_data['class'] if flare_data else None

        # 3. Fetch NASA CME Data (NEW STEP)
        cme_data = fetch_latest_cme()
        cme_speed = cme_data['speed'] if cme_data else None
        
        # 4. Score Risk using ALL three sources (UPDATED CALL)
        risk = score_risk(kp, flare_class, cme_speed) 

        cache = load_cache()
        last = cache.get("last_kp")
        
        should_send = False
        if not last or risk != cache.get("last_risk"):
            should_send = True

        # --- Dashboard/Cache Saving Logic ---
        
        # 1. Create a clean, readable timestamp 
        clean_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        current_status = {
            "risk": risk,
            "kp_value": kp,
            "flare_class": flare_class,
            "cme_speed": cme_speed,
            "time": clean_time 
        }
        
        # Save current status to a file for the web dashboard (app.py)
        with open("status.json", "w") as f:
            json.dump(current_status, f, indent=2)
        # --- End Dashboard/Cache Saving Logic ---


        if should_send:
            msg_en = format_message(risk, kp, t, flare_class, cme_speed, lang="en") 
            msg_ml = format_message(risk, kp, t, flare_class, cme_speed, lang="ml") 
            
            full_msg = f"{msg_en}\n\n---\n{msg_ml}"
            sid = send_whatsapp(full_msg)
            
            print("Sent:", sid, "Risk:", risk)
            # Update cache only after sending the message
            cache["last_kp"] = kp
            cache["last_time"] = t
            cache["last_risk"] = risk
            cache["last_sent_sid"] = sid
            cache["last_sent_at"] = datetime.now(timezone.utc).isoformat()
            save_cache(cache)
        else:
            print(f"No alert (no change). Kp: {kp}, Flare: {flare_class}, CME Speed: {cme_speed} km/s") 
            
    except Exception as e:
        print("Error in check:", e)

# --- Run as loop for demo; in production use scheduler (cron) ---
if __name__ =="__main__":
    # 1. Run immediately on startup
    check_and_alert()
    
    # 2. Schedule checks every 5 minutes
    schedule.every(5).minutes.do(check_and_alert)
    
    print("\n--- Starting Continuous Monitoring Loop ---")
    print("Checking for space weather updates every 5 minutes...")
    
    while True:
        schedule.run_pending()
        time.sleep(1)
