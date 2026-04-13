import os
from dotenv import load_dotenv

load_dotenv()

# API credentials
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY")
ADMIN_ID       = int(os.getenv("ADMIN_ID", "0"))

# Folders
LOGS_DIR  = "logs"
MEDIA_DIR = "media"

# Free tier limit (messages per day)
FREE_LIMIT = 20

# Users with permanent unlimited access
UNLIMITED_USERS = {
    1306045697,  # owner
    792686373,   # unlimited user
}

# Telegram Stars pricing (1 star ≈ $0.013)
PLANS = {
    "weekly":    {"stars": 75,   "label": "1 Week",    "price": "$1"},
    "monthly":   {"stars": 230,  "label": "1 Month",   "price": "$3"},
    "yearly":    {"stars": 1150, "label": "1 Year",    "price": "$15"},
    "unlimited": {"stars": 1500, "label": "Unlimited", "price": "$20"},
}

# AI system prompt
SYSTEM_PROMPT = """You are Transgrammar, a professional grammar correction assistant. Be concise and direct.

Rules:
- Treat EVERY message as text to be grammar-checked
- DO NOT correct slang or informal language (e.g. "gonna", "wanna", "lit", "fr", "ngl", "bruh")
- DO NOT correct brand names, proper nouns, or technical terms
- ONLY respond with NO_CORRECTION if the message is clearly a question directed at you (e.g. "what can you do?", "are you a bot?")

For each grammar error found, format EXACTLY as:
WRONG: [incorrect text]
REASON: [rule]
CORRECT: [corrected version]

If no errors, respond with:
CORRECT: No errors found."""
