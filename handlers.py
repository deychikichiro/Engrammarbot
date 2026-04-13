import os
import base64
import cv2
from datetime import datetime
from groq import Groq
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import (
    GROQ_API_KEY, PLANS, FREE_LIMIT,
    SYSTEM_PROMPT, LOGS_DIR, MEDIA_DIR, ADMIN_ID
)
from database import ensure_user, check_and_increment, get_usage, set_plan, get_user

client = Groq(api_key=GROQ_API_KEY)

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)


# ── Helpers ──────────────────────────────────────────────────────────────────

def upgrade_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1 Week — $1 (75 Stars)",       callback_data="pay_weekly")],
        [InlineKeyboardButton("1 Month — $3 (230 Stars)",     callback_data="pay_monthly")],
        [InlineKeyboardButton("1 Year — $15 (1150 Stars)",    callback_data="pay_yearly")],
        [InlineKeyboardButton("Unlimited — $20 (1500 Stars)", callback_data="pay_unlimited")],
    ])


def log_message(user_id: int, username: str, first_name: str, message: str):
    log_file = os.path.join(LOGS_DIR, f"{user_id}.txt")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not os.path.exists(log_file):
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"User ID  : {user_id}\n")
            f.write(f"Username : @{username or 'N/A'}\n")
            f.write(f"Name     : {first_name or 'N/A'}\n")
            f.write(f"{'='*40}\n\n")

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n\n")


async def send_invoice_to(context, chat_id: int, plan_key: str):
    plan = PLANS[plan_key]
    await context.bot.send_invoice(
        chat_id=chat_id,
        title=f"{plan['label']} Plan",
        description=f"Unlimited grammar corrections for {plan['label']} ({plan['price']})",
        payload=plan_key,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(plan["label"], plan["stars"])]
    )


async def send_plan_message(user, reply_fn):
    messages_today, plan, plan_expiry = get_usage(user.id)

    if plan == "free":
        remaining = FREE_LIMIT - messages_today
        await reply_fn(
            f"Plan: Free\nUsed today: {messages_today}/{FREE_LIMIT}\nRemaining: {remaining}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Upgrade Plan", callback_data="show_upgrade")]]
            )
        )
    elif plan == "unlimited":
        await reply_fn(f"Plan: Unlimited\nUsed today: {messages_today}\nNo limits!")
    else:
        await reply_fn(
            f"Plan: {plan.capitalize()}\nExpires: {plan_expiry}\nUsed today: {messages_today}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Upgrade Plan", callback_data="show_upgrade")]]
            )
        )


def is_allowed(user_id: int) -> bool:
    return check_and_increment(user_id)


def image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def extract_middle_frame(video_path: str, output_path: str) -> bool:
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)
    ret, frame = cap.read()
    cap.release()
    if ret:
        cv2.imwrite(output_path, frame)
    return ret


# ── Command handlers ──────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.username, user.first_name)
    log_message(user.id, user.username, user.first_name, "/start")

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("My Plan", callback_data="show_plan"),
        InlineKeyboardButton("Upgrade", callback_data="show_upgrade"),
    ]])
    await update.message.reply_text(
        f"Hello, {user.first_name}! Welcome!\n\n"
        "I can:\n"
        "- Correct your English grammar (send text or voice)\n"
        "- Translate text from photos\n"
        "- Translate speech or text from videos\n\n"
        "Free plan: 20 requests/day",
        reply_markup=keyboard
    )


async def plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.username, user.first_name)
    await send_plan_message(user, update.message.reply_text)


async def upgrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Choose a plan:", reply_markup=upgrade_keyboard())


