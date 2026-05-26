# nasdaq_monitor.py
# Requirements: pip install flask yfinance ollama apscheduler

import smtplib
import threading
from email.mime.text import MIMEText
from datetime import datetime

import yfinance as yf
from flask import Flask, jsonify, render_template_string
from apscheduler.schedulers.background import BackgroundScheduler
import ollama

# ─────────────────────────────────────────
#  CONSTANTS — edit these before running
# ─────────────────────────────────────────
# Separate thresholds for previous and current sessions (in percent)
ALERT_THRESHOLD_PREV_PCT = -0.5   # trigger when previous session change % <= this value
ALERT_THRESHOLD_CURR_PCT = -0.2   # trigger when current session change % <= this value

NASDAQ_TICKER = "^IXIC"           # Nasdaq Composite
POLL_INTERVAL_SECONDS = 60        # check every 60 seconds

# Email config (use Gmail App Password or SMTP relay)
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_SENDER = "jaymodi2026@gmail.com   "
EMAIL_PASSWORD = "nbyoxzxmfixxcfhe"        # Gmail App Password
EMAIL_RECEIVER = "jpmodi@gmail.com"


OLLAMA_MODEL ="gemma4:e4b" 
#OLLAMA_MODEL = "deepseek-r1:8b" #"gemma4" 
   # must be pulled: ollama pull gemma4
# ─────────────────────────────────────────

app = Flask(__name__)

# Shared state
state = {
    "prev_close": None,
    "current_price": None,
    "prev_change_pct": None,
    "current_change_pct": None,
    "last_updated": None,
    "alert_sent": False,
    "status": "Initializing...",
}

# ── Data Fetching ──────────────────────────────────────────────────────────────

def fetch_nasdaq_data():
    """Fetch previous close and current/last price from Yahoo Finance."""
    ticker = yf.Ticker(NASDAQ_TICKER)
    info = ticker.fast_info
    prev_close = info.previous_close
    prev_open = info.open
    current = info.last_price

    prev_change_pct = None
    current_change_pct = None

    # Defensively handle missing values
    if prev_open is not None and prev_open != 0:
        # Previous session change vs open
        prev_change_pct = ((prev_close - prev_open) / prev_open) * 100

    if prev_close is not None and prev_close != 0:
        # Current session change vs previous close
        current_change_pct = ((current - prev_close) / prev_close) * 100

    return prev_close, current, prev_change_pct, current_change_pct

# ── Email ──────────────────────────────────────────────────────────────────────

def send_email(subject: str, body: str):
    msg = MIMEText(body, "html")
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())

def build_email_body(prev_close, current, prev_change_pct, current_change_pct, test=False):
    tag = "[TEST] " if test else "[ALERT] "

    # Fallback text for None values
    prev_close_str = f"{prev_close:,.2f}" if prev_close is not None else "N/A"
    current_str = f"{current:,.2f}" if current is not None else "N/A"
    prev_pct_str = f"{prev_change_pct:.2f}%" if prev_change_pct is not None else "N/A"
    curr_pct_str = f"{current_change_pct:.2f}%" if current_change_pct is not None else "N/A"

    prev_color = "red" if (prev_change_pct is not None and prev_change_pct <= ALERT_THRESHOLD_PREV_PCT) else "green"
    curr_color = "red" if (current_change_pct is not None and current_change_pct <= ALERT_THRESHOLD_CURR_PCT) else "green"

    return f"""
    <h2>{tag}Nasdaq Alert</h2>
    <table border="1" cellpadding="6">
      <tr><th>Metric</th><th>Value</th><th>Threshold</th></tr>

      <tr>
        <td>Previous Close</td>
        <td>{prev_close_str}</td>
        <td>-</td>
      </tr>

      <tr>
        <td>Prev Session Change</td>
        <td style="color:{prev_color}">{prev_pct_str}</td>
        <td>{ALERT_THRESHOLD_PREV_PCT}%</td>
      </tr>

      <tr>
        <td>Current Price</td>
        <td>{current_str}</td>
        <td>-</td>
      </tr>

      <tr>
        <td>Current Session Change</td>
        <td style="color:{curr_color}">{curr_pct_str}</td>
        <td>{ALERT_THRESHOLD_CURR_PCT}%</td>
      </tr>
    </table>
    <p>Checked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    """

# ── Monitor Job (runs every minute) ───────────────────────────────────────────

def monitor_nasdaq():
    try:
        prev_close, current, prev_chg, curr_chg = fetch_nasdaq_data()
        state.update({
            "prev_close": prev_close,
            "current_price": current,
            "prev_change_pct": prev_chg,
            "current_change_pct": curr_chg,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "OK",
        })

        # Alert condition: BOTH sessions down beyond their respective thresholds
        if (
            prev_chg is not None
            and curr_chg is not None
            and prev_chg <= ALERT_THRESHOLD_PREV_PCT
            and curr_chg <= ALERT_THRESHOLD_CURR_PCT
            and not state["alert_sent"]
        ):
            body = build_email_body(prev_close, current, prev_chg, curr_chg)
            send_email("🚨 Nasdaq Double-Drop Alert", body)
            state["alert_sent"] = True
            state["status"] = "ALERT SENT"

        # Reset alert flag once current session recovers beyond its own threshold
        if curr_chg is not None and curr_chg > ALERT_THRESHOLD_CURR_PCT:
            state["alert_sent"] = False

    except Exception as e:
        state["status"] = f"Error: {e}"

