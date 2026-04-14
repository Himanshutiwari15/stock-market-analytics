"""
src/alerts/email_alerter.py — Gmail SMTP email alerter
=======================================================
WHAT THIS MODULE DOES
---------------------
Sends an HTML email via Gmail's SMTP server whenever anomalies are detected.

HOW GMAIL SMTP WORKS
--------------------
SMTP (Simple Mail Transfer Protocol) is the protocol used to send email.
Gmail exposes an SMTP server at smtp.gmail.com:587.

The connection sequence:
  1. Connect to smtp.gmail.com on port 587 (plain TCP)
  2. Send EHLO — introduces ourselves to the server
  3. STARTTLS — upgrade the connection to encrypted TLS
  4. LOGIN — authenticate with email + App Password
  5. SENDMAIL — send the message
  6. QUIT — close the connection

IMPORTANT: APP PASSWORDS VS REAL GMAIL PASSWORD
------------------------------------------------
You MUST use a Gmail App Password, NOT your real Gmail password.
Why?
  - Google blocks "less secure app" direct password auth for most accounts.
  - An App Password is a 16-character one-time credential that only
    grants SMTP access — it cannot read your emails or change your
    account settings. If it leaks, you revoke just that one credential.

How to create one:
  1. Enable 2-Step Verification on your Google account
  2. Go to: https://myaccount.google.com/apppasswords
  3. Create a new App Password (name it "stock-alerts" or similar)
  4. Copy the 16-character code into SMTP_PASSWORD in your .env

DEPENDENCIES
------------
- smtplib: Python stdlib — no installation needed
- email:   Python stdlib — no installation needed
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.alerts.anomaly_detector import Anomaly

logger = logging.getLogger(__name__)


def _build_html_body(anomalies: list[Anomaly]) -> str:
    """
    Build the HTML body of the alert email.

    Returns a complete HTML string with a styled table showing one
    row per anomaly. Inline styles are used (no external CSS) because
    many email clients strip <style> tags for security reasons.
    """
    # Build one table row per anomaly.
    rows_html = ""
    for a in anomalies:
        # Colour the z-score cell: red for spike, blue for drop.
        colour = "#c0392b" if a.direction == "spike" else "#2980b9"
        sign = "+" if a.z_score > 0 else ""

        rows_html += f"""
        <tr>
          <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">{a.symbol}</td>
          <td style="padding: 8px; border: 1px solid #ddd;">${a.latest_price:,.4f}</td>
          <td style="padding: 8px; border: 1px solid #ddd;">${a.mean:,.4f}</td>
          <td style="padding: 8px; border: 1px solid #ddd;">${a.stdev:,.4f}</td>
          <td style="padding: 8px; border: 1px solid #ddd; color: {colour}; font-weight: bold;">
            {sign}{a.z_score:.2f}
          </td>
          <td style="padding: 8px; border: 1px solid #ddd; color: {colour}; text-transform: uppercase;">
            {a.direction}
          </td>
          <td style="padding: 8px; border: 1px solid #ddd; font-size: 12px; color: #666;">
            {a.detected_at.strftime('%Y-%m-%d %H:%M:%S UTC') if a.detected_at else 'N/A'}
          </td>
        </tr>
        """

    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333; max-width: 800px; margin: 0 auto;">

      <h2 style="color: #e74c3c;">
        ⚠ Stock Anomaly Alert — {len(anomalies)} symbol(s) flagged
      </h2>

      <p>
        The anomaly detection pipeline has identified unusual price movements.
        These prices deviated significantly from their recent baseline.
      </p>

      <table style="border-collapse: collapse; width: 100%; margin-top: 16px;">
        <thead>
          <tr style="background-color: #2c3e50; color: white;">
            <th style="padding: 10px; border: 1px solid #555; text-align: left;">Symbol</th>
            <th style="padding: 10px; border: 1px solid #555; text-align: left;">Latest Price</th>
            <th style="padding: 10px; border: 1px solid #555; text-align: left;">20-Day Mean</th>
            <th style="padding: 10px; border: 1px solid #555; text-align: left;">Std Dev</th>
            <th style="padding: 10px; border: 1px solid #555; text-align: left;">Z-Score</th>
            <th style="padding: 10px; border: 1px solid #555; text-align: left;">Direction</th>
            <th style="padding: 10px; border: 1px solid #555; text-align: left;">Detected At</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>

      <p style="margin-top: 24px; font-size: 13px; color: #888;">
        Z-score threshold: ±2.5 &nbsp;|&nbsp; Lookback window: 20 days<br>
        This alert was generated automatically by the Stock Market Analytics Platform.
      </p>

    </body>
    </html>
    """


