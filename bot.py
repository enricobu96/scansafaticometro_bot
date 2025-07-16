from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from collections import defaultdict
from dotenv import load_dotenv
import os

load_dotenv()
bot_key = os.getenv("BOT_KEY")

# Keeps user message counts
user_message_counts = defaultdict(int)

# Tracks thresholds already triggered per user
user_thresholds_triggered = defaultdict(set)

# Define thresholds and messages
thresholds = {
    20: "Diocan {name} la smetti di spammare",
    100: "Qualcuno qui non ha davvero un cazzo da fare eh",
    200: "Oh ma che cazzo è {name}, torna a lavorare",
    500: "{name} ha trasceso il significato di lavorare, ben fatto compagno"
}

async def count_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type in ["group", "supergroup"]:
        user = update.message.from_user
        user_id = user.id
        user_name = user.full_name or user.username or str(user_id)

        # Increase count
        user_message_counts[user_id] += 1
        count = user_message_counts[user_id]

        # Check thresholds
        for threshold, message in thresholds.items():
            if count >= threshold and threshold not in user_thresholds_triggered[user_id]:
                user_thresholds_triggered[user_id].add(threshold)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=message.format(name=user_name)
                )

# Respond to /scansafatiche @botname
async def scansafatiche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    # Only respond in groups
    if message.chat.type not in ["group", "supergroup"]:
        return

    # Check if the bot is mentioned
    bot_username = (await context.bot.get_me()).username
    entities = message.entities or []

    mentioned = any(
        e.type == "mention" and message.text[e.offset:e.offset + e.length] == f"@{bot_username}"
        for e in entities
    )

    if not mentioned:
        return  # bot was not tagged

    # If no messages have been counted
    if not user_message_counts:
        await message.reply_text("Nessun messaggio da conteggiare!")
        return

    # Build the report
    report = "📊 *Conteggio messaggi dei scansafatiche:*\n\n"
    for user_id, count in sorted(user_message_counts.items(), key=lambda x: -x[1]):
        try:
            member = await context.bot.get_chat_member(message.chat_id, user_id)
            name = member.user.full_name or member.user.username or str(user_id)
        except Exception:
            name = str(user_id)
        report += f"• {name}: {count} messaggi\n"

    await message.reply_text(report, parse_mode="Markdown")

# ✅ Run the bot
if __name__ == "__main__":
    app = ApplicationBuilder().token(bot_key).build()

    # Count all group messages
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), count_messages))

    # Command handler
    app.add_handler(CommandHandler("scansafatiche", scansafatiche))

    print("Bot is running...")
    app.run_polling()

