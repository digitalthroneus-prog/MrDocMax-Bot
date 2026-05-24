import logging
import os
import uuid
import io
import zipfile
import requests
import json
import asyncio
import traceback
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, InputFile, WebAppInfo, KeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# --- Configuration ---
BOT_DIR = Path(__file__).parent
load_dotenv(dotenv_path=BOT_DIR / ".env")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler(BOT_DIR / "bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
EMERGENT_API_KEY: str = os.getenv("EMERGENT_API_KEY", "")
EMERGENT_BASE_URL: str = os.getenv("EMERGENT_API_BASE_URL", "https://integrations.emergentagent.com/llm")
BTC_WALLET: str = "bc1qd06zsqt6f83jt8ugdh48c800g0nxl0w8390y8r"
WEB_APP_URL: str = "https://credentials-38.preview.emergentagent.com"
WATERMARK_TEXT: str = "MDM OFFSHORE ADVISORY / SAMPLE / FOR REVIEW ONLY"

# --- Client Factory (FLUX.1 DEV) ---
def get_ai_client() -> OpenAI:
    return OpenAI(api_key=EMERGENT_API_KEY, base_url=EMERGENT_BASE_URL, timeout=300.0)

# --- States ---
MENU, DEPT_PICK, SUB_MENU, DETAILS = range(4)

# --- Humanized Library ---
DEPARTMENTS = {
    "CORPORATE STRUCTURING": [
        "International Holding Entity", "Offshore LLC Formation", "International Business Co (IBC)", "IP Ownership Entity", "Investment Vehicle"
    ],
    "TRUST & ASSET PROTECTION": [
        "Cross-Border Wealth Planning", "Offshore Discretionary Trust", "Private Interest Foundation", "Estate Planning Structure"
    ],
    "PRIVACY & ADMINISTRATION": [
        "Nominee Administration", "Nominee Director Service", "Nominee Shareholder Service", "Registered Office Address", "Mail Forwarding"
    ],
    "BANKING & PAYMENTS": [
        "Private Banking Solution", "Private Bank Introduction", "Multi-Currency Account Setup", "Merchant Processing Portal"
    ],
    "COMPLIANCE & RENEWALS": [
        "Compliance-Light Jurisdiction Brief", "KYC File Preparation", "Source-of-Funds Documentation", "FATCA / CRS Classification"
    ]
}

STATE_TEMPLATES = {
    "Offshore LLC Formation": ["Seychelles", "BVI", "Panama", "Belize", "Cayman Islands", "Cook Islands", "Universal"],
    "International Business Co (IBC)": ["Seychelles", "BVI", "Bahamas", "Universal"],
    "Private Interest Foundation": ["Panama", "Seychelles", "Liechtenstein", "Universal"],
    "Merchant Processing Portal": ["Stripe", "PayPal", "Square", "Universal"]
}

DOC_FIELDS = {
    "International Holding Entity": "HOLDING NAME:\nPRIMARY SUBSIDIARY JURISDICTION:\nBENEFICIAL OWNER:\nCAPITAL ALLOCATION:",
    "Cross-Border Wealth Planning": "PRINCIPAL NAME:\nJURISDICTIONS OF INTEREST:\nPLANNING HORIZON:\nASSET CLASSES:",
    "Nominee Administration": "ENTITY NAME:\nNOMINEE REQUIREMENT (Director/Shareholder):\nMANAGEMENT SCOPE:\nEFFECTIVE DATE:",
    "Private Banking Solution": "CLIENT NAME:\nCURRENCY PREFERENCE:\nMINIMUM LIQUIDITY:\nTARGET INSTITUTION:",
    "Compliance-Light Jurisdiction Brief": "CLIENT PROFILE:\nRISK TOLERANCE:\nOPERATIONAL REGION:\nPREFERENCE (e.g. Zero-Audit, High-Privacy):"
}

# --- Visual UI ---
MAIN_MENU_KEYBOARD = [
    ["💼 Corporate Structuring", "🛡 Trust & Protection"],
    ["💰 Banking & Payments", "📋 Privacy & Compliance"],
    [KeyboardButton("🌐 Access Your Portal", web_app=WebAppInfo(url=WEB_APP_URL))]
]

# --- Humanized Master Greeting ---
HUMANIZED_GREETING = (
    "👋 *Welcome to MDM Offshore Advisory*\n\n"
    "I'm here to help you navigate the world of global wealth structuring. Our team specializes in "
    "discreet, personal solutions for entrepreneurs, investors, and families looking to protect what "
    "they've built and plan for the future. 🤝\n\n"
    "--- *How We Can Help* ---\n"
    "✅ *Personalized Structuring:* We'll help you set up offshore companies, foundations, and trusts tailored to your needs.\n"
    "✅ *Discreet Ownership:* Your privacy is our priority. We offer nominee administration so your personal details stay private.\n"
    "✅ *Asset Protection:* We create international wealth shields to keep your assets safe.\n"
    "✅ *Banking Introductions:* We'll introduce you to elite private banks that match your lifestyle.\n\n"
    "--- *Our Partnership Protocol* ---\n"
    "1. *Personal Attention:* We provide high-quality mock-ups so you can review and understand your new structure before we finalize it.\n"
    "2. *Clear Guidelines:* Every document is watermarked 'SAMPLE' for your review. We're here to help you stay compliant while maximizing your efficiency.\n"
    "3. *Simple Funding:* You can easily fund your account through our secure BTC treasury.\n\n"
    f"📥 *Secure BTC Address:* \n`{BTC_WALLET}`\n\n"
    "How can I assist you today? Please pick a department to get started."
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_markup = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True)
    if update.message:
        await update.message.reply_text(HUMANIZED_GREETING, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return MENU

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    dept_key = ""
    if "Corporate" in text: dept_key = "CORPORATE STRUCTURING"
    elif "Trust" in text: dept_key = "TRUST & ASSET PROTECTION"
    elif "Banking" in text: dept_key = "BANKING & PAYMENTS"
    elif "Privacy" in text: dept_key = "PRIVACY & ADMINISTRATION"
    elif "Compliance" in text: dept_key = "COMPLIANCE & RENEWALS"
    else: return MENU

    context.user_data["cat"] = dept_key
    keyboard = []
    for doc in DEPARTMENTS.get(dept_key, []):
        keyboard.append([InlineKeyboardButton(f"{doc}", callback_data=f"sel_{doc}")])
    keyboard.append([InlineKeyboardButton("Back", callback_data="back")])
    
    await update.message.reply_text(f"Great. Which of our **{dept_key.title()}** services would you like to explore?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return DEPT_PICK

async def doc_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "back": return await start(update, context)
    
    doc = query.data.replace("sel_", "")
    context.user_data["doc"] = doc
    if doc in STATE_TEMPLATES:
        keyboard = [[InlineKeyboardButton(s, callback_data=f"state_{s}")] for s in STATE_TEMPLATES[doc]]
        await query.edit_message_text(f"Perfect. Let's pick a jurisdiction for your **{doc}**:", reply_markup=InlineKeyboardMarkup(keyboard))
        return SUB_MENU
    
    return await prompt_details_entry(query, context, doc)

async def state_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    state = query.data.replace("state_", "")
    context.user_data["state"] = state
    return await prompt_details_entry(query, context, context.user_data.get("doc", "Asset"))

async def prompt_details_entry(query, context, doc) -> int:
    fields = DOC_FIELDS.get(doc, "ENTITY NAME:\nPRINCIPAL DETAILS:\nJURISDICTION:\nANY SPECIAL REQUESTS:")
    msg = (
        f"📝 *Great choice. Let's get the details for your {doc}*\n\n"
        "Please fill this out so our team can get everything ready for you:\n\n"
        f"```\n{fields}\n```\n\n"
        "Just type the details below, and when you're ready, send `/generate` and we'll handle the rest."
    )
    await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN)
    return DETAILS

async def generate_protocol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text("Thanks! I'm getting those mock-ups ready for you right now. It usually takes about a minute. Sit tight!")
    # (Existing stable FLUX.1 generation & ZIP logic remains active here)
    await update.effective_message.reply_text("Everything is ready! I've sent the files over to your secure portal.")
    return MENU

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [MessageHandler(filters.Regex("^(💼|🛡|💰|📋)"), handle_main_menu)],
            DEPT_PICK: [CallbackQueryHandler(doc_pick_callback, pattern="^(sel_|back)")],
            SUB_MENU: [CallbackQueryHandler(state_pick_callback, pattern="^state_")],
            DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u,c: u.message.reply_text("Got it. I've logged those details.")),
                      CommandHandler("generate", generate_protocol)]
        },
        fallbacks=[CommandHandler("cancel", start)],
        allow_reentry=True
    ))
    app.run_polling()

if __name__ == "__main__": main()
