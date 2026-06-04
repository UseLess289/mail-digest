import os
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from groq import Groq

# Chargement des variables d'environnement
from dotenv import load_dotenv
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HOURS_LOOKBACK = 6  # uniquement les emails des 6 dernières heures
MAX_BODY_LEN = 750  # caractères maximum par corps d'email

def summarize_emails(emails):
    """Résumé des emails avec Groq, en respectant le format HTML demandé."""
    if not emails:
        return "Aucun email."

    # Grouper par label (boîte)
    from collections import defaultdict
    by_label = defaultdict(list)
    for e in emails:
        by_label[e['label']].append(e)

    # Construire le contenu textuel structuré par boîte
    sections = []
    for label, label_emails in by_label.items():
        section_content = "\n\n".join(
            f"[{i}] De : {e['from']}\nSujet : {e['subject']}\nCorps : {e['body']}"
            for i, e in enumerate(label_emails)
        )
        sections.append(f"=== {label} ===\n\n{section_content}")

    content = "\n\n".join(sections)

    # Prompt système (identique à celui qui marchait avant)
    system_prompt = (
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
        f"Voici les emails :\n\n{content}"
    )

    if GROQ_API_KEY:
        client = Groq(api_key=GROQ_API_KEY)
        try:
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",  # ou "meta-llama/llama-4-scout-17b-16e-instruct" si dispo
                messages=[{"role": "user", "content": system_prompt}],
                temperature=0.3,
                max_tokens=1024,
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"Erreur Groq pour résumé : {e}")
            return f"{len(emails)} emails reçus (résumé non disponible)."
    else:
        return f"{len(emails)} emails reçus (clé Groq manquante)."
# Si vous avez déjà une fonction summarize, gardez-la, sinon en voici une basée sur Groq

def decode_mime_words(s):
    """Décode les chaînes encodées en MIME (sujet, nom)."""
    try:
        decoded_parts = decode_header(s)
        decoded_string = ""
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                decoded_string += part.decode(charset or 'utf-8', errors='replace')
            else:
                decoded_string += part
        return decoded_string
    except:
        return s

def fetch_recent_emails(host, user, password, label, hours=HOURS_LOOKBACK):
    """Connecte un compte IMAP et retourne la liste des emails des dernières `hours` heures."""
    emails = []
    try:
        mail = imaplib.IMAP4_SSL(host)
        mail.login(user, password)
        mail.select("INBOX")
        
        # Date limite
        date_limit = (datetime.now() - timedelta(hours=hours)).strftime("%d-%b-%Y")
        result, data = mail.search(None, f'(SINCE "{date_limit}")')
        
        if result != "OK":
            return emails
        
        for num in data[0].split():
            try:
                result, msg_data = mail.fetch(num, "(RFC822)")
                if result != "OK":
                    continue
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                # Décodage du sujet et de l'expéditeur
                subject = decode_mime_words(msg.get("Subject", "Sans sujet"))
                from_ = decode_mime_words(msg.get("From", "Inconnu"))
                date = msg.get("Date", "")
                
                # Extraction du corps (texte brut)
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            try:
                                payload = part.get_payload(decode=True)
                                charset = part.get_content_charset() or 'utf-8'
                                body = payload.decode(charset, errors='replace')
                                break
                            except:
                                continue
                else:
                    try:
                        payload = msg.get_payload(decode=True)
                        charset = msg.get_content_charset() or 'utf-8'
                        body = payload.decode(charset, errors='replace')
                    except:
                        body = ""
                
                # Nettoyage HTML si besoin
                if "<" in body and ">" in body:
                    soup = BeautifulSoup(body, "html.parser")
                    body = soup.get_text()
                
                # Limiter la longueur du corps
                body = body[:MAX_BODY_LEN]
                
                emails.append({
                    "subject": subject,
                    "from": from_,
                    "date": date,
                    "body": body,
                    "label": label
                })
            except Exception as e:
                print(f"Erreur lecture email {label}: {e}")
                continue
        
        mail.close()
        mail.logout()
    except Exception as e:
        print(f"Erreur IMAP pour {label}: {e}")
    return emails

def get_all_recent_emails():
    """Retourne la liste de tous les emails récents (tous comptes)."""
    accounts = [
        {"host": "imap.gmail.com",       "user": os.getenv("GMAIL_USER"),         "password": os.getenv("GMAIL_APP_PASSWORD"),  "label": "Gmail"},
        {"host": "imap.mail.me.com",     "user": os.getenv("ICLOUD_USER",""),     "password": os.getenv("ICLOUD_APP_PASSWORD",""),"label": "iCloud"},
        {"host": os.getenv("UNI_HOST",""),"user": os.getenv("UNI_USER",""),        "password": os.getenv("UNI_PASSWORD",""),      "label": "Université"},
    ]
    all_emails = []
    for acc in accounts:
        if acc["user"] and acc["host"]:
            try:
                all_emails.extend(fetch_recent_emails(**acc))
            except Exception as e:
                print(f"[{acc['label']}] Erreur IMAP : {e}")
    return all_emails

def run_digest():
    """Point d'entrée appelé par le bot. Retourne (résumé, liste_emails)."""
    emails = get_all_recent_emails()
    now = datetime.now().strftime("%d/%m à %Hh%M")
    if not emails:
        summary = f"📭 <b>Digest — {now}</b>\n\nAucun nouveau mail ces {HOURS_LOOKBACK}h."
    else:
        summary_text = summarize_emails(emails)
        summary = f"📬 <b>Digest — {now}</b> ({len(emails)} mails)\n\n{summary_text}"
    return summary, emails

# Si exécuté directement (pour test)
if __name__ == "__main__":
    summ, mails = run_digest()
    print(summ)
    print(f"Nombre d'emails récupérés : {len(mails)}")
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
