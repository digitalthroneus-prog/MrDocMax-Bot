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

# --- Configuration & Safety Audit ---
BOT_DIR = Path(__file__).parent
load_dotenv(dotenv_path=BOT_DIR / ".env")

# Robust Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler(BOT_DIR / "bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Mandatory Variable Check
REQUIRED_VARS = ["TELEGRAM_BOT_TOKEN", "EMERGENT_API_KEY"]
missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
if missing:
    logger.error(f"CRITICAL: Missing environment variables: {', '.join(missing)}")

TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
EMERGENT_API_KEY: str = os.getenv("EMERGENT_API_KEY", "")
EMERGENT_BASE_URL: str = os.getenv("EMERGENT_API_BASE_URL", "https://integrations.emergentagent.com/llm")
BTC_WALLET: str = "bc1qd06zsqt6f83jt8ugdh48c800g0nxl0w8390y8r"
WEB_APP_URL: str = "https://credentials-38.preview.emergentagent.com"
WATERMARK_TEXT: str = "MRDOCMAX / SAMPLE / NOT OFFICIAL / FOR REVIEW ONLY"

# --- Client Factory ---
def get_ai_client() -> OpenAI:
    """Initialize OpenAI client with production-grade timeout."""
    return OpenAI(api_key=EMERGENT_API_KEY, base_url=EMERGENT_BASE_URL, timeout=300.0)

# --- States ---
MENU, DOC_PICK, SUB_MENU, DETAILS, PROFILE_BUILDER = range(5)

# --- Library (Locked In) ---
CATEGORIES: Dict[str, List[str]] = {
    "CORPORATE": [
        "Articles of Org", "UK Incorporation Set", "PH SEC Cert", "Cert of Status", 
        "BVI Share Cert", "Board Resolution", "Letterhead", "Register of Shareholders", 
        "Corporate Resolution", "AML/KYC Policy Cover", "Branded Invoice", "Payment Receipt",
        "Stripe Merchant Dashboard"
    ],
    "PERSONAL": [
        "Birth Certificate", "Driver's License", "Social Security Card", "US Passport", 
        "International ID", "Galactic Passport", "License to Chill", "Diplomatic Immunity", 
        "Overthinker ID", "Snack Vault Security", "Bank Statement", "Bank Check", 
        "Money Order", "Wire Transfer", "Utility Bill", "Pay Stub", "Certificate of Title", 
        "Vehicle Registration", "High School GED", "University PhD", "Participation Diploma", "RPG Profile"
    ]
}

STATE_TEMPLATES: Dict[str, List[str]] = {
    "Articles of Org": ["California", "Ohio", "Colorado", "Singapore (ACRA)", "BVI", "UK", "Universal"],
    "Birth Certificate": ["California", "Florida", "Texas", "Mexico City", "Universal"],
    "Driver's License": ["Alabama", "Florida", "Georgia", "Illinois", "Iowa", "Maryland", "New York", "New Jersey", "Pennsylvania", "Texas", "Philippines", "Angola", "Universal"],
    "Bank Check": ["Seacoast Bank", "US Bank", "Chase Cashier", "Bank of America", "PNC Bank", "Treasury Check", "Universal"],
    "Bank Statement": ["Wells Fargo", "Bank of America", "Chase", "Universal"],
    "Wire Transfer": ["Chase", "HSBC", "ING Bank", "Emirates NBD", "Universal"],
    "Cert of Status": ["Florida", "California", "Universal"],
    "Certificate of Title": ["Missouri", "California", "Oklahoma", "Texas", "Universal"]
}

