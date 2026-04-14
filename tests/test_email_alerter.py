"""
tests/test_email_alerter.py — Unit tests for the email alerter
===============================================================
TESTING STRATEGY
----------------
We NEVER send real emails in unit tests. Sending an actual email:
  - Requires working network + valid credentials
  - Would spam someone's inbox every time CI runs
  - Would fail in CI (no Gmail credentials available)

Instead, we mock smtplib.SMTP — the class that actually connects to
the mail server. By replacing it with a MagicMock, we can:
  1. Verify that the right SMTP methods were called (login, sendmail)
  2. Test error-handling paths without a real server
  3. Run tests anywhere, instantly, with no credentials

HOW `unittest.mock.patch` WORKS
---------------------------------
`@patch("src.alerts.email_alerter.smtplib.SMTP")` means:
  "While this test runs, replace smtplib.SMTP in email_alerter.py
   with a MagicMock object."

The mock is passed as the last argument to the test function:
  def test_something(self, mock_smtp_class):
      ...

When the code does `with smtplib.SMTP(host, port) as server:`,
Python actually runs `with mock_smtp_class(host, port) as server:`.
The mock records every method call so we can assert on them later.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.alerts.anomaly_detector import Anomaly
from src.alerts.email_alerter import send_alert_email


# -----------------------------------------------------------------------
# HELPERS — build fake Anomaly objects
# -----------------------------------------------------------------------

def _make_anomaly(
    symbol: str = "TSLA",
    latest_price: float = 200.0,
    mean: float = 100.0,
    stdev: float = 5.0,
    z_score: float = 20.0,
    direction: str = "spike",
) -> Anomaly:
    """Create a fake Anomaly for testing — no DB required."""
    return Anomaly(
        symbol=symbol,
        latest_price=latest_price,
        mean=mean,
        stdev=stdev,
        z_score=z_score,
        direction=direction,
        detected_at=datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
        sample_size=19,
    )


# -----------------------------------------------------------------------
# TESTS
# -----------------------------------------------------------------------

class TestSendAlertEmail:
    """Tests for the send_alert_email() function."""

    def test_returns_false_for_empty_anomalies(self):
        """
        HAPPY PATH: empty anomalies list → no email sent → returns False.
        No SMTP connection should be attempted.
        """
        result = send_alert_email(
            anomalies=[],
            smtp_user="user@gmail.com",
            smtp_password="app_password",
            recipient="dest@example.com",
        )

        assert result is False

    def test_returns_false_when_smtp_user_missing(self):
        """
        EDGE CASE: SMTP credentials not configured → return False gracefully.
        Should not crash or attempt a connection.
        """
        anomaly = _make_anomaly()

        result = send_alert_email(
            anomalies=[anomaly],
            smtp_user="",           # empty = not configured
            smtp_password="secret",
            recipient="dest@example.com",
        )

        assert result is False

    def test_returns_false_when_smtp_password_missing(self):
        """EDGE CASE: password missing → return False."""
        anomaly = _make_anomaly()

        result = send_alert_email(
            anomalies=[anomaly],
            smtp_user="user@gmail.com",
            smtp_password="",       # empty = not configured
            recipient="dest@example.com",
        )

        assert result is False

    def test_returns_false_when_recipient_missing(self):
        """EDGE CASE: no recipient address → return False."""
        anomaly = _make_anomaly()

        result = send_alert_email(
            anomalies=[anomaly],
            smtp_user="user@gmail.com",
            smtp_password="app_password",
            recipient="",           # empty = not configured
        )

        assert result is False

    @patch("src.alerts.email_alerter.smtplib.SMTP")
    def test_sends_email_with_valid_inputs(self, mock_smtp_class):
        """
        HAPPY PATH: valid inputs → SMTP connection is made → returns True.

        We check that:
          - smtplib.SMTP was instantiated with the right host/port
          - starttls() was called (encrypted connection)
          - login() was called with our credentials
          - sendmail() was called with the right sender + recipient
        """
        # Set up the mock so the context manager (`with SMTP(...) as server`)
        # works correctly. __enter__ returns the "server" object.
        mock_smtp_instance = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance

        anomaly = _make_anomaly()

        result = send_alert_email(
            anomalies=[anomaly],
            smtp_user="sender@gmail.com",
            smtp_password="my_app_password",
            recipient="recipient@example.com",
            smtp_host="smtp.gmail.com",
            smtp_port=587,
        )

        assert result is True

        # SMTP class was instantiated with the correct host and port
        mock_smtp_class.assert_called_once_with("smtp.gmail.com", 587)

        # STARTTLS was called — connection is encrypted
        mock_smtp_instance.starttls.assert_called_once()

        # Login was called with the right credentials
        mock_smtp_instance.login.assert_called_once_with(
            "sender@gmail.com", "my_app_password"
        )

        # sendmail was called with correct from/to addresses
        call_args = mock_smtp_instance.sendmail.call_args
        assert call_args[0][0] == "sender@gmail.com"          # from
        assert call_args[0][1] == ["recipient@example.com"]   # to (list)

    @patch("src.alerts.email_alerter.smtplib.SMTP")
    def test_email_subject_contains_symbol(self, mock_smtp_class):
        """
        The email subject should mention the anomalous symbol(s).
        Interviewers will check this kind of detail.
        """
        mock_smtp_instance = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance

        anomaly = _make_anomaly(symbol="AAPL")
        send_alert_email(
            anomalies=[anomaly],
            smtp_user="s@gmail.com",
            smtp_password="pw",
            recipient="r@example.com",
        )

        # The third argument to sendmail is the full RFC-2822 message string.
        # It should contain the subject line with "AAPL".
        message_string = mock_smtp_instance.sendmail.call_args[0][2]
        assert "AAPL" in message_string

    @patch("src.alerts.email_alerter.smtplib.SMTP")
    def test_authentication_error_returns_false(self, mock_smtp_class):
        """
        EDGE CASE: wrong password → SMTPAuthenticationError → return False,
        don't crash the caller.
        """
        import smtplib

        mock_smtp_instance = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance

        # Simulate Gmail rejecting the login
        mock_smtp_instance.login.side_effect = smtplib.SMTPAuthenticationError(
            535, b"Bad credentials"
        )

        anomaly = _make_anomaly()
        result = send_alert_email(
            anomalies=[anomaly],
            smtp_user="user@gmail.com",
            smtp_password="wrong_password",
            recipient="dest@example.com",
        )

        assert result is False

    @patch("src.alerts.email_alerter.smtplib.SMTP")
    def test_network_error_returns_false(self, mock_smtp_class):
        """
        EDGE CASE: network down → OSError → return False gracefully.
        (smtplib raises OSError for connection refused / DNS failure)
        """
        # Make SMTP() itself raise OSError (can't even connect)
        mock_smtp_class.side_effect = OSError("Connection refused")

        anomaly = _make_anomaly()
        result = send_alert_email(
            anomalies=[anomaly],
            smtp_user="user@gmail.com",
            smtp_password="password",
            recipient="dest@example.com",
        )

        assert result is False

    @patch("src.alerts.email_alerter.smtplib.SMTP")
    def test_multiple_anomalies_single_email(self, mock_smtp_class):
        """
        Multiple anomalies should be batched into ONE email,
        not one email per anomaly.
        """
        mock_smtp_instance = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance

        anomalies = [
            _make_anomaly("AAPL", z_score=3.1),
            _make_anomaly("TSLA", z_score=-4.2, direction="drop"),
            _make_anomaly("MSFT", z_score=2.8),
        ]

        result = send_alert_email(
            anomalies=anomalies,
            smtp_user="user@gmail.com",
            smtp_password="pw",
            recipient="dest@example.com",
        )

        assert result is True
        # sendmail should have been called exactly ONCE — one email for all anomalies
        assert mock_smtp_instance.sendmail.call_count == 1
