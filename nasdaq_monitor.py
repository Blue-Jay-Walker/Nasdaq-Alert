# nasdaq_monitor.py (Streamlit version with secrets) - FIXED V2
import streamlit as st
import yfinance as yf
from datetime import datetime
import smtplib
from email.mime.text import MIMEText


# ─────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────
ALERT_THRESHOLD_PREV_PCT = -0.5
ALERT_THRESHOLD_CURR_PCT = -0.2
NASDAQ_TICKER = "^IXIC"


# ── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Nasdaq Monitor", layout="wide")
st.title("📈 Nasdaq Real-Time Monitor")


# ── Load Secrets ─────────────────────────────────────────────────────────────
EMAIL_SENDER = st.secrets["EMAIL_SENDER"]
EMAIL_PASSWORD = st.secrets["EMAIL_PASSWORD"]
EMAIL_RECEIVER = st.secrets["EMAIL_RECEIVER"]
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


# ── Data Fetching ────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def fetch_nasdaq_data():
    """Fetch Nasdaq data and calculate change percentages correctly.
    
    prev_change_pct: Day-over-day change for the PREVIOUS completed session
                     (e.g., May 28 close vs May 27 close)
    current_change_pct: Intraday change for CURRENT session 
                        (e.g., current price vs May 28 close)
    """
    ticker = yf.Ticker(NASDAQ_TICKER)
    
    # Get historical daily closes - this is the cleanest approach
    hist = ticker.history(period="10d")
    
    if len(hist) < 3:
        return None, None, None, None
    
    # Get the last 3 closing prices
    # hist.iloc[-1] = most recent CLOSE (yesterday's close if market closed, or today's close if closed)
    # hist.iloc[-2] = previous session close  
    # hist.iloc[-3] = session before that
    
    # The most recent completed session's close
    most_recent_close = hist["Close"].iloc[-1]
    # The session before that (2 days ago)
    prev_session_close = hist["Close"].iloc[-2]
    
    # Current price (live/intraday)
    # Use fast_info for real-time current price
    info = ticker.fast_info
    current_price = info.last_price
    prev_close = info.previous_close
    
    prev_change_pct = None
    current_change_pct = None
    
    # Prev session change: (most_recent_close - prev_session_close) / prev_session_close
    # This is the actual day-over-day change for the last completed session
    if len(hist) >= 2 and most_recent_close != 0:
        prev_change_pct = ((most_recent_close - prev_session_close) / prev_session_close) * 100
    
    # Current session change: (current_price - prev_close) / prev_close
    # This is the intraday change for today's session
    if prev_close is not None and prev_close != 0:
        current_change_pct = ((current_price - prev_close) / prev_close) * 100
    
    return prev_close, current_price, prev_change_pct, current_change_pct


# ── Email Functions ──────────────────────────────────────────────────────────
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
    tag = "[TEST] " if test else "[ALERT]"
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
      <tr><td>Previous Close</td><td>{prev_close_str}</td><td>-</td></tr>
      <tr><td style="color:{prev_color}">Prev Session Change</td><td>{prev_pct_str}</td><td>{ALERT_THRESHOLD_PREV_PCT}%</td></tr>
      <tr><td>Current Price</td><td>{current_str}</td><td>-</td></tr>
      <tr><td style="color:{curr_color}">Current Session Change</td><td>{curr_pct_str}</td><td>{ALERT_THRESHOLD_CURR_PCT}%</td></tr>
    </table>
    <p>Checked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    """


# ── Fetch Data ───────────────────────────────────────────────────────────────
try:
    prev_close, current, prev_chg, curr_chg = fetch_nasdaq_data()
    status = "OK"
except Exception as e:
    prev_close, current, prev_chg, curr_chg = None, None, None, None
    status = f"Error: {e}"


# ── Display Metrics ──────────────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.metric(
        label="Previous Close",
        value=f"{prev_close:,.2f}" if prev_close else "N/A",
        delta=f"{prev_chg:.2f}%" if prev_chg is not None else "N/A"
    )

with col2:
    st.metric(
        label="Current Price",
        value=f"{current:,.2f}" if current else "N/A",
        delta=f"{curr_chg:.2f}%" if curr_chg is not None else "N/A"
    )

st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Status: {status}")


# ── Alert Check ──────────────────────────────────────────────────────────────
if (prev_chg is not None and curr_chg is not None and
    prev_chg <= ALERT_THRESHOLD_PREV_PCT and
    curr_chg <= ALERT_THRESHOLD_CURR_PCT):
    st.error("🚨 ALERT: Nasdaq dropped below both thresholds!")
    if st.button("Send Alert Email"):
        try:
            body = build_email_body(prev_close, current, prev_chg, curr_chg)
            send_email("🚨 Nasdaq Double-Drop Alert", body)
            st.success("✅ Alert email sent!")
        except Exception as e:
            st.error(f"❌ Failed to send email: {e}")
else:
    st.success("✅ Nasdaq within normal range")


# ── Test Email Button ────────────────────────────────────────────────────────
if st.button("📧 Send Test Email"):
    try:
        body = build_email_body(prev_close, current, prev_chg, curr_chg, test=True)
        send_email("[TEST] Nasdaq Monitor — Test Email", body)
        st.success("✅ Test email sent successfully!")
    except Exception as e:
        st.error(f"❌ Failed: {e}")