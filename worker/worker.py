import boto3
import sqlite3
import hashlib
import shutil
from pathlib import Path
from email import policy
from email.parser import BytesParser
from datetime import datetime, timezone

BUCKET = "ricardo-vc-ses-mailbox"
PREFIX = "incoming/"

BASE_DIR = Path.home() / "ses-s3-mailbox"
RAW_DIR = BASE_DIR / "data" / "raw-emails"
MAILDIR_NEW = BASE_DIR / "data" / "maildir" / "master" / "new"
DB_PATH = BASE_DIR / "data" / "mailbox.db"

RAW_DIR.mkdir(parents=True, exist_ok=True)
MAILDIR_NEW.mkdir(parents=True, exist_ok=True)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            s3_bucket TEXT NOT NULL,
            s3_key TEXT NOT NULL UNIQUE,
            local_raw_path TEXT NOT NULL,
            local_maildir_path TEXT NOT NULL,
            message_id TEXT,
            sender TEXT,
            recipient TEXT,
            subject TEXT,
            date_header TEXT,
            ses_spam_verdict TEXT,
            ses_virus_verdict TEXT,
            processed_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def already_processed(s3_key):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT 1 FROM messages WHERE s3_key = ?", (s3_key,))
    exists = cur.fetchone() is not None
    conn.close()
    return exists


def parse_email_headers(path):
    with open(path, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)

    return {
        "message_id": msg.get("Message-ID"),
        "sender": msg.get("From"),
        "recipient": msg.get("To"),
        "subject": msg.get("Subject"),
        "date_header": msg.get("Date"),
        "ses_spam_verdict": msg.get("X-SES-Spam-Verdict"),
        "ses_virus_verdict": msg.get("X-SES-Virus-Verdict"),
    }


def save_metadata(s3_key, raw_path, maildir_path, headers):
    conn = sqlite3.connect(DB_PATH)

    conn.execute("""
        INSERT INTO messages (
            s3_bucket,
            s3_key,
            local_raw_path,
            local_maildir_path,
            message_id,
            sender,
            recipient,
            subject,
            date_header,
            ses_spam_verdict,
            ses_virus_verdict,
            processed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        BUCKET,
        s3_key,
        str(raw_path),
        str(maildir_path),
        headers.get("message_id"),
        headers.get("sender"),
        headers.get("recipient"),
        headers.get("subject"),
        headers.get("date_header"),
        headers.get("ses_spam_verdict"),
        headers.get("ses_virus_verdict"),
        datetime.now(timezone.utc).isoformat()
    ))

    conn.commit()
    conn.close()


def make_safe_filename(s3_key):
    digest = hashlib.sha256(s3_key.encode()).hexdigest()[:16]
    original_name = s3_key.replace("/", "_")
    return f"{digest}_{original_name}.eml"


def main():
    init_db()

    s3 = boto3.client("s3")

    response = s3.list_objects_v2(
        Bucket=BUCKET,
        Prefix=PREFIX
    )

    objects = response.get("Contents", [])

    if not objects:
        print("Nenhum objeto encontrado.")
        return

    for obj in objects:
        s3_key = obj["Key"]

        if s3_key.endswith("/"):
            continue

        if s3_key == "incoming/AMAZON_SES_SETUP_NOTIFICATION":
            print(f"Ignorando notificação de setup: {s3_key}")
            continue

        if already_processed(s3_key):
            print(f"Já processado: {s3_key}")
            continue

        filename = make_safe_filename(s3_key)
        raw_path = RAW_DIR / filename
        maildir_path = MAILDIR_NEW / filename

        print(f"Baixando: {s3_key}")

        s3.download_file(
            BUCKET,
            s3_key,
            str(raw_path)
        )

        headers = parse_email_headers(raw_path)

        shutil.copy2(raw_path, maildir_path)

        save_metadata(
            s3_key=s3_key,
            raw_path=raw_path,
            maildir_path=maildir_path,
            headers=headers
        )

        print(f"Processado com sucesso: {s3_key}")
        print(f"  From: {headers.get('sender')}")
        print(f"  To: {headers.get('recipient')}")
        print(f"  Subject: {headers.get('subject')}")
        print(f"  Spam: {headers.get('ses_spam_verdict')}")
        print(f"  Virus: {headers.get('ses_virus_verdict')}")


if __name__ == "__main__":
    main()
