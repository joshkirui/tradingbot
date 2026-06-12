import subprocess
import os
import signal
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- DATA FROM YOUR CLIPBOARD ---
BOT_TOKEN = "8964245113:AAE-5cYyCYAGogkdA9VgYbyag0UuteAKIXs"
CHAT_ID   = 7890036882  # Note: Must be an integer for the library

# --- CONFIGURATION ---
# Replace 'trading_bot.py' with the actual filename of your bot
TRADING_BOT_FILENAME = "trading_bot.py" 

# This variable holds the running process
trading_process = None

async def start_trading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global trading_process
    
    # Security: Only YOU can start it
    if update.effective_user.id != CHAT_ID:
        await update.message.reply_text("❌ Unauthorized.")
        return

    if trading_process and trading_process.poll() is None:
        await update.message.reply_text("⚠️ FrostBot is already running on the terminal.")
        return

    try:
        # This command runs: python trading_bot.py
        trading_process = subprocess.Popen(["python", TRADING_BOT_FILENAME])
        await update.message.reply_text("🚀 <b>FrostBot STARTED</b> from terminal.")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to start: {e}")

async def stop_trading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global trading_process
    if update.effective_user.id != CHAT_ID: return

    if trading_process and trading_process.poll() is None:
        # Kill the process
        trading_process.terminate()
        trading_process = None
        await update.message.reply_text("🛑 <b>FrostBot STOPPED</b> on terminal.")
    else:
        await update.message.reply_text("❓ Bot is not currently running.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CHAT_ID: return
    
    if trading_process and trading_process.poll() is None:
        await update.message.reply_text("✅ <b>Status:</b> RUNNING")
    else:
        await update.message.reply_text("💤 <b>Status:</b> IDLE")

if __name__ == '__main__':
    # Initialize the Listener
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Add commands
    app.add_handler(CommandHandler("run", start_trading))
    app.add_handler(CommandHandler("stop", stop_trading))
    app.add_handler(CommandHandler("status", status))
    
    print("--- Manager Bot is Live ---")
    print("Waiting for /run command in Telegram...")
    app.run_polling()