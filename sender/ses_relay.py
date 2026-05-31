"""Relay email via Amazon SES SMTP using smtplib."""

import smtplib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sender.config import (  # noqa: E402
    SES_SMTP_HOST,
    SES_SMTP_PASSWORD,
    SES_SMTP_PORT,
    SES_SMTP_USERNAME,
    SES_STARTTLS,
    log,
)


def relay_via_ses(raw_bytes, mail_from, rcpt_tos, timeout=30):
    """Relay a raw email via Amazon SES SMTP.

    Returns:
        (ok: bool, response: str) — ``ok`` is True on success.
    """
    if not SES_SMTP_USERNAME or not SES_SMTP_PASSWORD:
        return False, "SES SMTP credentials not configured (check .env)"

    try:
        smtp = smtplib.SMTP(SES_SMTP_HOST, SES_SMTP_PORT, timeout=timeout)
        smtp.ehlo()

        if SES_STARTTLS:
            smtp.starttls()
            smtp.ehlo()

        smtp.login(SES_SMTP_USERNAME, SES_SMTP_PASSWORD)
        refusals = smtp.sendmail(mail_from, rcpt_tos, raw_bytes)
        smtp.quit()

        if refusals:
            return False, f"Recipient refused: {refusals}"

        log("INFO", f"SES relay OK — from={mail_from} to={rcpt_tos}")
        return True, "250 OK"

    except smtplib.SMTPAuthenticationError as exc:
        msg = f"SES auth failed: {exc}"
        log("ERROR", msg)
        return False, msg

    except smtplib.SMTPRecipientsRefused as exc:
        msg = f"SES recipient refused: {exc}"
        log("ERROR", msg)
        return False, msg

    except smtplib.SMTPSenderRefused as exc:
        msg = f"SES sender refused: {exc}"
        log("ERROR", msg)
        return False, msg

    except smtplib.SMTPDataError as exc:
        msg = f"SES data error: {exc}"
        log("ERROR", msg)
        return False, msg

    except (smtplib.SMTPConnectError, smtplib.SMTPHeloError) as exc:
        msg = f"SES connection error: {exc}"
        log("ERROR", msg)
        return False, msg

    except OSError as exc:
        msg = f"SES network error: {exc}"
        log("ERROR", msg)
        return False, msg

    except Exception as exc:
        msg = f"SES unexpected error: {type(exc).__name__}: {exc}"
        log("ERROR", msg)
        return False, msg
