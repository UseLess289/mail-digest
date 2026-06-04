import os
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from groq import Groq

from dotenv import load_dotenv
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HOURS_LOOKBACK = 6
MAX_BODY_LEN = 750

def summarize_emails(emails):
    if not emails:
        return "Aucun email."

    # group by label 
    from collections import defaultdict
    by_label = defaultdict(list)
    for e in emails:
        by_label[e['label']].append(e)

    sections = []
    for label, label_emails in by_label.items():
        section_content = "\n\n".join(
            f"[{i}] De : {e['from']}\nSujet : {e['subject']}\nCorps : {e['body']}"
            for i, e in enumerate(label_emails)
        )
        sections.append(f"=== {label} ===\n\n{section_content}")

    content = "\n\n".join(sections)

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
                model="llama-3.3-70b-versatile",
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


                subject = decode_mime_words(msg.get("Subject", "Sans sujet"))
                from_ = decode_mime_words(msg.get("From", "Inconnu"))
                date = msg.get("Date", "")


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


                if "<" in body and ">" in body:
                    soup = BeautifulSoup(body, "html.parser")
                    body = soup.get_text()


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
        print(f"IMAP Error for {label}: {e}")
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
                print(f"[{acc['label']}] Error IMAP : {e}")
    return all_emails

def run_digest():
    """Point d'entrée appelé par le bot. Retourne (résumé, liste_emails)."""
    emails = get_all_recent_emails()
    now = datetime.now().strftime("%d/%m à %Hh%M")
    if not emails:
        summary = f"<b>Digest — {now}</b>\n\nNo news for {HOURS_LOOKBACK}h."
    else:
        summary_text = summarize_emails(emails)
        summary = f"<b>Digest — {now}</b> ({len(emails)} mails)\n\n{summary_text}"
    return summary, emails

if __name__ == "__main__":
    summ, mails = run_digest()
    print(summ)
    print(f"Number emails returned : {len(mails)}")