DOC_FIELDS: Dict[str, str] = {
    "Birth Certificate": "NAME OF CHILD:\nSEX:\nDATE OF BIRTH:\nHOUR:\nPLACE OF BIRTH:\nMOTHER'S NAME:\nFATHER'S NAME:",
    "Driver's License": "FULL NAME:\nADDRESS:\nDATE OF BIRTH:\nLICENSE NO:\nCLASS:\nSEX:\nHEIGHT:\nEYES:",
    "Social Security Card": "FULL NAME:\nSOCIAL SECURITY NUMBER:",
    "US Passport": "SURNAME:\nGIVEN NAMES:\nNATIONALITY:\nDATE OF BIRTH:\nPASSPORT NUMBER:",
    "Bank Statement": "ACCOUNT HOLDER NAME:\nACCOUNT NUMBER:\nBANK NAME:\nPERIOD:\nBALANCE:",
    "Pay Stub": "EMPLOYEE NAME:\nEMPLOYEE ID:\nPAY PERIOD:\nGROSS PAY:\nCOMPANY NAME:",
    "Articles of Org": "ENTITY NAME:\nBUSINESS ADDRESS:\nPURPOSE:",
    "Bank Check": "PAY TO THE ORDER OF:\nAMOUNT ($):\nMEMO:\nDATE:",
    "Utility Bill": "CUSTOMER NAME:\nSERVICE ADDRESS:\nACCOUNT NUMBER:",
    "Certificate of Title": "VIN:\nYEAR/MAKE/MODEL:\nPLATE NUMBER:\nOWNER NAME:",
    "Stripe Merchant Dashboard": "COMPANY NAME:\nCURRENCY (e.g. GBP, USD):\nGROSS VOLUME AMOUNT:\nBALANCE AMOUNT:\nPAYOUTS AMOUNT:\nRECENT TRANSACTIONS LIST:"
}

# --- UI Components ---
MAIN_MENU_KEYBOARD = [
    ["💼 CORPORATE", "👤 PERSONAL"],
    ["👤 PROFILE", "💰 TOP UP"],
    [KeyboardButton("⚡ OPEN WEB STORE", web_app=WebAppInfo(url=WEB_APP_URL))]
]

# --- Global Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("🔳 *SYSTEM ALERT*\nJarvis encountered an internal protocol deviation. Resetting sequence. Send /start.")

