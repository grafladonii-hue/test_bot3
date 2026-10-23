import os
import json
import re
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from google import genai
from PIL import Image
from supabase import create_client, Client
import pypdf  # PDF чекларни ўқиш учун

logging.basicConfig(level=logging.INFO)

TOKEN = "8788215308:AAHc0btjQsQj2MUYSbD1F5iyblTE_iKuDHs"
GROUP_ID = -1003919402335
WEB_APP_URL = "https://test-mini-app-3.vercel.app"
WEBHOOK_URL = f"{WEB_APP_URL}/api/webhook"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
REQUIRED_AMOUNT = 50000  # Талаб қилинадиган сумма: 50 000 сўм

# Supabase созламалари
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    logging.error("❌ SUPABASE_URL ёки SUPABASE_KEY Vercel Environment Variables'да топилмади!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

gemini_client = genai.Client(api_key=GEMINI_API_KEY)
BASE_DIR = Path(__file__).resolve().parent

bot = Bot(token=TOKEN)
dp = Dispatcher()

DATA_FILE = BASE_DIR / "questions.json"

# ==========================================
# 1. ТРАНЗАКЦИЯ ID НИ ТОЗАЛАШ
# ==========================================
def clean_txn_id(txn_id) -> str:
    if not txn_id:
        return ""
    cleaned = re.sub(r'[^a-zA-Z0-9]', '', str(txn_id)).strip().lower()
    if cleaned in ["null", "none", "undefined", "false", "true", ""]:
        return ""
    return cleaned

# ==========================================
# 2. SUPABASE БАЗАСИ БИЛАН ИШЛАШ
# ==========================================
def is_user_approved(user_id: int) -> bool:
    if not supabase:
        return False
    try:
        res = supabase.table("approved_users").select("user_id").eq("user_id", user_id).execute()
        return len(res.data) > 0
    except Exception as e:
        logging.error(f"Supabase хатоси: {e}")
        return False

def save_approved_user(user_id: int):
    if not supabase:
        return
    try:
        supabase.table("approved_users").upsert({"user_id": user_id}).execute()
    except Exception as e:
        logging.error(f"Supabase сақлаш хатоси: {e}")

def is_receipt_used(txn_id) -> bool:
    cleaned = clean_txn_id(txn_id)
    if not cleaned or not supabase:
        return False
    try:
        res = supabase.table("used_receipts").select("txn_id").eq("txn_id", cleaned).execute()
        return len(res.data) > 0
    except Exception as e:
        logging.error(f"Supabase чек текшириш хатоси: {e}")
        return False

def save_used_receipt(txn_id):
    cleaned = clean_txn_id(txn_id)
    if not cleaned or not supabase:
        return
    try:
        supabase.table("used_receipts").insert({"txn_id": cleaned}).execute()
    except Exception as e:
        logging.error(f"Supabase чек сақлаш хатоси: {e}")

# ==========================================
# 3. FASTAPI ВА WEBHOOK
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await bot.set_webhook(WEBHOOK_URL)
        logging.info(f"Webhook ўрнатилди: {WEBHOOK_URL}")
    except Exception as e:
        logging.error(f"Webhook хатоси: {e}")
    yield

app = FastAPI(lifespan=lifespan)

def load_data():
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Саволлар файлини ўқиш хатоси: {e}")
    return {}

@app.get("/api/tests")
def get_tests():
    return load_data()

@app.post("/api/tests")
def update_tests(data: dict):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Саволларни ёзиш хатоси: {e}")
    return {"status": "ok"}

async def check_membership(user_id: int, bot: Bot) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
            return True
    except Exception as e:
        logging.error(f"Аъзоликни текшириш хатоси: {e}")
    return False

# ==========================================
# 4. БОТ ХЭНДЛЕРЛАРИ
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.chat.type != "private":
        return

    user_id = message.from_user.id
    is_member = await check_membership(user_id, bot)
    is_allowed = is_user_approved(user_id)
     
    if is_member or is_allowed:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📝 Тестларни бошлаш", web_app=WebAppInfo(url=WEB_APP_URL))]
            ]
        )
        await message.answer(
            "Хуш келибсиз, Demotestlar.uz (Бахтиёр Каржабов Демо тестлар платформаси)га!\n\n"
            "Сизда мини-аппдан фойдаланиш ҳуқуқи мавжуд. Тестларни ишлаш учун қуйидаги тугмани босинг:",
            reply_markup=keyboard
        )
    else:
        await message.answer(
            "❌ Кечирасиз, сиз бизнинг ёпиқ гуруҳимиз аъзоси эмассиз.\n\n"
            "Мини-аппдан фойдаланиш учун ёпиқ гуруҳимизга қўшилинг ёки қуйидаги картага **50 000 сўм** ўтказиб, тўлов чекини (скриншот ёки файл шаклида) юборинг:\n\n"
            "💳 **Карта рақами:** **9860120155197128**\n"
            "👤 **Қабул қилувчи:** Бахтиёр Каржабов\n\n"
            "⚠️ Банк иловасидан олинган **'O'tkazma tafsilotlari'** чеки (скриншот ёки файл) ни юборишингиз мумкин."
        )

