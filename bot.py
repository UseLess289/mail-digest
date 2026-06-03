import asyncio
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from digest import run_digest

load_dotenv()

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Sécurité : ignore les requêtes d'autres chats
    if str(update.effective_chat.id) != TELEGRAM_CHAT_ID:
        return
    await update.message.reply_text("⏳ Récupération des mails en cours...")
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, run_digest)
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur : {e}")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != TELEGRAM_CHAT_ID:
        return
    await update.message.reply_text(
        "Commandes disponibles :\n"
        "/digest — résumé des mails des dernières heures\n"
        "/help — affiche ce message"
    )


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(CommandHandler("help",   cmd_help))
    print("Bot en écoute...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
