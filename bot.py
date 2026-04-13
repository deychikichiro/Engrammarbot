import os
from groq import Groq
from dotenv import load_dotenv
from datetime import datetime
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# Load environment variables
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Initialize Groq client
client = Groq(api_key=GROQ_API_KEY)

# Logs and media folders
LOGS_DIR = "logs"
MEDIA_DIR = "media"
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)

# System prompt for the grammar assistant
SYSTEM_PROMPT = """You are an English grammar assistant. Your job is to correct grammar mistakes in the user's text.

For each message the user sends:
1. Identify any grammar, spelling, or punctuation errors
2. Format your response EXACTLY as:
   WRONG: [the incorrect text]
   REASON: [why it's wrong - cite the grammar rule]
   CORRECT: [the corrected version]

If there are multiple errors, list each one separately.

If the text has no errors, respond with:
   CORRECT: The text is already correct.

Be concise and educational. Focus on accuracy."""


def log_message(user_id: int, username: str, first_name: str, message: str) -> None:
    """Save user message to their individual log file."""
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


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages."""
    user = update.effective_user
    user_message = update.message.text

    log_message(user.id, user.username, user.first_name, user_message)
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
        await update.message.reply_text(correction)

    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")
        print(f"Error: {e}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle voice messages — transcribe then grammar correct."""
    user = update.effective_user

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        # Download and save voice file permanently
        voice_file = await update.message.voice.get_file()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_media_dir = os.path.join(MEDIA_DIR, str(user.id))
        os.makedirs(user_media_dir, exist_ok=True)
        file_path = os.path.join(user_media_dir, f"voice_{timestamp}.ogg")
        await voice_file.download_to_drive(file_path)

        # Transcribe with Groq Whisper
        with open(file_path, "rb") as audio:
            transcription = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio
            )
        transcript_text = transcription.text

        # Log the transcribed message
        log_message(user.id, user.username, user.first_name, f"[VOICE] {transcript_text}")

        # Grammar correct the transcript
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": transcript_text}
            ]
        )
        correction = response.choices[0].message.content

        await update.message.reply_text(
            f"Transcribed: {transcript_text}\n\n{correction}"
        )

    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")
        print(f"Error: {e}")


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save video and reject with message."""
    user = update.effective_user

    try:
        # Download and save video file
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    log_message(user.id, user.username, user.first_name, "/start")

    await update.message.reply_text(
        "Welcome to English Grammar Assistant!\n\n"
        "Send me any text or voice message and I'll correct it for you. I'll show:\n"
        "- What was wrong\n"
        "- Why it's wrong\n"
        "- The correct version"
    )


def main() -> None:
    if not TELEGRAM_TOKEN or not GROQ_API_KEY:
        print("Error: TELEGRAM_BOT_TOKEN or GROQ_API_KEY not set in .env file")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(MessageHandler(filters.COMMAND, start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.VIDEO | filters.VIDEO_NOTE, handle_video))

    print("Bot is running... Press Ctrl+C to stop")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