def send_alert_email(
    anomalies: list[Anomaly],
    smtp_user: str,
    smtp_password: str,
    recipient: str,
    smtp_host: str = "smtp.gmail.com",
    smtp_port: int = 587,
) -> bool:
    """
    Send an HTML email listing all detected anomalies.

    Does nothing and returns False if:
      - anomalies list is empty (no point sending an empty alert)
      - smtp_user or smtp_password are not configured

    Args:
        anomalies:     List of Anomaly objects from detect_anomalies().
        smtp_user:     Gmail address to send FROM (e.g. "you@gmail.com").
        smtp_password: 16-character Gmail App Password (NOT your real password).
        recipient:     Address to send the alert TO.
        smtp_host:     SMTP server hostname. Default: smtp.gmail.com.
        smtp_port:     SMTP server port. 587 uses STARTTLS (recommended).

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    # Early exits — don't try to send if we have nothing to send or no credentials.
    if not anomalies:
        logger.debug("No anomalies — email not sent.")
        return False

    if not smtp_user or not smtp_password:
        logger.warning(
            "SMTP credentials not configured (SMTP_USER / SMTP_PASSWORD). "
            "Email alert skipped. Set these in your .env file."
        )
        return False

    if not recipient:
        logger.warning("ALERT_RECIPIENT not configured. Email alert skipped.")
        return False

    # Build the email message object.
    # MIMEMultipart("alternative") means the message has multiple representations.
    # We only send HTML here, but "alternative" is the correct MIME type for HTML
    # emails — it tells clients to prefer the last (HTML) part.
    msg = MIMEMultipart("alternative")
    msg["Subject"] = (
        f"[Stock Alert] {len(anomalies)} anomaly/anomalies detected — "
        + ", ".join(a.symbol for a in anomalies)
    )
    msg["From"] = smtp_user
    msg["To"] = recipient

    # Attach the HTML body.
    html_body = _build_html_body(anomalies)
    msg.attach(MIMEText(html_body, "html"))

    # Connect, authenticate, and send.
    # The `with` block automatically calls server.quit() when done.
    try:
        logger.info("Connecting to %s:%d...", smtp_host, smtp_port)

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            # EHLO introduces us to the server (extended SMTP handshake).
            server.ehlo()

            # STARTTLS upgrades the plain TCP connection to encrypted TLS.
            # After this, all communication (including the password) is encrypted.
            server.starttls()
            server.ehlo()  # re-identify after TLS upgrade

            # Authenticate with the App Password.
            server.login(smtp_user, smtp_password)

            # Send the email.
            server.sendmail(smtp_user, [recipient], msg.as_string())

        logger.info(
            "Alert email sent to %s for symbols: %s",
            recipient,
            ", ".join(a.symbol for a in anomalies),
        )
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "SMTP authentication failed. "
            "Check that SMTP_USER and SMTP_PASSWORD are correct, "
            "and that you're using a Gmail App Password (not your real password)."
        )
        return False

    except smtplib.SMTPException as exc:
        logger.error("SMTP error while sending alert email: %s", exc)
        return False

    except OSError as exc:
        # Covers connection refused, network unreachable, DNS failure, etc.
        logger.error(
            "Network error connecting to %s:%d — %s",
            smtp_host, smtp_port, exc
        )
        return False
