# mail-digest

A self-hosted Docker service that fetches your emails via IMAP, summarizes them with an LLM (Groq), and sends a formatted digest to a Telegram bot on a schedule.

## Requirements

- Docker + Docker Compose
- A Groq API key ([console.groq.com](https://console.groq.com))
- Gmail with IMAP enabled + an [App Password](https://myaccount.google.com/apppasswords)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Your Telegram chat ID (get it from `https://api.telegram.org/bot<TOKEN>/getUpdates`)

## Setup

**1. Clone and configure**

```bash
git clone https://github.com/UseLess298/mail-digest
cd mail-digest
```

**2. Create and edit `.env`**

```env
GMAIL_USER=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
GROQ_API_KEY=gsk_...
TELEGRAM_TOKEN=123456:ABC-...
TELEGRAM_CHAT_ID=123456789
HOURS_LOOKBACK=8
```

**3. Build**

```bash
docker compose build
```

**4. Test**

```bash
docker compose run --rm mail-digest
```

You should receive a Telegram message within seconds.

## Scheduling

Add to your crontab (`crontab -e`) to run at 8am, noon, and 6pm (time is set for UTC +0):

```cron
0 8  * * * cd /path/to/mail-digest && docker compose run --rm mail-digest
0 12 * * * cd /path/to/mail-digest && docker compose run --rm mail-digest
0 18 * * * cd /path/to/mail-digest && docker compose run --rm mail-digest
```

## How it works

1. Connects to Gmail via IMAP and fetches emails from the last `HOURS_LOOKBACK` hours
2. Sends them to the Groq API (Llama 4 Scout) for categorization and summarization
3. Important emails are summarized in bullet points, grouped by topic
4. Promotional/newsletter emails are counted and shown as a single line at the end
5. The digest is sent to your Telegram chat with HTML formatting

## Adding more mailboxes

You can configure various email boxes with configuring .env and import IMAP credentials in python.
