import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta, timezone
import os
import requests
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

GMAIL_USER        = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD= os.getenv("GMAIL_APP_PASSWORD")
GROQ_API_KEY      = os.getenv("GROQ_API_KEY")
TELEGRAM_TOKEN    = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID  = os.getenv("TELEGRAM_CHAT_ID")
HOURS_LOOKBACK    = int(os.getenv("HOURS_LOOKBACK", "8"))


def decode_str(value):
    if not value:
        return ""
    decoded, enc = decode_header(value)[0]
    if isinstance(decoded, bytes):
        return decoded.decode(enc or "utf-8", errors="replace")
    return decoded


def get_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get("Content-Disposition"):
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )[:800]
                except Exception:
                    pass
    else:
        try:
            return msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="replace"
            )[:800]
        except Exception:
            pass
    return ""


def fetch_recent_emails():
    since = (datetime.now(timezone.utc) - timedelta(hours=HOURS_LOOKBACK))
    imap_date = since.strftime("%d-%b-%Y")  # format IMAP : "02-Jun-2025"

    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    mail.select("INBOX")

    _, ids = mail.search(None, f'SINCE "{imap_date}"')

    emails = []
    for mid in ids[0].split():
        _, data = mail.fetch(mid, "(RFC822)")
        msg = email.message_from_bytes(data[0][1])

        # Filtrer précisément par heure (IMAP SINCE ne filtre que par jour)
        date_str = msg.get("Date", "")
        try:
            from email.utils import parsedate_to_datetime
            msg_date = parsedate_to_datetime(date_str)
            if msg_date < since:
                continue
        except Exception:
            pass

        emails.append({
            "from":    msg.get("From", "?"),
            "subject": decode_str(msg.get("Subject", "(sans sujet)")),
            "body":    get_body(msg),
            "date":    date_str,
        })

    mail.logout()
    return emails

def summarize(emails):
    content = "\n\n---\n\n".join(
        f"[{i}] De : {e['from']}\nSujet : {e['subject']}\n\n{e['body']}"
        for i, e in enumerate(emails)
    )

    client = Groq(api_key=GROQ_API_KEY)
    resp = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{
            "role": "user",
            "content": (
                "Tu es un assistant personnel. Voici une liste d'emails numérotés.\n\n"
                "Ta tâche :\n"
                "1. Sépare les emails en deux catégories :\n"
                "   - IMPORTANTS : emails personnels, professionnels, administratifs, urgents, notifications utiles\n"
                "   - AUTRES : promotions, réductions, newsletters, publicités, emails marketing\n"
                "2. Pour les IMPORTANTS : fais un résumé concis en bullet points en français. "
                "Signale ce qui est urgent. Regroupe par thème si pertinent.\n"
                "3. À la toute fin, ajoute UNE seule ligne : 'Autres : X mails' "
                "(X = nombre d'emails classés comme autres). "
                "Si il n'y a aucun mail important, dis-le brièvement avant la ligne Autres.\n\n"
                f"{content}"
            )
        }],
        max_tokens=1024,
    )
    return resp.choices[0].message.content


def send_telegram(text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
        timeout=10,
    )


if __name__ == "__main__":
    now = datetime.now().strftime("%d/%m à %Hh%M")
    emails = fetch_recent_emails()

    if not emails:
        send_telegram(f"📭 *Digest Gmail — {now}*\n\nAucun nouveau mail ces {HOURS_LOOKBACK}h.")
    else:
        summary = summarize(emails)
        send_telegram(f"📬 *Digest Gmail — {now}* ({len(emails)} mail{'s' if len(emails)>1 else ''})\n\n{summary}")