async def admin_setplan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized.")
        return

    args = context.args
    valid_plans = ["free", "weekly", "monthly", "yearly", "unlimited"]

    if len(args) != 2 or args[1] not in valid_plans:
        await update.message.reply_text(
            f"Usage: /setplan <user_id> <plan>\nPlans: {', '.join(valid_plans)}"
        )
        return

    user_id = int(args[0])
    if not get_user(user_id):
        await update.message.reply_text(f"User {user_id} not found.")
        return

    set_plan(user_id, args[1])
    await update.message.reply_text(f"User {user_id} set to {args[1]} plan.")


# ── Callback & payment handlers ───────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "show_plan":
        await send_plan_message(query.from_user, query.message.reply_text)
    elif query.data == "show_upgrade":
        await query.message.reply_text("Choose a plan:", reply_markup=upgrade_keyboard())
    elif query.data.startswith("pay_"):
        plan_key = query.data.replace("pay_", "")
        await send_invoice_to(context, query.message.chat_id, plan_key)


async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    plan_key = update.message.successful_payment.invoice_payload
    set_plan(user.id, plan_key)
    log_message(user.id, user.username, user.first_name, f"[PAYMENT] {plan_key}")
    await update.message.reply_text(
        f"Payment successful! Your {PLANS[plan_key]['label']} plan is now active."
    )


# ── Translation helpers ───────────────────────────────────────────────────────

async def translate_text(text: str, language: str) -> str:
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": f"Translate the following text to {language}. Return only the translation, nothing else."},
            {"role": "user",   "content": text}
        ]
    )
    return response.choices[0].message.content


async def extract_and_translate_image(image_path: str, language: str) -> str:
    b64 = image_to_base64(image_path)
    response = client.chat.completions.create(
        model="llama-3.2-11b-vision-preview",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": f"Extract all visible text from this image and translate it to {language}. Format: first show the original text, then the translation."}
            ]
        }]
    )
    return response.choices[0].message.content


