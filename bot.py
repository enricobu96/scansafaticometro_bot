import json
import os
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from dotenv import load_dotenv
load_dotenv()
bot_key = os.getenv("BOT_KEY")

# Persistence file and structures
DATA_FILE = "data.json"

user_message_counts = defaultdict(int)
user_thresholds_triggered = defaultdict(set)
user_timestamps = defaultdict(lambda: deque(maxlen=1000))
user_hourly_triggered = defaultdict(set)
user_spam_triggered = defaultdict(lambda: datetime.min.replace(tzinfo=timezone.utc))

# Thresholds
total_thresholds = {
    20: "Diocan {name} la smetti di spammare",
    100: "Qualcuno qui non ha davvero un cazzo da fare eh",
    200: "Dai dai su {name}, torna a lavorare",
    500: "{name} ha trasceso il significato di lavorare, ben fatto compagno, abbasso i padroni"
}

hourly_thresholds = {
    20: "Oi {name} guarda che la pausa dovrebbe essere di 5 minuti, non di un'ora",
    40: "Boh vabbè io basito da {name} che non ha veramente una minchia da fare, beato te",
    50: "Non sono un bot intelligente, ma qualcosa mi dice che Enrico e Luca stanno rantando"
}

def save_data():
    """
    Save the current state to the data file.
    This includes user message counts, triggered thresholds,
    timestamps, hourly triggers, and spam detection timestamps.
    Args:
        None
    Returns:
        None
    """
    with open(DATA_FILE, "w") as f:
        json.dump({
            "counts": dict(user_message_counts),
            "thresholds": {k: list(v) for k, v in user_thresholds_triggered.items()},
            "timestamps": {k: [ts.isoformat() for ts in v] for k, v in user_timestamps.items()},
            "hourly": {k: list(v) for k, v in user_hourly_triggered.items()},
            "spam": {k: v.isoformat() for k, v in user_spam_triggered.items()},
        }, f)

def load_data():
    """
    Load the state from the data file if it exists.
    This populates the user message counts, triggered thresholds,
    timestamps, hourly triggers, and spam detection timestamps.
    Args:
        None
    Returns:
        None
    """
    if not os.path.exists(DATA_FILE):
        return

    with open(DATA_FILE, "r") as f:
        data = json.load(f)

    for k, v in data.get("counts", {}).items():
        user_message_counts[int(k)] = v

    for k, v in data.get("thresholds", {}).items():
        user_thresholds_triggered[int(k)] = set(v)

    for k, v in data.get("timestamps", {}).items():
        user_timestamps[int(k)] = deque([datetime.fromisoformat(ts) for ts in v], maxlen=1000)

    for k, v in data.get("hourly", {}).items():
        user_hourly_triggered[int(k)] = set(v)

    for k, v in data.get("spam", {}).items():
        user_spam_triggered[int(k)] = datetime.fromisoformat(v).astimezone(timezone.utc)

