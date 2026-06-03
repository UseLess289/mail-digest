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
ICLOUD_USER= os.getenv("ICLOUD_USER")
ICLOUD_APP_PASSWORD= os.getenv("ICLOUD_USER")
UNI_HOST= os.getenv("UNI_HOST")
UNI_USER= os.getenv("UNI_USER")
UNI_PASSWORD= os.getenv("UNI_PASSWORD")



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
                    payload = part.get_payload(decode=True)
                    if not isinstance(payload, bytes):
                        continue
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")[:800]
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            if not isinstance(payload, bytes):
                return ""
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")[:800]
        except Exception:
            pass
    return ""

def fetch_recent_emails(host, user, password, label):
    since = datetime.now(timezone.utc) - timedelta(hours=HOURS_LOOKBACK)
    imap_date = since.strftime("%d-%b-%Y")

    mail = imaplib.IMAP4_SSL(host, 993)
    mail.login(user, password)
    mail.select("INBOX")

    _, ids = mail.search(None, f'SINCE "{imap_date}"')

    emails = []
    for mid in ids[0].split():
        _, data = mail.fetch(mid, "(RFC822)")

        # iCloud inclut parfois des entiers (taille) dans la réponse
        raw = next((d[1] for d in data if isinstance(d, tuple)), None)
        if not raw:
            continue

        msg = email.message_from_bytes(raw)

        try:
            from email.utils import parsedate_to_datetime
            if parsedate_to_datetime(msg.get("Date", "")) < since:
                continue
        except Exception:
            pass

        emails.append({
            "label":   label,
            "from":    msg.get("From", "?"),
            "subject": decode_str(msg.get("Subject", "(sans sujet)")),
            "body":    get_body(msg),
        })

    mail.logout()
    return emails
def summarize(emails):
    # Groupement par boite fait en Python, pas par le LLM
    from collections import defaultdict
    by_label = defaultdict(list)
    for e in emails:
        by_label[e['label']].append(e)

    sections = []
    for label, label_emails in by_label.items():
        section_content = "\n\n".join(
            f"[{i}] De : {e['from']}\nSujet : {e['subject']}\n\n{e['body']}"
            for i, e in enumerate(label_emails)
        )
        sections.append(f"=== {label} ===\n\n{section_content}")

    content = "\n\n".join(sections)

    client = Groq(api_key=GROQ_API_KEY)
    resp = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{
            "role": "user",
                "content": (
    "Tu es un assistant personnel. Voici des emails de plusieurs boites mail.\n\n"
    "RÈGLES DE FORMATAGE — respecte-les strictement :\n"
    "• Utilise UNIQUEMENT ces balises HTML : <b>texte</b> et <i>texte</i>\n"
    "• INTERDIT : #, ##, ###, **, __, *, _ ou tout autre syntaxe Markdown\n"
    "• Les bullet points sont le caractère •\n"
    "• Les séparateurs de section sont ——\n\n"
    "STRUCTURE À RESPECTER pour chaque boite mail présente :\n\n"
    "<b>—— NOM_BOITE ——</b>\n"
    "<b>Thème éventuel</b>\n"
    "• Expéditeur — résumé court\n"
    "• ...\n\n"
    "RÈGLES DE CONTENU :\n"
    "• IMPORTANT : le champ BOITE= indique la boite d'origine de chaque mail. "
"Ne déplace JAMAIS un mail dans la section d'une autre boite.\n"
    "• Regroupe les mails importants par thème au sein de chaque boite\n"
    "• Préfixe ⚠ devant ce qui est urgent ou un problème de sécurité\n"
    "• Ignore les mails promotionnels/newsletters dans les sections, "
    "compte-les uniquement à la fin\n"
    "• Termine par UNE seule ligne : <i>Autres : X mails</i>\n"
    "• Si une boite n'a aucun mail important, ne l'affiche pas du tout\n\n"
    f"{content}"
)
        }],
        max_tokens=1024,
    )
    return resp.choices[0].message.content

def send_telegram(text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
        timeout=10,
    )
def run_digest():
    accounts = [
        {"host": "imap.gmail.com",       "user": os.getenv("GMAIL_USER"),         "password": os.getenv("GMAIL_APP_PASSWORD"),  "label": "Gmail"},
        {"host": "imap.mail.me.com",      "user": os.getenv("ICLOUD_USER",""),     "password": os.getenv("ICLOUD_APP_PASSWORD",""),"label": "iCloud"},
        {"host": os.getenv("UNI_HOST",""),"user": os.getenv("UNI_USER",""),        "password": os.getenv("UNI_PASSWORD",""),      "label": "Université"},
    ]

    all_emails = []
    for acc in accounts:
        if acc["user"] and acc["host"]:
            try:
                all_emails.extend(fetch_recent_emails(**acc))
            except Exception as e:
                print(f"[{acc['label']}] Erreur IMAP : {e}")

    now = datetime.now().strftime("%d/%m à %Hh%M")
    if not all_emails:
        send_telegram(f"📭 <b>Digest — {now}</b>\n\nAucun nouveau mail ces {HOURS_LOOKBACK}h.")
    else:
        summary = summarize(all_emails)
        send_telegram(f"📬 <b>Digest — {now}</b> ({len(all_emails)} mails)\n\n{summary}")

if __name__ == "__main__":
    run_digest()