# --- Protocol Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_markup = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True)
    msg = (
        "🤖 *MRDOCMAX MASTER INTERFACE — ELITE PROTOCOL*\n\n"
        "Welcome, Sir. All generation systems are fully operational. 📋\n\n"
        "Select a suite below to begin."
    )
    if update.message:
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return MENU

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if text == "💰 TOP UP":
        await update.message.reply_text(f"💰 *TOP UP PROTOCOL*\n\nBTC Wallet:\n`{BTC_WALLET}`", parse_mode=ParseMode.MARKDOWN)
        return MENU
    if text == "👤 PROFILE":
        profile = context.user_data.get("active_profile")
        if not profile:
            keyboard = [[InlineKeyboardButton("🆕 Create Profile", callback_data="start_prof")]]
            await update.message.reply_text("👤 *PROFILE PROTOCOL*\n\nNo identity active. Initialize now?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
        else:
            msg = f"👤 *ACTIVE IDENTITY*\n\nName: `{profile['name']}`\nDOB: `{profile['dob']}`\nAddr: `{profile['address']}`"
            keyboard = [[InlineKeyboardButton("🔄 Update Profile", callback_data="start_prof")]]
            await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return MENU
    
    cat = "CORPORATE" if "CORPORATE" in text else "PERSONAL"
    context.user_data["cat"] = cat
    keyboard = []
    for doc in CATEGORIES[cat]:
        keyboard.append([InlineKeyboardButton(f"▫️ {doc}", callback_data=f"sel_{doc}")])
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back")])
    await update.message.reply_text(f"🔳 *{cat} Suite Selection:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return DOC_PICK

async def doc_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "back": return await start(update, context)
    
    doc = query.data.replace("sel_", "")
    context.user_data["doc"] = doc
    if doc in STATE_TEMPLATES:
        keyboard = [[InlineKeyboardButton(s, callback_data=f"state_{s}")] for s in STATE_TEMPLATES[doc]]
        await query.edit_message_text(f"📍 *Jurisdiction for {doc}:*", reply_markup=InlineKeyboardMarkup(keyboard))
        return SUB_MENU
    
    return await prompt_details_entry(query, context, doc)

async def state_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    state = query.data.replace("state_", "")
    context.user_data["state"] = state
    return await prompt_details_entry(query, context, context.user_data.get("doc", "Asset"))

async def prompt_details_entry(query, context, doc) -> int:
    fields = DOC_FIELDS.get(doc, "Full Name:\nDate:\nDetails:")
    msg = f"📝 *Data Entry Protocol: {doc}*\n\nProvide the info exactly as requested:\n\n```\n{fields}\n```\nType details then send `/generate`."
    await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN)
    return DETAILS

async def handle_details_capture(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["details"] = update.message.text
    await update.message.reply_text("✅ Data logged. Protocol ready. Send `/generate` to start AI transmission.")
    return DETAILS

async def generate_protocol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text("⚙️ *JARVIS is generating your high-fidelity package...*\nStand by for digital transmission.", parse_mode=ParseMode.MARKDOWN)
    
    doc = context.user_data.get("doc", "Asset")
    state = context.user_data.get("state", "Universal")
    details = context.user_data.get("details", "N/A")
    profile = context.user_data.get("active_profile", {})
    client = get_ai_client()
    
    try:
        # Prompt Optimization based on analyzed template
        if doc == "Stripe Merchant Dashboard":
            prompt = (
                f"A high-quality 4k digital screenshot of a professional minimalist light-mode Stripe Merchant Dashboard. "
                f"Features a clean white background, a light grey sidebar with menu items like Payments and Balances. "
                f"The main view shows 'Today' with a line chart of 'Gross Volume', a GBP/USD Balance box, and a Payouts box. "
                f"Top right includes a red 'TEST DATA' banner. Context details: {details}. "
                f"Watermark diagonally: '{WATERMARK_TEXT}'."
            )
        else:
            prompt = f"A high-quality professional 4k scan of a novelty prop {state} {doc}. Context: {profile} {details}. Watermark: {WATERMARK_TEXT}."
            
        loop = asyncio.get_event_loop()
        img_res = await loop.run_in_executor(None, lambda: client.images.generate(model="gpt-image-1", prompt=prompt, n=1, size="1024x1024"))
        
        img_url = img_res.data[0].url
        img_data = await loop.run_in_executor(None, lambda: requests.get(img_url).content if img_url else None)
        
        if not img_data:
            raise ValueError("No image data received from AI.")

        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=io.BytesIO(img_data), caption=f"📄 {doc} Preview")
        
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            clean_name = "".join([c for c in doc if c.isalnum() or c==' ']).replace(' ', '_')
            zf.writestr(f"{clean_name}.png", img_data)
            zf.writestr("README.txt", f"MRDOCMAX ELITE ASSET\n\nDocument: {doc}\nJurisdiction: {state}\nTimestamp: {datetime.now()}")
        buf.seek(0)
        await context.bot.send_document(chat_id=update.effective_chat.id, document=InputFile(buf, filename=f"Package_{uuid.uuid4().hex[:6]}.zip"), caption="📦 Branded package delivered.")
        
    except Exception as e:
        logger.error(f"Gen failed: {e}")
        await update.effective_message.reply_text(f"❌ Protocol Error: Generation failed. Error: {str(e)}")
    
    return MENU

# --- Profile Builder ---
async def start_profile_seq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["builder_step"] = "name"
    context.user_data["temp_prof"] = {}
    await query.edit_message_text("👤 *Initialize Profile*\n\nWhat is the **Full Name**?", parse_mode=ParseMode.MARKDOWN)
    return PROFILE_BUILDER

async def handle_profile_input_seq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    step = context.user_data.get("builder_step")
    profile = context.user_data.get("temp_prof", {})
    if step == "name":
        profile["name"] = update.message.text
        await update.message.reply_text(f"✅ Name logged. What is the **Date of Birth**? (mm/dd/yyyy)")
        context.user_data["builder_step"] = "dob"
    elif step == "dob":
        profile["dob"] = update.message.text
        await update.message.reply_text(f"✅ DOB logged. What is the **Residential Address**?")
        context.user_data["builder_step"] = "address"
    elif step == "address":
        profile["address"] = update.message.text
        context.user_data["active_profile"] = profile
        await update.message.reply_text(f"✅ *Profile Active:* {profile['name']}.")
        return await start(update, context)
    return PROFILE_BUILDER

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_error_handler(error_handler)
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [MessageHandler(filters.Regex("^(💼 CORPORATE|👤 PERSONAL|👤 PROFILE|💰 TOP UP)$"), handle_main_menu),
                   CallbackQueryHandler(start_profile_seq, pattern="^start_prof$")],
            DOC_PICK: [CallbackQueryHandler(doc_pick_callback, pattern="^(sel_|back)")],
            SUB_MENU: [CallbackQueryHandler(state_pick_callback, pattern="^state_")],
            DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_details_capture),
                      CommandHandler("generate", generate_protocol)],
            PROFILE_BUILDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_profile_input_seq)]
        },
        fallbacks=[CommandHandler("cancel", start)],
        allow_reentry=True
    )
    app.add_handler(conv_handler)
    
    logger.info("🤖 System Online. Stripe Protocol Integrated.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
