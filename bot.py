from telegram import Update, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, PreCheckoutQueryHandler, filters
)

from config import TELEGRAM_TOKEN
from database import init_db
from handlers import (
    start, plan_command, upgrade_command, admin_setplan,
    button_handler, precheckout_handler, successful_payment_handler,
    handle_text, handle_voice, handle_video, error_handler
)


async def post_init(application: Application):
    await application.bot.set_my_commands([
        BotCommand("start",   "Start the bot"),
        BotCommand("plan",    "Check your plan and daily usage"),
        BotCommand("upgrade", "Upgrade your plan"),
    ])


def main():
    if not TELEGRAM_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not set in .env file")
        return

    init_db()

    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    # Commands
    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("plan",    plan_command))
    app.add_handler(CommandHandler("upgrade", upgrade_command))
    app.add_handler(CommandHandler("setplan", admin_setplan))

    # Inline buttons & payments
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT  & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE,                    handle_voice))
    app.add_handler(MessageHandler(filters.VIDEO | filters.VIDEO_NOTE, handle_video))

    app.add_error_handler(error_handler)

    print("Bot is running... Press Ctrl+C to stop")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
