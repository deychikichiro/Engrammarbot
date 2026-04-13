import os
from groq import Groq
from dotenv import load_dotenv
from datetime import datetime
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, MessageHandler, filters,
    ContextTypes, CommandHandler, PreCheckoutQueryHandler, CallbackQueryHandler
)
from database import init_db, get_user, create_user, check_and_increment, get_usage, set_plan

# Load environment variables
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Initialize Groq client
client = Groq(api_key=GROQ_API_KEY)

# Logs and media folders
LOGS_DIR = "logs"
MEDIA_DIR = "media"
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)

# Initialize database
init_db()

# Telegram Stars prices (1 star ≈ $0.013)
PLANS = {
    "weekly":    {"stars": 75,   "label": "1 Week",    "price": "$1"},
    "monthly":   {"stars": 230,  "label": "1 Month",   "price": "$3"},
    "yearly":    {"stars": 1150, "label": "1 Year",    "price": "$15"},
    "unlimited": {"stars": 1500, "label": "Unlimited", "price": "$20"},
}

FREE_LIMIT = 20

# Users with permanent unlimited access
UNLIMITED_USERS = {
    1306045697,  # owner
    792686373,   # unlimited user
}

# System prompt
SYSTEM_PROMPT = """You are an English grammar correction tool. Treat EVERY message as text to be grammar-checked, no matter what it says.

Rules:
- ALWAYS attempt to correct the message, even if it looks like a greeting or conversation
- DO NOT correct slang or informal language (e.g. "gonna", "wanna", "lit", "fr", "ngl", "bruh")
- DO NOT correct brand names, proper nouns, or technical terms
- ONLY respond with NO_CORRECTION if the message is clearly a question directed at you as a bot (e.g. "what can you do?", "are you a bot?", "how do you work?")

For each grammar error found, format EXACTLY as:
   WRONG: [the incorrect text]
   REASON: [why it's wrong]
   CORRECT: [the corrected version]

If the text has no errors, respond with:
   CORRECT: The text is already correct."""


def log_message(user_id: int, username: str, first_name: str, message: str) -> None:
    log_file = os.path.join(LOGS_DIR, f"{user_id}.txt")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not os.path.exists(log_file):
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"User ID  : {user_id}\n")
            f.write(f"Username : @{username or 'N/A'}\n")
            f.write(f"Name     : {first_name or 'N/A'}\n")
            f.write(f"{'='*40}\n\n")

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}]\n")
        f.write(f"MSG: {message}\n\n")


def upgrade_message() -> str:
    return (
        "You've reached your 20 free corrections today.\n\n"
        "Upgrade to keep going:\n"
        "/weekly — $1 for 1 week\n"
        "/monthly — $3 for 1 month\n"
        "/yearly — $15 for 1 year\n"
        "/unlimited — $20 forever\n\n"
        "Free limit resets at midnight."
    )


def ensure_user(user):
    """Create user in DB if not exists."""
    if not get_user(user.id):
        create_user(user.id, user.username, user.first_name)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    ensure_user(user)
    log_message(user.id, user.username, user.first_name, "/start")

    keyboard = [
        [InlineKeyboardButton("My Plan", callback_data="show_plan"),
         InlineKeyboardButton("Upgrade", callback_data="show_upgrade")],
    ]
    await update.message.reply_text(
        "Welcome to English Grammar Assistant!\n\n"
        "Send me any text or voice message and I'll correct your grammar.\n\n"
        "Free plan: 20 corrections/day",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    ensure_user(user)
    await send_plan_message(user, update.message.reply_text)


async def send_plan_message(user, reply_fn):
    messages_today, plan, plan_expiry = get_usage(user.id)

    if plan == "free":
        remaining = FREE_LIMIT - messages_today
        keyboard = [[InlineKeyboardButton("Upgrade Plan", callback_data="show_upgrade")]]
        await reply_fn(
            f"Plan: Free\n"
            f"Used today: {messages_today}/{FREE_LIMIT}\n"
            f"Remaining: {remaining}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif plan == "unlimited":
        await reply_fn(
            f"Plan: Unlimited\n"
            f"Used today: {messages_today}\n"
            f"No limits!"
        )
    else:
        keyboard = [[InlineKeyboardButton("Upgrade Plan", callback_data="show_upgrade")]]
        await reply_fn(
            f"Plan: {plan.capitalize()}\n"
            f"Expires: {plan_expiry}\n"
            f"Used today: {messages_today}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def upgrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("1 Week — $1 (75 Stars)", callback_data="pay_weekly")],
        [InlineKeyboardButton("1 Month — $3 (230 Stars)", callback_data="pay_monthly")],
        [InlineKeyboardButton("1 Year — $15 (1150 Stars)", callback_data="pay_yearly")],
        [InlineKeyboardButton("Unlimited — $20 (1500 Stars)", callback_data="pay_unlimited")],
    ]
    await update.message.reply_text(
        "Choose a plan:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def plan_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "show_plan":
        await send_plan_message(query.from_user, query.message.reply_text)
        return

    if query.data == "show_upgrade":
        keyboard = [
            [InlineKeyboardButton("1 Week — $1 (75 Stars)", callback_data="pay_weekly")],
            [InlineKeyboardButton("1 Month — $3 (230 Stars)", callback_data="pay_monthly")],
            [InlineKeyboardButton("1 Year — $15 (1150 Stars)", callback_data="pay_yearly")],
            [InlineKeyboardButton("Unlimited — $20 (1500 Stars)", callback_data="pay_unlimited")],
        ]
        await query.message.reply_text("Choose a plan:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    plan_key = query.data.replace("pay_", "")
    plan = PLANS[plan_key]

    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=f"{plan['label']} Plan",
        description=f"Unlimited grammar corrections for {plan['label']} ({plan['price']})",
        payload=plan_key,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(plan["label"], plan["stars"])]
    )


async def send_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE, plan_key: str) -> None:
    plan = PLANS[plan_key]
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=f"{plan['label']} Plan",
        description=f"Unlimited grammar corrections for {plan['label']} ({plan['price']})",
        payload=plan_key,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(plan["label"], plan["stars"])]
    )