# ── Flask Routes ───────────────────────────────────────────────────────────────

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>Nasdaq Monitor</title>
  <meta http-equiv="refresh" content="60">
  <style>
    body { font-family: Arial, sans-serif; background: #0d0d0d; color: #e0e0e0; padding: 30px; }
    h1   { color: #00d4ff; }
    .card { background: #1a1a2e; border-radius: 10px; padding: 20px; margin: 10px 0; display: inline-block; min-width: 220px; }
    .label  { font-size: 12px; color: #888; text-transform: uppercase; }
    .value  { font-size: 32px; font-weight: bold; }
    .red    { color: #ff4d4d; }
    .green  { color: #4dff88; }
    .threshold { color: #ffcc00; font-size: 14px; margin-top: 6px; }
    button  { margin: 6px; padding: 10px 18px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; }
    .btn-test  { background: #0077cc; color: white; }
    .btn-llm   { background: #5500cc; color: white; }
    #llm-response { background: #111; padding: 15px; border-radius: 8px; margin-top: 12px; white-space: pre-wrap; min-height: 40px; }
    .status-ok    { color: #4dff88; }
    .status-alert { color: #ff4d4d; font-weight: bold; }
  </style>
  <script>
    async function sendTestEmail() {
      const r = await fetch('/test_email'); const d = await r.json();
      alert(d.message);
    }
    async function testLLM() {
      document.getElementById('llm-response').innerText = 'Calling Gemma 4...';
      const r = await fetch('/test_llm'); const d = await r.json();
      document.getElementById('llm-response').innerText = d.response || d.error;
    }
  </script>
</head>
<body>
  <h1>📈 Nasdaq Real-Time Monitor</h1>

  <div class="card">
    <div class="label">Previous Close</div>
    <div class="value">{{ prev_close }}</div>
    <div class="threshold">Prev threshold: {{ threshold_prev }}%</div>
    <div class="label">Prev Session Δ</div>
    <div class="value {{ 'red' if prev_chg_color == 'red' else 'green' }}">{{ prev_chg }}</div>
  </div>

  &nbsp;

  <div class="card">
    <div class="label">Current Price</div>
    <div class="value">{{ current }}</div>
    <div class="threshold">Curr threshold: {{ threshold_curr }}%</div>
    <div class="label">Current Session Δ</div>
    <div class="value {{ 'red' if curr_chg_color == 'red' else 'green' }}">{{ curr_chg }}</div>
  </div>

  <p>Last updated: <b>{{ last_updated }}</b> &nbsp;|&nbsp;
     Status: <span class="{{ 'status-alert' if 'ALERT' in status else 'status-ok' }}">{{ status }}</span></p>

  <button class="btn-test" onclick="sendTestEmail()">📧 Send Test Email</button>
  <button class="btn-llm"  onclick="testLLM()">🤖 Test Gemma 4 via Ollama</button>

  <div id="llm-response">LLM response will appear here...</div>
</body>
</html>
"""

@app.route("/")
def index():
    s = state

    def fmt_pct(v):
        return f"{v:.2f}%" if v is not None else "N/A"

    def color_prev(v):
        return "red" if v is not None and v <= ALERT_THRESHOLD_PREV_PCT else "green"

    def color_curr(v):
        return "red" if v is not None and v <= ALERT_THRESHOLD_CURR_PCT else "green"

    return render_template_string(
        HTML_TEMPLATE,
        prev_close=f"{s['prev_close']:,.2f}" if s["prev_close"] is not None else "N/A",
        current=f"{s['current_price']:,.2f}" if s["current_price"] is not None else "N/A",
        prev_chg=fmt_pct(s["prev_change_pct"]),
        curr_chg=fmt_pct(s["current_change_pct"]),
        prev_chg_color=color_prev(s["prev_change_pct"]),
        curr_chg_color=color_curr(s["current_change_pct"]),
        last_updated=s["last_updated"] or "—",
        status=s["status"],
        threshold_prev=ALERT_THRESHOLD_PREV_PCT,
        threshold_curr=ALERT_THRESHOLD_CURR_PCT,
    )

@app.route("/test_email")
def test_email():
    try:
        s = state
        body = build_email_body(
            s["prev_close"], s["current_price"],
            s["prev_change_pct"], s["current_change_pct"], test=True
        )
        send_email("[TEST] Nasdaq Monitor — Test Email", body)
        return jsonify({"message": "✅ Test email sent successfully!"})
    except Exception as e:
        return jsonify({"message": f"❌ Failed: {e}"})

@app.route("/test_llm")
def test_llm():
    """Test a call to Gemma 4 via local Ollama."""
    try:
        s = state
        curr_price_str = f"{s['current_price']:,.2f}" if s["current_price"] is not None else "N/A"
        prev_close_str = f"{s['prev_close']:,.2f}" if s["prev_close"] is not None else "N/A"
        curr_chg_str = f"{s['current_change_pct']:.2f}%" if s["current_change_pct"] is not None else "N/A"

        prompt = (
            f"The Nasdaq Composite is currently at {curr_price_str} "
            f"(previous close: {prev_close_str}, "
            f"change: {curr_chg_str}). "
            "In 2-3 sentences, briefly comment on this market move."
        )
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt} 
                     ]
        )
        return jsonify({"response": response["message"]["content"]})
    except Exception as e:
        return jsonify({"error": str(e)})

# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Run first fetch immediately
    monitor_nasdaq()

    # Schedule every POLL_INTERVAL_SECONDS
    scheduler = BackgroundScheduler()
    scheduler.add_job(monitor_nasdaq, "interval", seconds=POLL_INTERVAL_SECONDS)
    scheduler.start()

    print("✅ Nasdaq Monitor running at http://127.0.0.1:5000")
    app.run(debug=False, use_reloader=False, port=5000)