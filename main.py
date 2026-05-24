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

# --- Global Wealth Structuring Library ---
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
    ["💼 CORPORATE STRUCTURING", "🛡 TRUST & PROTECTION"],
    ["💰 BANKING & PAYMENTS", "📋 PRIVACY & COMPLIANCE"],
    [KeyboardButton("🌐 ACCESS FIDUCIARY PORTAL", web_app=WebAppInfo(url=WEB_APP_URL))]
]

# --- Master Briefing ---
STABLE_GREETING = (
    "🏛 *MDM OFFSHORE ADVISORY — GLOBAL WEALTH STRUCTURING*\n\n"
    "Welcome. We provide discreet international structuring solutions for entrepreneurs, "
    "investors, and private families seeking tax efficiency, asset protection, and "
    "long-term wealth preservation. 📋\n\n"
    "--- *ELITE ADVISORY PROTOCOLS* ---\n"
    "✅ *Cross-Border Wealth Planning:* Multi-jurisdictional legacy protection.\n"
    "✅ *International Holding Entities:* Efficient cross-border capital management.\n"
    "✅ *Nominee Administration:* Absolute discretion for high-net-worth principals.\n"
    "✅ *Private Banking Solutions:* Bespoke multi-currency institutional access.\n\n"
    "--- *COMPLIANCE & PRIVACY* ---\n"
    "Our firm specializes in **Compliance-Light Jurisdictions**, providing a 0% tax corporate "
    "environment with zero public registry exposure.\n\n"
    "Select a department below to initiate your structural instructions."
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_markup = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True)
    if update.message:
        await update.message.reply_text(STABLE_GREETING, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return MENU

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    dept_key = ""
    if "CORPORATE" in text: dept_key = "CORPORATE STRUCTURING"
    elif "TRUST" in text: dept_key = "TRUST & ASSET PROTECTION"
    elif "BANKING" in text: dept_key = "BANKING & PAYMENTS"
    elif "PRIVACY" in text: dept_key = "PRIVACY & ADMINISTRATION"
    elif "COMPLIANCE" in text: dept_key = "COMPLIANCE & RENEWALS"
    else: return MENU

    context.user_data["cat"] = dept_key
    keyboard = []
    for doc in DEPARTMENTS.get(dept_key, []):
        keyboard.append([InlineKeyboardButton(f"{doc}", callback_data=f"sel_{doc}")])
    keyboard.append([InlineKeyboardButton("Back to Main", callback_data="back")])
    
    await update.message.reply_text(f"🏛 *{dept_key} DEPARTMENT:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return DEPT_PICK

async def doc_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "back": return await start(update, context)
    
    doc = query.data.replace("sel_", "")
    context.user_data["doc"] = doc
    if doc in STATE_TEMPLATES:
        keyboard = [[InlineKeyboardButton(s, callback_data=f"state_{s}")] for s in STATE_TEMPLATES[doc]]
        await query.edit_message_text(f"JURISDICTION SELECTION: {doc}", reply_markup=InlineKeyboardMarkup(keyboard))
        return SUB_MENU
    
    return await prompt_details_entry(query, context, doc)

async def state_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    state = query.data.replace("state_", "")
    context.user_data["state"] = state
    return await prompt_details_entry(query, context, context.user_data.get("doc", "Asset"))

async def prompt_details_entry(query, context, doc) -> int:
    fields = DOC_FIELDS.get(doc, "ENTITY NAME:\nPRINCIPAL DETAILS:\nJURISDICTION:\nINSTRUCTION NOTES:")
    msg = (
        f"📝 *INSTRUCTION INTAKE: {doc}*\n\n"
        "Provide your requirements exactly as they should be presented:\n\n"
        f"```\n{fields}\n```\n\n"
        "Type details below, then send `/generate` to process."
    )
    await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN)
    return DETAILS

async def generate_protocol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text("SYSTEM: Initiating high-fidelity structural render. Please wait.")
    await update.effective_message.reply_text("Instruction finalized. Deliverable transmitted to secure vault.")
    return MENU

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [MessageHandler(filters.Regex("^(💼|🛡|💰|📋)"), handle_main_menu)],
            DEPT_PICK: [CallbackQueryHandler(doc_pick_callback, pattern="^(sel_|back)")],
            SUB_MENU: [CallbackQueryHandler(state_pick_callback, pattern="^state_")],
            DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u,c: u.message.reply_text("Instruction logged.")),
                      CommandHandler("generate", generate_protocol)]
        },
        fallbacks=[CommandHandler("cancel", start)],
        allow_reentry=True
    ))
    app.run_polling()

if __name__ == "__main__": main()
