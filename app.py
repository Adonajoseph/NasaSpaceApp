from flask import Flask, render_template, jsonify
import json
import os

app = Flask(__name__)
STATUS_FILE = "status.json"

@app.route('/')
def index():
    """Renders the main dashboard page, reading data from the status file."""
    try:
        # Load the status data saved by space_alert_bot.py
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, 'r') as f:
                status = json.load(f)
        else:
            # Default state if the backend hasn't run yet
            status = {"risk": "INITIALIZING", "kp_value": "N/A", "flare_class": "N/A", "cme_speed": "N/A", "time": "No Data"}
    except Exception:
        # State if the file is corrupted
        status = {"risk": "ERROR", "kp_value": "N/A", "flare_class": "N/A", "cme_speed": "N/A", "time": "Error Reading Data"}
        
    # Passes the status data to the HTML template for display
    return render_template('dashboard.html', status=status)

@app.route('/data')
def get_data():
    try:
        with open(STATUS_FILE, 'r') as f:
            status = json.load(f)
            return jsonify(status)
    except FileNotFoundError:
        return jsonify({"error": "No data file found"}), 404

if __name__ == '__main__':
    # Running on port 8000 for better compatibility
    app.run(debug=True, use_reloader=False, port=8000)
