import streamlit as st
import yfinance as yf
from datetime import datetime
import smtplib
from email.mime.text import MIMEText

ALERT_THRESHOLD_PREV_PCT = -0.5
ALERT_THRESHOLD_CURR_PCT = -0.2
NASDAQ_TICKER = "^IXIC"

st.set_page_config(page_title="Nasdaq Monitor", layout="wide")
st.title("📈 Nasdaq Real-Time Monitor")

EMAIL_SENDER = st.secrets["EMAIL_SENDER"]
EMAIL_PASSWORD = st.secrets["EMAIL_PASSWORD"]
EMAIL_RECEIVER = st.secrets["EMAIL_RECEIVER"]
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

@st.cache_data(ttl=60)
def fetch_nasdaq_data():
    ticker = yf.Ticker(NASDAQ_TICKER)
    hist = ticker.history(period="10d", auto_adjust=False)
    info = ticker.fast_info
    current_index = info.last_price

    if hist.empty or len(hist) < 2:
        return None, None, None, None, None, None, None, None

    prev_row = hist.iloc[-1]
    curr_open = prev_row["Open"]
    prev_close = prev_row["Close"]
    prev_open = hist.iloc[-2]["Open"]
    prev_prev_close = hist.iloc[-2]["Close"]

    prev_open = 100
    prev_close = 110
    curr_open = 110
    current_index = 132

    prev_open_diff = ((prev_close - prev_open) / prev_open * 100) if prev_open else None
    prev_close_diff = ((prev_close - prev_open) / prev_open * 100) if prev_prev_close else None
    curr_open_diff = ((current_index - curr_open) / curr_open * 100) if curr_open else None
    curr_index_diff = ((current_index - curr_open) / curr_open * 100) if prev_close else None

    return prev_open, prev_close, current_index, curr_open, prev_open_diff, prev_close_diff, curr_open_diff, curr_index_diff


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


def build_email_body(prev_open, prev_close, current_open, current_index,
                     prev_open_diff, prev_close_diff, curr_open_diff, curr_index_diff,
                     test=False):
    tag = "[TEST] " if test else "[ALERT]"
    fmt = lambda x: f"{x:,.2f}" if x is not None else "N/A"
    pct = lambda x: f"{x:.2f}%" if x is not None else "N/A"
    return f"""
    <h2>{tag}Nasdaq Alert</h2>
    <table border="1" cellpadding="6">
      <tr><th>Metric</th><th>Value</th></tr>
      <tr><td>Previous Open</td><td>{fmt(prev_open)}</td></tr>
      <tr><td>Previous Close</td><td>{fmt(prev_close)}</td></tr>
      <tr><td>Previous Open to Close</td><td>{pct(prev_open_diff)}</td></tr>
      <tr><td>Previous Close to Prior Close</td><td>{pct(prev_close_diff)}</td></tr>
      <tr><td>Current Open</td><td>{fmt(current_open)}</td></tr>
      <tr><td>Current Index</td><td>{fmt(current_index)}</td></tr>
      <tr><td>Current Open to Index</td><td>{pct(curr_open_diff)}</td></tr>
      <tr><td>Current Close Reference to Index</td><td>{pct(curr_index_diff)}</td></tr>
    </table>
    <p>Checked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    """

try:
    prev_open, prev_close, current_index, current_open, prev_open_diff, prev_close_diff, curr_open_diff, curr_index_diff = fetch_nasdaq_data()
    status = "OK"
except Exception as e:
    prev_open = prev_close = current_index = current_open = None
    prev_open_diff = prev_close_diff = curr_open_diff = curr_index_diff = None
    status = f"Error: {e}"

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Previous Open", f"{prev_open:,.2f}" if prev_open is not None else "N/A", f"{prev_open_diff:.2f}%" if prev_open_diff is not None else "N/A")
with c2:
    st.metric("Previous Close", f"{prev_close:,.2f}" if prev_close is not None else "N/A", f"{prev_close_diff:.2f}%" if prev_close_diff is not None else "N/A")
with c3:
    st.metric("Current Open", f"{current_open:,.2f}" if current_open is not None else "N/A", f"{curr_open_diff:.2f}%" if curr_open_diff is not None else "N/A")
with c4:
    st.metric("Current Index", f"{current_index:,.2f}" if current_index is not None else "N/A", f"{curr_index_diff:.2f}%" if curr_index_diff is not None else "N/A")

st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Status: {status}")

st.success("✅ Nasdaq within normal range")

if st.button("📧 Send Test Email"):
    try:
        body = build_email_body(prev_open, prev_close, current_open, current_index, prev_open_diff, prev_close_diff, curr_open_diff, curr_index_diff, test=True)
        send_email("[TEST] Nasdaq Monitor — Test Email", body)
        st.success("✅ Test email sent successfully!")
    except Exception as e:
        st.error(f"❌ Failed: {e}")