import subprocess
import os
import json
import asyncio
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    filters, ConversationHandler, ContextTypes, CallbackQueryHandler
)
from telegram.constants import ParseMode
from telegram.request import HTTPXRequest  # Required for the Timeout Fix

# --- CONFIGURATION ---
BOT_TOKEN = "8964245113:AAE-5cYyCYAGogkdA9VgYbyag0UuteAKIXs"
CHAT_ID   = 7890036882 
TRADING_BOT_FILENAME = "frostbotlive.py" 
ACCOUNTS_FILE = "accounts.json"
JOURNAL_FILE  = "openclaw_journal.json"

# Conversation States
NICKNAME, LOGIN, PASSWORD, SERVER = range(4)
active_processes = {}

def load_accounts():
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, "r") as f: return json.load(f)
    return {}

def save_accounts(accounts):
    with open(ACCOUNTS_FILE, "w") as f: json.dump(accounts, f, indent=4)

# --- AI ANALYSIS ---
async def run_ai_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != CHAT_ID: return
    
    if not os.path.exists(JOURNAL_FILE):
        await context.bot.send_message(chat_id=CHAT_ID, text="❌ No journal found yet.")
        return

    await context.bot.send_message(chat_id=CHAT_ID, text="🧠 <b>OpenClaw AI</b> is analyzing setups...", parse_mode=ParseMode.HTML)

    try:
        cmd = f"openclaw analyze {JOURNAL_FILE} --summary"
        process = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await process.communicate()
        report = stdout.decode() if stdout else "⚠️ AI Report empty."
        await context.bot.send_message(chat_id=CHAT_ID, text=f"📊 <b>AI REVIEW</b>\n\n{report[:4000]}", parse_mode=ParseMode.HTML)
    except Exception as e:
        await context.bot.send_message(chat_id=CHAT_ID, text=f"❌ AI Error: {e}")

# --- COMMANDS ---
async def start_setup(update, context):
    if update.effective_user.id != CHAT_ID: return
    await update.message.reply_text("🏦 <b>Multi-Account Setup</b>\nEnter a Nickname (e.g. Live):", parse_mode=ParseMode.HTML)
    return NICKNAME

async def get_nickname(update, context):
    context.user_data['n'] = update.message.text
    await update.message.reply_text(f"🏦 Enter ID for {update.message.text}:")
    return LOGIN

async def get_login(update, context):
    context.user_data['i'] = update.message.text
    await update.message.reply_text("🔑 Enter Password:")
    return PASSWORD

async def get_password(update, context):
    context.user_data['p'] = update.message.text
    await update.message.reply_text("🌐 Enter Server Name:")
    return SERVER

async def get_server(update, context):
    accs = load_accounts()
    n = context.user_data['n']
    accs[n] = {"login": context.user_data['i'], "password": context.user_data['p'], "server": update.message.text}
    save_accounts(accs)
    await update.message.reply_text(f"✅ Account {n} saved!")
    return ConversationHandler.END

async def show_menu(update, context):
    if update.effective_user.id != CHAT_ID: return
    accs = load_accounts()
    if not accs:
        await update.message.reply_text("❌ No accounts. Use /add_account")
        return
    keys = [[InlineKeyboardButton(f"🚀 Run {n}", callback_data=f"r_{n}")] for n in accs.keys()]
    keys.append([InlineKeyboardButton("🧠 AI Analysis", callback_data="ai_analyze")])
    await update.message.reply_text("<b>FrostBot Control:</b>", reply_markup=InlineKeyboardMarkup(keys), parse_mode=ParseMode.HTML)

async def handle_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "ai_analyze":
        await run_ai_analysis(update, context)
        return
    
    nick = query.data.replace("r_", "")
    if not os.path.exists(TRADING_BOT_FILENAME):
        await query.edit_message_text(f"❌ Error: <code>{TRADING_BOT_FILENAME}</code> not found!")
        return

    # Check if already running in this session
    if nick in active_processes and active_processes[nick].poll() is None:
        await query.edit_message_text(f"⚠️ {nick} is already running.")
        return

    active_processes[nick] = subprocess.Popen([sys.executable, TRADING_BOT_FILENAME, nick])
    await query.edit_message_text(f"🚀 <b>Bot Launching:</b> {nick}\nLogs in terminal.", parse_mode=ParseMode.HTML)

async def stop_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global active_processes
    for nick, proc in active_processes.items():
        if proc.poll() is None:
            proc.terminate()
            await update.message.reply_text(f"🛑 Stopped: {nick}")
    active_processes = {}

if __name__ == '__main__':
    # --- THE TIMEOUT FIX ---
    # We increase timeouts to 30 seconds to handle Python 3.14 Alpha lag
    t_request = HTTPXRequest(connect_timeout=30, read_timeout=30)
    
    app = ApplicationBuilder().token(BOT_TOKEN).request(t_request).build()
    
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("add_account", start_setup)],
        states={NICKNAME:[MessageHandler(filters.TEXT, get_nickname)], 
                LOGIN:[MessageHandler(filters.TEXT, get_login)], 
                PASSWORD:[MessageHandler(filters.TEXT, get_password)], 
                SERVER:[MessageHandler(filters.TEXT, get_server)]},
        fallbacks=[]
    ))
    
    app.add_handler(CommandHandler("run", show_menu))
    app.add_handler(CommandHandler("stop", stop_all))
    app.add_handler(CallbackQueryHandler(handle_click))
    
    print("--- Manager Live ---")
    # Clean up old sessions on start to prevent Conflict error
    app.run_polling(drop_pending_updates=True)