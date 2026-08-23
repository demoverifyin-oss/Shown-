# Maccaron Referral Automation Bot (Pro Edition)

Hey there! This is a professional-grade Telegram bot designed to automate referrals for maccaron.in. It handles everything from account creation to email verification using temporary mail services.

**Branded and Enhanced by @prime5d.**

## Features
- **Clean UI**: Easy to use Telegram interface with simple commands and inline buttons.
- **Auto-Referral**: Support for manual referrals and Firebase-based automation.
- **Deep Extraction**: Robust Firebase scanning logic to find OTPs hidden in APKs or complex database structures.
- **Secure Vault**: Uses a local SQLite database to safely store your referral codes and tracking data.
- **Robust Logic**: Asynchronous execution for fast performance and reliability.
- **Email Automation**: Automatically handles mail.tm verification links.

## How to Setup

1. **Install Dependencies**:
   Make sure you have Python 3.8+ installed. Run:
   ```bash
   pip install httpx python-telegram-bot
   ```

2. **Configure the Bot**:
   Open `src/bot.py` and you can tweak the database settings if needed.

3. **Run the Bot**:
   Get a bot token from [@BotFather](https://t.me/BotFather) and run:
   ```bash
   python -m src.bot YOUR_BOT_TOKEN
   ```

## Commands
- `/start`: See the welcome message and help.
- `/set_code <code>`: Save your referral code to the database.
- `/refer`: Start a manual referral process (interactive).
- `/auto`: Start scanning a Firebase panel for auto-referrals.
- `/stats`: Check your successful referral counts.

## Note
This tool was built for educational purposes. Use it responsibly and respect the terms of service of the target platforms.

**Made with ❤️ by @prime5d.**