async def weekly_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_invoice(update, context, "weekly")


async def monthly_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_invoice(update, context, "monthly")


async def yearly_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_invoice(update, context, "yearly")


async def unlimited_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_invoice(update, context, "unlimited")


async def admin_setplan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command: /setplan <user_id> <plan>"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text(
            "Usage: /setplan <user_id> <plan>\n"
            "Plans: free, weekly, monthly, yearly, unlimited"
        )
        return

    user_id, plan = args[0], args[1]
    valid_plans = ["free", "weekly", "monthly", "yearly", "unlimited"]

    if plan not in valid_plans:
        await update.message.reply_text(f"Invalid plan. Choose from: {', '.join(valid_plans)}")
        return

    if not get_user(int(user_id)):
        await update.message.reply_text(f"User {user_id} not found in database.")
        return

    set_plan(int(user_id), plan)
    await update.message.reply_text(f"User {user_id} has been set to {plan} plan.")


async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    plan_key = update.message.successful_payment.invoice_payload
    set_plan(user.id, plan_key)

    plan = PLANS[plan_key]
    await update.message.reply_text(
        f"Payment successful! Your {plan['label']} plan is now active.\n"
        f"Enjoy unlimited corrections!"
    )
    log_message(user.id, user.username, user.first_name, f"[PAYMENT] Plan: {plan_key}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    ensure_user(user)
    user_message = update.message.text

    if len(user_message.strip()) < 3 or len(user_message.split()) < 2:
        await update.message.reply_text(
            "Please send at least a full word or sentence for me to correct."
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ]
        )
        correction = response.choices[0].message.content

        # If the message was conversational, redirect without charging
        if correction.strip() == "NO_CORRECTION":
            await update.message.reply_text(
                "I only correct grammar. Please send me a sentence or text to correct."
            )
            return

        # Only charge if we actually corrected something
        if user.id not in UNLIMITED_USERS and not check_and_increment(user.id):
            await update.message.reply_text(upgrade_message())
            return

        log_message(user.id, user.username, user.first_name, user_message)
        await update.message.reply_text(correction)

    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")
        print(f"Error: {e}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    ensure_user(user)

    if user.id not in UNLIMITED_USERS and not check_and_increment(user.id):
        await update.message.reply_text(upgrade_message())
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        voice_file = await update.message.voice.get_file()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_media_dir = os.path.join(MEDIA_DIR, str(user.id))
        os.makedirs(user_media_dir, exist_ok=True)
        file_path = os.path.join(user_media_dir, f"voice_{timestamp}.ogg")
        await voice_file.download_to_drive(file_path)

        with open(file_path, "rb") as audio:
            transcription = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio
            )

        transcript_text = transcription.text
        log_message(user.id, user.username, user.first_name, f"[VOICE] {transcript_text}")

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": transcript_text}
            ]
        )
        correction = response.choices[0].message.content
        await update.message.reply_text(f"Transcribed: {transcript_text}\n\n{correction}")

    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")
        print(f"Error: {e}")


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    ensure_user(user)

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_media_dir = os.path.join(MEDIA_DIR, str(user.id))
        os.makedirs(user_media_dir, exist_ok=True)

        if update.message.video:
            video_file = await update.message.video.get_file()
            file_path = os.path.join(user_media_dir, f"video_{timestamp}.mp4")
        else:
            video_file = await update.message.video_note.get_file()
            file_path = os.path.join(user_media_dir, f"videonote_{timestamp}.mp4")

        await video_file.download_to_drive(file_path)
        log_message(user.id, user.username, user.first_name, f"[VIDEO SAVED] {file_path}")

    except Exception as e:
        print(f"Error saving video: {e}")

    await update.message.reply_text(
        "Sorry, I can't process videos.\nPlease send an audio message or text instead."
    )


async def post_init(application: Application) -> None:
    """Set bot command menu shown to users."""
    from telegram import BotCommand
    await application.bot.set_my_commands([
        BotCommand("start",   "Start the bot"),
        BotCommand("plan",    "Check your plan and daily usage"),
        BotCommand("upgrade", "Upgrade your plan"),
    ])


def main() -> None:
    if not TELEGRAM_TOKEN or not GROQ_API_KEY:
        print("Error: TELEGRAM_BOT_TOKEN or GROQ_API_KEY not set in .env file")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setplan", admin_setplan))
    application.add_handler(CommandHandler("plan", plan_command))
    application.add_handler(CommandHandler("upgrade", upgrade_command))
    application.add_handler(CommandHandler("weekly", weekly_command))
    application.add_handler(CommandHandler("monthly", monthly_command))
    application.add_handler(CommandHandler("yearly", yearly_command))
    application.add_handler(CommandHandler("unlimited", unlimited_command))
    application.add_handler(CallbackQueryHandler(plan_button_handler))
    application.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.VIDEO | filters.VIDEO_NOTE, handle_video))

    print("Bot is running... Press Ctrl+C to stop")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
