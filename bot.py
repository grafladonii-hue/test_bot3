import os
import json
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

logging.basicConfig(level=logging.INFO)

TOKEN = "8788215308:AAHc0btjQsQj2MUYSbD1F5iyblTE_iKuDHs"
GROUP_ID = -1003919402335
WEB_APP_URL = "https://test-mini-app-3.vercel.app"
WEBHOOK_URL = f"{WEB_APP_URL}/api/webhook"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
REQUIRED_AMOUNT = 50000  # Талаб қилинадиган сумма 50 000 сўм

# Замонавий Google GenAI клиенти
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

BASE_DIR = Path(__file__).resolve().parent

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Файллар йўли
APPROVED_USERS_FILE = BASE_DIR / "approved_users.json"
USED_RECEIPTS_FILE = BASE_DIR / "used_receipts.json"
DATA_FILE = BASE_DIR / "questions.json"

# ==========================================
# 1. ТАСДИҚЛАНГАН ФОЙДАЛАНУВЧИЛАР БИЛАН ИШЛАШ
# ==========================================
def load_approved_users() -> list:
    if APPROVED_USERS_FILE.exists():
        try:
            with open(APPROVED_USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Тасдиқланган фойдаланувчиларни ўқишда хатолик: {e}")
    return []

def save_approved_user(user_id: int):
    users = load_approved_users()
    if user_id not in users:
        users.append(user_id)
        try:
            with open(APPROVED_USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(users, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"Фойдаланувчини сақлашда хатолик: {e}")

def is_user_approved(user_id: int) -> bool:
    return user_id in load_approved_users()

# ==========================================
# 2. ИШЛАТИЛГАН ЧЕКЛАРНИ (TRANSACTION ID) ТЕКШИРИШ
# ==========================================
def load_used_receipts() -> list:
    if USED_RECEIPTS_FILE.exists():
        try:
            with open(USED_RECEIPTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Ишлатилган чекларни ўқишда хатолик: {e}")
    return []

def is_receipt_used(txn_id: str) -> bool:
    if not txn_id:
        return False
    return str(txn_id).strip() in load_used_receipts()

def save_used_receipt(txn_id: str):
    if not txn_id:
        return
    receipts = load_used_receipts()
    clean_id = str(txn_id).strip()
    if clean_id not in receipts:
        receipts.append(clean_id)
        try:
            with open(USED_RECEIPTS_FILE, "w", encoding="utf-8") as f:
                json.dump(receipts, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"Транзакция ID ни сақлашда хатолик: {e}")

# ==========================================
# 3. FASTAPI ВА WEBHOOK СОЗЛАМАЛАРИ
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
            logging.error(f"Файлни ўқишда хатолик: {e}")
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
        logging.error(f"Файлга ёзишда хатолик: {e}")
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

        # Gemini AI учун янгиланган промпт (Transaction ID ни ажратиб олиш билан)
        prompt = (
            "Analyze this payment receipt image. Extract: "
            "1. Numeric payment amount. "
            "2. Unique Transaction ID / Receipt Number / Check ID (string, numeric/alphanumeric). "
            "3. Determine if it is a formal/valid bank receipt (must have an explicit transaction ID/number, not just a simple transfer screen/screenshot). "
            "Return ONLY a raw JSON object with keys: "
            "amount (number), transaction_id (string or null), is_valid_receipt (boolean), reason (string). "
            "No markdown, no backticks, no extra text."
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
        txn_id = data.get("transaction_id")
        is_valid = data.get("is_valid_receipt", False)

        # 1. ТРАНЗАКЦИЯ ID ТОПИЛМАСА (Скриншот бўлса)
        if not txn_id or str(txn_id).lower() in ["null", "none", ""]:
            await bot.edit_message_text(
                text="❌ **Тўлов қабул қилинмади!**\n\n"
                     "Юборган расмингизда аниқ **Транзакция ID (чек рақами)** топилмади.\n\n"
                     "📌 Илтимос, оддий экран скриншотини эмас, балки банк иловасидаги **'O'tkazma tafsilotlari'** тугмасини босиб, тўлиқ квитанцияни (чекни) юборинг.",
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                parse_mode="Markdown"
            )
            return

        # 2. ТРАНЗАКЦИЯ ID ИЛГАРИ ИШЛАТИЛГАН БЎЛСА (Такрорий чек)
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

        # 3. ЧЕК ҲАҚИҚИЙ ВА СУММА ЕТАРЛИ БЎЛСА
        if is_valid and extracted_amount >= REQUIRED_AMOUNT:
            save_used_receipt(txn_id)     # Чек ID'сини базага сақлаймиз
            save_approved_user(user_id)  # Фойдаланувчига рухсат берамиз
            
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
