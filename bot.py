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
# 1. TRANSAKCIYA ID НИ ТОЗАЛАШ
# ==========================================
def clean_txn_id(txn_id) -> str:
    """Транзакция ID'сидан ортиқча бўшлиқ ва белгиларни олиб ташлайди."""
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
        logging.error("Supabase уланмаган!")
        return False
    try:
        res = supabase.table("approved_users").select("user_id").eq("user_id", user_id).execute()
        return len(res.data) > 0
    except Exception as e:
        logging.error(f"Supabase'да фойдаланувчини текширишда хатолик: {e}")
        return False

def save_approved_user(user_id: int):
    if not supabase:
        return
    try:
        supabase.table("approved_users").upsert({"user_id": user_id}).execute()
        logging.info(f"Фойдаланувчи {user_id} Supabase'га сақланди.")
    except Exception as e:
        logging.error(f"Фойдаланувчини Supabase'га сақлашда хатолик: {e}")

def is_receipt_used(txn_id) -> bool:
    cleaned = clean_txn_id(txn_id)
    if not cleaned or not supabase:
        return False
    try:
        res = supabase.table("used_receipts").select("txn_id").eq("txn_id", cleaned).execute()
        is_used = len(res.data) > 0
        logging.info(f"Чек текширилди: {cleaned} -> Ишлатилганми: {is_used}")
        return is_used
    except Exception as e:
        logging.error(f"Supabase'да чекни текширишда хатолик: {e}")
        return False

def save_used_receipt(txn_id):
    cleaned = clean_txn_id(txn_id)
    if not cleaned or not supabase:
        return
    try:
        supabase.table("used_receipts").insert({"txn_id": cleaned}).execute()
        logging.info(f"Чек {cleaned} Supabase'га муваффақиятли сақланди.")
    except Exception as e:
        logging.error(f"Чекни Supabase'га сақлашда хатолик: {e}")

# ==========================================
# 3. FASTAPI ВА WEBHOOK
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await bot.set_webhook(WEBHOOK_URL)
        logging.info(f"Webhook муваффақиятли ўрнатилди: {WEBHOOK_URL}")
    except Exception as e:
        logging.error(f"Webhook ўрнатишда хатолик: {e}")
    yield

app = FastAPI(lifespan=lifespan)

def load_data():
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Саволлар файлини ўқишда хатолик: {e}")
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
        logging.error(f"Саволларни файлга ёзишда хатолик: {e}")
    return {"status": "ok"}

async def check_membership(user_id: int, bot: Bot) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
            return True
    except Exception as e:
        logging.error(f"Аъзоликни текширишда хатолик: {e}")
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
            "Мини-аппдан фойдаланиш учун ёпиқ гуруҳимизга қўшилинг ёки қуйидаги картага **50 000 сўм** ўтказиб, расмий чек (квитанция) юборинг:\n\n"
            "💳 **Карта рақами:** **9860120155197128**\n"
            "👤 **Қабул қилувчи:** Бахтиёр Каржабов\n\n"
            "⚠️ **Изоҳ:** Шунчаки ўтказма экрани скриншоти қабул қилинмайди! Банк иловасидан **'O'tkazma tafsilotlari'** ёки **'Квитанция/Чек'** бўлимидаги аниқ Transaction ID'си бор чекни юборинг."
        )