async def count_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Count messages sent by users in a group chat and trigger actions based on thresholds.
    This function handles incoming messages, updates user message counts,
    checks for thresholds, and sends notifications if thresholds are met.
    Args:
        update (Update): The incoming update containing the message.
        context (ContextTypes.DEFAULT_TYPE): The context for the bot.
    Returns:
        None
    """
    if update.message.chat.type not in ["group", "supergroup"]:
        return

    now = datetime.now(timezone.utc)
    user = update.message.from_user
    user_id = user.id
    user_name = user.full_name or user.username or str(user_id)

    # Total message count
    user_message_counts[user_id] += 1
    total_count = user_message_counts[user_id]

    for threshold, msg in total_thresholds.items():
        if total_count >= threshold and threshold not in user_thresholds_triggered[user_id]:
            user_thresholds_triggered[user_id].add(threshold)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=msg.format(name=user_name)
            )

    # Sliding window count for hourly messages
    timestamps = user_timestamps[user_id]
    timestamps.append(now)

    one_hour_ago = now - timedelta(hours=1)
    timestamps = deque([ts for ts in timestamps if ts > one_hour_ago])
    user_timestamps[user_id] = timestamps

    count_last_hour = len(timestamps)
    for threshold, msg in hourly_thresholds.items():
        if count_last_hour >= threshold and threshold not in user_hourly_triggered[user_id]:
            user_hourly_triggered[user_id].add(threshold)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=msg.format(name=user_name)
            )

    # Short burst count
    one_minute_ago = now - timedelta(minutes=1)
    count_last_minute = len([ts for ts in timestamps if ts > one_minute_ago])

    if count_last_minute > 10:
        last_triggered = user_spam_triggered[user_id]
        if last_triggered.tzinfo is None:
            last_triggered = last_triggered.replace(tzinfo=timezone.utc)
        if (now - last_triggered) > timedelta(minutes=5):
            user_spam_triggered[user_id] = now
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Oh {user_name} ma ti calmi? Dio bestia oh"
            )

    save_data()

async def scansafatiche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle the /scansafatiche command to report message counts of users.
    This command checks if the bot is mentioned in the message and then
    compiles a report of message counts for users in the chat.
    Args:
        update (Update): The incoming update containing the command.
        context (ContextTypes.DEFAULT_TYPE): The context for the bot.
    Returns:
        None
    """
    message = update.message

    if message.chat.type not in ["group", "supergroup"]:
        return

    bot_username = (await context.bot.get_me()).username
    entities = message.entities or []

    mentioned = any(
        e.type == "mention" and message.text[e.offset:e.offset + e.length] == f"@{bot_username}"
        for e in entities
    )

    if not mentioned:
        return

    if not user_message_counts:
        await message.reply_text("Nessun messaggio da conteggiare!")
        return

    report = "*Gente che non ha veramente un cazzo da fare:*\n\n"
    for user_id, count in sorted(user_message_counts.items(), key=lambda x: -x[1]):
        try:
            member = await context.bot.get_chat_member(message.chat_id, user_id)
            name = member.user.full_name or member.user.username or str(user_id)
        except Exception:
            name = str(user_id)
        report += f"• {name}: {count} messaggi\n"

    await message.reply_text(report, parse_mode="Markdown")

async def rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not user_message_counts:
        await update.message.reply_text("Nessun messaggio ancora.")
        return

    top_users = sorted(user_message_counts.items(), key=lambda x: -x[1])[:3]
    text = "🏆 *Top 3 persone che non hanno un cazzo da fare:*\n\n"

    for idx, (user_id, count) in enumerate(top_users, 1):
        try:
            member = await context.bot.get_chat_member(update.message.chat_id, user_id)
            name = member.user.full_name or member.user.username or str(user_id)
        except Exception:
            name = str(user_id)
        text += f"{idx}. {name} — {count} messaggi\n"

    await update.message.reply_text(text, parse_mode="Markdown")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle the /reset command to clear all message counts and thresholds.
    This command resets the message counts, thresholds, timestamps,
    hourly triggers, and spam detection timestamps for all users.
    Args:
        update (Update): The incoming update containing the command.
        context (ContextTypes.DEFAULT_TYPE): The context for the bot.
    Returns:
        None
    """
    global user_message_counts, user_thresholds_triggered
    global user_timestamps, user_hourly_triggered, user_spam_triggered

    user_message_counts.clear()
    user_thresholds_triggered.clear()
    user_timestamps.clear()
    user_hourly_triggered.clear()
    user_spam_triggered.clear()

    save_data()
    await update.message.reply_text("Dati resettati!")

if __name__ == "__main__":
    """
    Main entry point for the bot.
    This function initializes the bot, loads existing data,
    and sets up command and message handlers.
    Args:
        None
    Returns:
        None
    """
    load_data()

    app = ApplicationBuilder().token(bot_key).build()

    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), count_messages))
    app.add_handler(CommandHandler("scansafatiche", scansafatiche))
    app.add_handler(CommandHandler("rank", rank))
    app.add_handler(CommandHandler("reset", reset))

    print("Bot is running...")
    app.run_polling()