# ── Message handlers ──────────────────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_message = update.message.text
    pending = context.user_data.get("pending")

    # ── Handle pending translation states ──
    if pending:
        action = pending.get("action")

        # User is choosing speech or text for video
        if action == "video_choice":
            choice = user_message.strip().lower()
            if choice not in ("speech", "text"):
                await update.message.reply_text("Please reply with 'speech' or 'text'.")
                return
            context.user_data["pending"]["action"] = f"video_{choice}_language"
            await update.message.reply_text("What language should I translate to?")
            return

        # User is providing target language for photo
        if action == "photo_language":
            language = user_message.strip()
            file_path = pending.get("file_path")
            context.user_data.pop("pending", None)
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            try:
                result = await extract_and_translate_image(file_path, language)
                log_message(user.id, user.username, user.first_name, f"[PHOTO TRANSLATE → {language}]")
                await update.message.reply_text(result)
            except Exception as e:
                print(f"[ERROR] photo translate: {e}")
                await update.message.reply_text("Something went wrong. Please try again.")
            return

        # User is providing target language for video speech
        if action == "video_speech_language":
            language = user_message.strip()
            file_path = pending.get("file_path")
            context.user_data.pop("pending", None)
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            try:
                with open(file_path, "rb") as f:
                    transcription = client.audio.transcriptions.create(
                        model="whisper-large-v3", file=f
                    )
                transcript = transcription.text
                translation = await translate_text(transcript, language)
                log_message(user.id, user.username, user.first_name, f"[VIDEO SPEECH TRANSLATE → {language}]")
                await update.message.reply_text(
                    f"Transcribed: {transcript}\n\nTranslation ({language}):\n{translation}"
                )
            except Exception as e:
                print(f"[ERROR] video speech translate: {e}")
                await update.message.reply_text("Something went wrong. Please try again.")
            return

        # User is providing target language for video text
        if action == "video_text_language":
            language = user_message.strip()
            file_path = pending.get("file_path")
            context.user_data.pop("pending", None)
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            try:
                frame_path = file_path.replace(".mp4", "_frame.jpg")
                if not extract_middle_frame(file_path, frame_path):
                    await update.message.reply_text("Could not extract frame from video.")
                    return
                result = await extract_and_translate_image(frame_path, language)
                os.remove(frame_path)
                log_message(user.id, user.username, user.first_name, f"[VIDEO TEXT TRANSLATE → {language}]")
                await update.message.reply_text(result)
            except Exception as e:
                print(f"[ERROR] video text translate: {e}")
                await update.message.reply_text("Something went wrong. Please try again.")
            return

    # ── Normal grammar correction ──
    if len(user_message.split()) < 2:
        await update.message.reply_text("Please send at least a full sentence to correct.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        ensure_user(user.id, user.username, user.first_name)

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_message}
            ]
        )
        correction = response.choices[0].message.content

        if correction.strip() == "NO_CORRECTION":
            await update.message.reply_text(
                "I only correct grammar. Please send me a sentence or text to correct."
            )
            return

        if not is_allowed(user.id):
            await update.message.reply_text(
                "You've reached your 20 free corrections today.\n\nUpgrade to keep going:",
                reply_markup=upgrade_keyboard()
            )
            return

        log_message(user.id, user.username, user.first_name, user_message)
        await update.message.reply_text(correction)

    except Exception as e:
        print(f"[ERROR] handle_text: {e}")
        await update.message.reply_text("Something went wrong. Please try again.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.username, user.first_name)

    if not is_allowed(user.id):
        await update.message.reply_text(
            "You've reached your 20 free requests today.\n\nUpgrade to keep going:",
            reply_markup=upgrade_keyboard()
        )
        return

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_media_dir = os.path.join(MEDIA_DIR, str(user.id))
        os.makedirs(user_media_dir, exist_ok=True)

        photo = update.message.photo[-1]  # highest resolution
        photo_file = await photo.get_file()
        file_path = os.path.join(user_media_dir, f"photo_{timestamp}.jpg")
        await photo_file.download_to_drive(file_path)

        context.user_data["pending"] = {"action": "photo_language", "file_path": file_path}
        await update.message.reply_text("What language should I translate the text to?")

    except Exception as e:
        print(f"[ERROR] handle_photo: {e}")
        await update.message.reply_text("Something went wrong. Please try again.")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.username, user.first_name)

    if not is_allowed(user.id):
        await update.message.reply_text(
            "You've reached your 20 free corrections today.\n\nUpgrade to keep going:",
            reply_markup=upgrade_keyboard()
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_media_dir = os.path.join(MEDIA_DIR, str(user.id))
        os.makedirs(user_media_dir, exist_ok=True)

        voice_file = await update.message.voice.get_file()
        file_path = os.path.join(user_media_dir, f"voice_{timestamp}.ogg")
        await voice_file.download_to_drive(file_path)

        with open(file_path, "rb") as audio:
            transcription = client.audio.transcriptions.create(
                model="whisper-large-v3", file=audio
            )

        transcript_text = transcription.text
        log_message(user.id, user.username, user.first_name, f"[VOICE] {transcript_text}")

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": transcript_text}
            ]
        )
        await update.message.reply_text(
            f"Transcribed: {transcript_text}\n\n{response.choices[0].message.content}"
        )

    except Exception as e:
        print(f"[ERROR] handle_voice: {e}")
        await update.message.reply_text("Something went wrong. Please try again.")


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.username, user.first_name)

    if not is_allowed(user.id):
        await update.message.reply_text(
            "You've reached your 20 free requests today.\n\nUpgrade to keep going:",
            reply_markup=upgrade_keyboard()
        )
        return

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

        context.user_data["pending"] = {"action": "video_choice", "file_path": file_path}
        await update.message.reply_text(
            "What do you want me to translate?\n\nReply with:\n'speech' — translate spoken audio\n'text' — translate text visible on screen"
        )

    except Exception as e:
        print(f"[ERROR] handle_video: {e}")
        await update.message.reply_text("Something went wrong. Please try again.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print(f"[ERROR] {context.error}")
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("Something went wrong. Please try again.")