@dp.message(F.photo)
async def handle_payment_screenshot(message: types.Message):
    if message.chat.type != "private":
        return

    user_id = message.from_user.id
    
    if await check_membership(user_id, bot) or is_user_approved(user_id):
        await message.answer("Сиз аллақачон мини-аппдан фойдаланиш ҳуқуқига эгасиз!")
        return

    photo = message.photo[-1]
    file_id = photo.file_id
    
    processing_msg = await message.answer("⏳ Сиз юборган чек текширилмоқда, илтимос кутиб туринг...")
    
    try:
        file_info = await bot.get_file(file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        image = Image.open(downloaded_file)

        # Кучайтирилган Промпт
        prompt = (
            "Analyze this payment receipt image strictly.\n"
            "1. Extract numeric payment amount.\n"
            "2. Extract the exact unique Transaction ID / Check Number / Receipt ID / Reference Number.\n"
            "3. If there is NO clear transaction ID / check number (for example, it's just a simple transfer success screen), set transaction_id to null.\n"
            "Return ONLY a raw JSON object without markdown or backticks:\n"
            '{"amount": number, "transaction_id": "string or null", "is_valid_receipt": boolean, "reason": "string"}'
        )

        response = gemini_client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=[image, prompt]
        )
        
        text_response = response.text.strip()
        if text_response.startswith("```json"):
            text_response = text_response[7:-3].strip()
        elif text_response.startswith("```"):
            text_response = text_response[3:-3].strip()

        data = json.loads(text_response)
        extracted_amount = float(data.get("amount", 0))
        raw_txn_id = data.get("transaction_id")
        txn_id = clean_txn_id(raw_txn_id)
        is_valid = data.get("is_valid_receipt", False)

        # 1. ТРАНЗАКЦИЯ ID ТОПИЛМАСА -> РАД ЭТИШ
        if not txn_id:
            await bot.edit_message_text(
                text="❌ **Тўлов қабул қилинмади!**\n\n"
                     "Юборган расмингизда аниқ **Транзакция ID (чек рақами)** топилмади.\n\n"
                     "📌 Илтимос, оддий экран скриншотини эмас, балки банк иловасидаги **'O'tkazma tafsilotlari'** тугмасини босиб, тўлиқ квитанцияни (чекни) юборинг.",
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                parse_mode="Markdown"
            )
            return

        # 2. ТРАНЗАКЦИЯ ID ИЛГАРИ ИШЛАТИЛГАН БЎЛСА -> РАД ЭТИШ
        if is_receipt_used(txn_id):
            await bot.edit_message_text(
                text=f"❌ **Тўлов рад этилди!**\n\n"
                     f"⚠️ Чек ID: `{txn_id}`\n\n"
                     f"Бу чек илгари тизимда фойдаланилган. Такрорий чек юбориш мумкин эмас!",
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                parse_mode="Markdown"
            )
            return

        # 3. ЧЕК ҲАҚИҚИЙ ВА СУММА ЕТАРЛИ БЎЛСА -> ТАСДИҚЛАШ
        if is_valid and extracted_amount >= REQUIRED_AMOUNT:
            save_used_receipt(txn_id)     # Чек ID'сини Supabase'га сақлаймиз
            save_approved_user(user_id)  # Фойдаланувчини Supabase'га сақлаймиз
            
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🚀 Тестларни бошлаш", web_app=WebAppInfo(url=WEB_APP_URL))]
                ]
            )
            await bot.edit_message_text(
                text=f"✅ **Тўлов муваффақиятли тасдиқланди!**\n\n"
                     f"💰 Аниқланган сумма: `{int(extracted_amount)} сўм`\n"
                     f"🧾 Чек ID: `{txn_id}`\n\n"
                     f"🎉 Сизга мини-аппдан фойдаланиш ҳуқуқи берилди!",
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        else:
            reason = data.get("reason", "Сумма етарли эмас ёки чек ҳақиқий эмас.")
            await bot.edit_message_text(
                text=f"❌ **Тўлов қабул қилинмади!**\n\n"
                     f"🔍 Чекдан топилган сумма: `{int(extracted_amount)} сўм`\n"
                     f"📌 Талаб қилинган сумма: `{REQUIRED_AMOUNT} сўм`\n"
                     f"⚠️ Сабаб: {reason}\n\n"
                     f"Илтимос, тўғри чекни қайтадан юборинг.",
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                parse_mode="Markdown"
            )
    except Exception as e:
        logging.error(f"AI чекни ўқишда хатолик: {e}")
        await bot.edit_message_text(
            text="❌ Чекни ўқишда хатолик юз берди. Илтимос, қайтадан уриниб кўринг.",
            chat_id=message.chat.id,
            message_id=processing_msg.message_id
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
        logging.error(f"Webhook update error: {e}")
    return {"ok": True}

@app.get("/")
async def root():
    html_path = BASE_DIR / "index.html"
    if html_path.exists():
        return FileResponse(html_path)
    return JSONResponse({"status": "Bot ишламоқда"}, status_code=200)
