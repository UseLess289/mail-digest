import asyncio
import os
from collections import deque
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from digest import run_digest, GROQ_API_KEY
from groq import Groq

load_dotenv()

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

MESSAGE_LIFETIME = 300
EMAIL_TTL = 21600

# Initialisation du client Groq
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

async def send_and_store(context, chat_id, text, parse_mode="HTML", auto_delete=True, delete_delay=MESSAGE_LIFETIME):
    """Envoie un message, stocke son ID et planifie sa suppression."""
    sent = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
    if 'bot_messages' not in context.bot_data:
        context.bot_data['bot_messages'] = deque(maxlen=200)
    context.bot_data['bot_messages'].append(sent.message_id)
    if auto_delete:
        asyncio.create_task(delete_message_after_delay(context, chat_id, sent.message_id, delete_delay))
    return sent

async def delete_message_after_delay(context, chat_id, msg_id, delay):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        # Retirer de la liste si présent
        if 'bot_messages' in context.bot_data:
            context.bot_data['bot_messages'] = deque(
                [mid for mid in context.bot_data['bot_messages'] if mid != msg_id],
                maxlen=200
            )
    except Exception:
        pass

# --- Commandes ---
async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != TELEGRAM_CHAT_ID:
        return
    status_msg = await update.message.reply_text("⏳ Récupération des mails en cours...")
    try:
        loop = asyncio.get_event_loop()
        summary, emails = await loop.run_in_executor(None, run_digest)
        # Stocker les emails avec timestamp
        context.user_data['last_emails'] = emails
        context.user_data['last_emails_time'] = loop.time()
        # Envoi du résumé
        await send_and_store(context, update.effective_chat.id, summary, parse_mode="HTML")
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"Error : {e}")

async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != TELEGRAM_CHAT_ID:
        return
    if not groq_client:
        await update.message.reply_text("Error : API key missing")
        return
    emails = context.user_data.get('last_emails')
    if not emails:
        await update.message.reply_text("You should run /digest first")
        return

    last_time = context.user_data.get('last_emails_time', 0)
    if asyncio.get_event_loop().time() - last_time > EMAIL_TTL:
        await update.message.reply_text("You should run /digest (emails disapeared)")
        return

    question = update.message.text.replace('/ask', '', 1).strip()
    if not question:
        await update.message.reply_text("Usage : /asl [Question]. Example : /ask what's the verification code for xbox")
        return

    emails_text = ""
    for i, e in enumerate(emails[:15]):
        emails_text += f"\nEmail {i+1} :\nDe: {e['from']}\nSujet: {e['subject']}\nDate: {e['date']}\nExtrait: {e['body'][:500]}\n"

    prompt = f"""Voici des emails récents (moins de 6h). Réponds précisément à la question posée en français, en te basant uniquement sur ces emails. Si l'information n'est pas présente, dis-le clairement.

Emails :
{emails_text}

Question : {question}

Réponse :"""
    
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        answer = completion.choices[0].message.content
        await update.message.reply_text(f"<b>Answer :</b> :\n{answer}", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"Error with Groq : {e}")

async def cmd_clean(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != TELEGRAM_CHAT_ID:
        return
    chat_id = update.effective_chat.id
    bot_messages = context.bot_data.get('bot_messages', [])
    if not bot_messages:
        await update.message.reply_text("No message to delete")
        return
    deleted = 0
    for mid in list(bot_messages):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
            deleted += 1
        except Exception:
            pass
    context.bot_data['bot_messages'] = deque(maxlen=200)
    await update.message.reply_text(f" {deleted} messages deleted")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != TELEGRAM_CHAT_ID:
        return
    await update.message.reply_text(
        "Commandes disponibles :\n"
        "/digest — résumé des mails des dernières heures (stocke les emails 6h)\n"
        "/ask <question> — pose une question sur les derniers emails récupérés\n"
        "/clean — supprime tous les messages du bot dans ce chat\n"
        "/help — affiche ce message"
    )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(CommandHandler("ask", cmd_ask))
    app.add_handler(CommandHandler("clean", cmd_clean))
