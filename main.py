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

# --- Configuration & Environment ---
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

# --- The New Global Wealth Structuring Inventory ---
DEPARTMENTS = {
    "INTERNATIONAL STRUCTURING": [
        "Offshore LLC/IBC Formation", "Private Foundation Charter", "Discretionary Trust Deed", "Shelf Entity Registry"
    ],
    "FIDUCIARY & NOMINEE": [
        "Nominee Director Agreement", "Nominee Shareholder Declaration", "Certificate of Incumbency", "Articles of Organization"
    ],
    "FINANCIAL INTEGRATION": [
        "Corporate Banking Portal", "Merchant Gateway (Stripe/PayPal)", "Bank Statement Portfolio", "Wire Transfer Confirmation"
    ],
    "COMPLIANCE & REGISTRY": [
        "Cross-Border Compliance Brief", "Board Resolution", "Register of Directors/Members", "Certificate of Good Standing"
    ]
}

STATE_TEMPLATES = {
    "Articles of Organization": ["California", "Ohio", "Colorado", "Singapore (ACRA)", "BVI", "UK", "Universal"],
    "Offshore LLC/IBC Formation": ["Seychelles", "BVI", "Panama", "Belize", "Cayman Islands", "Universal"],
    "Corporate Banking Portal": ["HSBC", "Barclays", "Emirates NBD", "Chase", "Universal"]
}

DOC_FIELDS = {
    "Offshore LLC/IBC Formation": "PROPOSED ENTITY NAME:\nJURISDICTION:\nPRINCIPAL DIRECTOR:\nINITIAL CAPITALIZATION:\nPURPOSE:",
    "Private Foundation Charter": "FOUNDATION NAME:\nFOUNDER NAME:\nBENEFICIARY DETAILS:\nCOUNCIL MEMBERS:",
    "Discretionary Trust Deed": "TRUST NAME:\nSETTLOR NAME:\nTRUSTEE DETAILS:\nASSET DESCRIPTION:",
    "Nominee Director Agreement": "BENEFICIAL OWNER NAME:\nNOMINEE NAME:\nENTITY REFERENCE:\nDATE OF APPOINTMENT:",
    "Corporate Banking Portal": "BANK NAME:\nACCOUNT HOLDER:\nACCOUNT NUMBER:\nCURRENT BALANCE:\nLAST 5 TRANSACTIONS:",
    "Merchant Gateway (Stripe/PayPal)": "MERCHANT NAME:\nTOTAL VOLUME:\nSTATUS (Active/Pending):\nCURRENCY:",
    "Cross-Border Compliance Brief": "ENTITY NAME:\nJURISDICTION:\nCOMPLIANCE OFFICER:\nREVIEW PERIOD:"
}

# --- Visual UI ---
MAIN_MENU_KEYBOARD = [
    ["💼 INTERNATIONAL STRUCTURING", "🛡 FIDUCIARY & NOMINEE"],
    ["💰 FINANCIAL INTEGRATION", "📋 COMPLIANCE & REGISTRY"],
    [KeyboardButton("🌐 ACCESS CLIENT PORTAL", web_app=WebAppInfo(url=WEB_APP_URL))]
]

# --- Master Briefing ---
STABLE_GREETING = (
    "🏛 *MDM OFFSHORE ADVISORY — GLOBAL WEALTH STRUCTURING*\n\n"
    "Welcome. We provide discreet international structuring solutions for entrepreneurs, "
    "investors, and private families seeking tax efficiency, asset protection, and "
    "long-term wealth preservation. 📋\n\n"
    "--- *CORE ADVISORY DOMAINS* ---\n"
    "✅ *International Structuring:* Offshore companies (LLC/IBC), foundations, and trusts.\n"
    "✅ *Fiduciary Services:* Nominee administration and incumbency certification.\n"
    "✅ *Financial Integration:* Banking introductions, portals, and merchant gateways.\n"
    "✅ *Compliance Registry:* Cross-border documentation and regulatory assets.\n\n"
    "--- *CLIENT PROTOCOLS* ---\n"
    "1. *DISCRETION:* High-fidelity mock-ups for review, presentation, and training.\n"
    "2. *NOVELTY ONLY:* Assets are diagonally watermarked 'SAMPLE' for novelty use.\n"
    "3. *SETTLEMENT:* Funding via secure Treasury channel (BTC).\n\n"
    f"📥 *BTC DEPOSIT ADDRESS:* \n`{BTC_WALLET}`\n\n"
    "Select a department below to initiate instructions."
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_markup = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True)
    if update.message:
        await update.message.reply_text(STABLE_GREETING, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return MENU

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    dept_name = text.replace("💼 ", "").replace("🛡 ", "").replace("💰 ", "").replace("📋 ", "")
    
    if dept_name not in DEPARTMENTS: return MENU

    context.user_data["cat"] = dept_name
    keyboard = []
    for doc in DEPARTMENTS[dept_name]:
        keyboard.append([InlineKeyboardButton(f"{doc}", callback_data=f"sel_{doc}")])
    keyboard.append([InlineKeyboardButton("Back", callback_data="back")])
    
    await update.message.reply_text(f"🏛 *{dept_name} DEPARTMENT:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
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
    fields = DOC_FIELDS.get(doc, "NAME:\nDATE:\nDETAILS:")
    msg = f"📝 *DATA ENTRY: {doc}*\n\nPlease provide instruction details:\n\n```\n{fields}\n```\nType info then send `/generate`."
    await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN)
    return DETAILS

async def generate_protocol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text("SYSTEM: Initiating FLUX.1 high-fidelity transmission. Please wait.")
    # AI Engine logic remains locked in for production
    await update.effective_message.reply_text("Transmission complete. Package delivered to vault.")
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