# Расм кўринишидаги чекларни қабул қилиш
@dp.message(F.photo)
async def handle_payment_screenshot(message: types.Message):
    if message.chat.type != "private":
        return

    user_id = message.from_user.id
     
    if await check_membership(user_id, bot) or is_user_approved(user_id):
        await message.answer("Сиз аллақачон мини-аппдан фойдаланиш ҳуқуқига эгасиз!")
        return

    photo = message.photo[-1]
    processing_msg = await message.answer("⏳ Чек расми текширилмоқда...")
     
    try:
        file_info = await bot.get_file(photo.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        image = Image.open(downloaded_file)

        prompt = (
            "Read this receipt. Extract amount (number) and transaction ID / check number (string or null). "
            "Return ONLY raw JSON without markdown: "
            '{"amount": 0, "transaction_id": "id_or_null"}'
        )

        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[image, prompt]
        )
        
        await process_gemini_response(response.text, user_id, message.chat.id, processing_msg.message_id)

    except Exception as e:
        logging.error(f"Расмни ўқиш хатоси: {e}")
        await bot.edit_message_text(
            text="❌ Чек расмини ўқишда хатолик. Қайта уриниб кўринг.",
            chat_id=message.chat.id,
            message_id=processing_msg.message_id
        )

# PDF ёки файл кўринишидаги чекларни қабул қилиш
@dp.message(F.document)
async def handle_payment_document(message: types.Message):
    if message.chat.type != "private":
        return

    user_id = message.from_user.id
     
    if await check_membership(user_id, bot) or is_user_approved(user_id):
        await message.answer("Сиз аллақачон мини-аппдан фойдаланиш ҳуқуқига эгасиз!")
        return

    doc = message.document
    file_name = doc.file_name.lower() if doc.file_name else ""
    
    if not file_name.endswith('.pdf'):
        await message.answer("❌ Илтимос, банк чекини **PDF** форматда ёки **расм** кўринишида юборинг.")
        return

    processing_msg = await message.answer("⏳ PDF чек ҳужжати текширилмоқда...")
     
    try:
        file_info = await bot.get_file(doc.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)

        reader = pypdf.PdfReader(downloaded_file)
        pdf_text = ""
        for page in reader.pages:
            pdf_text += page.extract_text() or ""

        prompt = (
            f"Бу банк ўтказмасининг PDF чеки матни:\n{pdf_text}\n\n"
            "Шу матндан суммани (amount - рақам кўринишида) ва транзакция ID / чек рақамини (transaction_id - стринг ёки null) ажратиб олиб беринг. "
            "Фақат ва фақат JSON форматда жавоб қайтаринг (markdownсиз): "
            '{"amount": 0, "transaction_id": "id_or_null"}'
        )

        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt]
        )
        
        await process_gemini_response(response.text, user_id, message.chat.id, processing_msg.message_id)

    except Exception as e:
        logging.error(f"PDF ҳужжатни ўқиш хатоси: {e}")
        await bot.edit_message_text(
            text="❌ PDF ҳужжатни ўқишда хатолик. Қайта уриниб кўринг.",
            chat_id=message.chat.id,
            message_id=processing_msg.message_id
        )

# Умумий жавобни қайта ишлаш ва тасдиқлаш функцияси
async def process_gemini_response(text_response: str, user_id: int, chat_id: int, message_id: int):
    try:
        text_response = text_response.strip()
        if text_response.startswith("```json"):
            text_response = text_response[7:-3].strip()
        elif text_response.startswith("```"):
            text_response = text_response[3:-3].strip()

        data = json.loads(text_response)
        extracted_amount = float(data.get("amount", 0))
        raw_txn_id = data.get("transaction_id")
        txn_id = clean_txn_id(raw_txn_id)

        if not txn_id:
            await bot.edit_message_text(
                text="❌ **Тўлов қабул қилинмади!**\n\n"
                     "Чекдан аниқ **Транзакция ID** топилмади. Илтимос, тўлов тафсилотлари тўлиқ кўринган чекни юборинг.",
                chat_id=chat_id,
                message_id=message_id,
                parse_mode="Markdown"
            )
            return

        if is_receipt_used(txn_id):
            await bot.edit_message_text(
                text=f"❌ **Тўлов рад этилди!**\n\n⚠️ Бу чек илгари ишлатилган (`{txn_id}`).",
                chat_id=chat_id,
                message_id=message_id,
                parse_mode="Markdown"
            )
            return

        if extracted_amount >= REQUIRED_AMOUNT:
            save_used_receipt(txn_id)
            save_approved_user(user_id)
             
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🚀 Тестларни бошлаш", web_app=WebAppInfo(url=WEB_APP_URL))]
                ]
            )
            await bot.edit_message_text(
                text=f"✅ **Тўлов тасдиқланди!**\n\n💰 Сумма: `{int(extracted_amount)} сўм`\n🧾 Чек ID: `{txn_id}`",
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        else:
            await bot.edit_message_text(
                text=f"❌ **Сумма етарли эмас!**\n\nТопилган сумма: `{int(extracted_amount)} сўм`\nТалаб қилингани: `{REQUIRED_AMOUNT} сўм`",
                chat_id=chat_id,
                message_id=message_id,
                parse_mode="Markdown"
            )
    except Exception as e:
        logging.error(f"JSON таҳлил қилиш хатоси: {e}")
        await bot.edit_message_text(
            text="❌ Чек маълумотларини қайта ишлашда хатолик юз берди.",
            chat_id=chat_id,
            message_id=message_id
        )

@app.post("/api/webhook")
@app.post("/webhook")
@app.post("/")
async def bot_webhook(request: Request):
    try:
        data = await request.json()
        update = types.Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception as e:
        logging.error(f"Webhook error: {e}")
    return {"ok": True}

@app.get("/")
async def root():
    html_path = BASE_DIR / "index.html"
    if html_path.exists():
        return FileResponse(html_path)
    return JSONResponse({"status": "Bot ишламоқда"}, status_code=200)
