# English Grammar Assistant Telegram Bot

A Telegram bot that corrects grammar mistakes and explains the rules.

## Setup

### 1. Install Python (if not already installed)
- Download from https://www.python.org/
- Make sure to check "Add Python to PATH" during installation

### 2. Clone or create the project folder
```bash
cd your-project-folder
```

### 3. Create a virtual environment (recommended)
```bash
python -m venv venv

# On Windows:
venv\Scripts\activate

# On Mac/Linux:
source venv/bin/activate
```

### 4. Install dependencies
```bash
pip install -r requirements.txt
```

### 5. Set up environment variables
1. Rename `.env.example` to `.env`
2. Add your tokens:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_token_here
   CLAUDE_API_KEY=your_claude_api_key_here
   ```

### 6. Run the bot
```bash
python bot.py
```

The bot will start polling for messages. When you see "Bot is running...", it's ready!

## How to use

1. Open Telegram and find your bot by username
2. Send `/start` to see the welcome message
3. Send any text and the bot will correct it

Example:
```
You: I is very happy today
Bot: WRONG: I is very happy today
     REASON: Subject-verb agreement error. "I" is first person singular and requires "am", not "is".
     CORRECT: I am very happy today.
```

## Deployment (later)

When ready to deploy to the cloud:
- Deploy to Render or Railway (instructions in separate guide)
- Bot will run 24/7 without your computer being on
