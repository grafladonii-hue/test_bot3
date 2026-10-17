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
import io

logging.basicConfig(level=logging.INFO)

# Янги токен ва манзиллар
TOKEN = "8788215308:AAHc0btjQsQj2MUYSbD1F5iyblTE_iKuDHs"
GROUP_ID = -1003919402335  # Бот ушбу гуруҳда алоҳида АДМИН бўлиши шарт!
WEB_APP_URL = "https://test-mini-app-3.vercel.app"
WEBHOOK_URL = f"{WEB_APP_URL}/api/webhook"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
REQUIRED_AMOUNT = 50000  # Талаб қилинган тўлов суммаси (сўмда)

gemini_client = genai.Client(api_key=GEMINI_API_KEY)
BASE_DIR = Path(__file__).resolve().parent

bot = Bot(token=TOKEN)
dp = Dispatcher()

# FastAPI lifespan (автоматик вебхук ўрнатиш учун)
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await bot.set_webhook(WEBHOOK_URL)
        logging.info(f"Webhook муваффақиятли ўрнатилди: {WEBHOOK_URL}")
    except Exception as e:
        logging.error(f"Webhook ўрнатишда хатолик: {e}")
    yield

app = FastAPI(lifespan=lifespan)

# --- TESTLAR BAZASI ---
DATA_FILE = BASE_DIR / "questions.json"

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

# --- TELEGRAM БОТ ВА ТЕКШИРУВ МАНТИҚИ ---

async def check_membership(user_id: int, bot: Bot) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
            return True
    except Exception as e:
        logging.error(f"Аъзоликни текширишда хатолик: {e}")
    return False

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    is_member = await check_membership(user_id, bot)
    
    if is_member:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📝 Testlarni boshlash", web_app=WebAppInfo(url=WEB_APP_URL))]
            ]
        )
        await message.answer(
            "Xush kelibsiz, Demotestlar.uz (Baxtiyor Karjabov Demo testlar platformasi)ga!\n\n"
            "Сиз ёпиқ гуруҳ аъзосисиз. Testlarni ishlash учун қуйидаги тугмани босинг:",
            reply_markup=keyboard
        )
    else:
        await message.answer(
            "❌ Кечирасиз, сиз бизнинг ёпиқ гуруҳимиз аъзоси эмассиз.\n\n"
            "Мини-аппдан фойдаланиш учун ёпиқ гуруҳимизга қўшилинг ёки қуйидаги картага **50 000 сўм** ўтказиб, чек скриншотини шу ботга юборинг:\n\n"
            "💳 **Карта рақами:** **9860120155197128**\n"
            "👤 **Қабул қилувчи:** Бахтиёр Каржабов\n\n"
            "Чек юборилгач Demotestlar.uz да тест ишлашингиз мумкин бўлади!"
        )

# --- ЧЕКНИ AI (GEMINI) ОРҚАЛИ АВТОМАТИК ТЕКШИРИШ ҚИСМИ ---
@dp.message(F.photo)
async def handle_payment_screenshot(message: types.Message):
    user_id = message.from_user.id
    
    if await check_membership(user_id, bot):
        await message.answer("Сиз аллақачон ёпиқ гуруҳ аъзосисиз ва мини-аппдан бепул фойдалана оласиз!")
        return

    photo = message.photo[-1]
    file_id = photo.file_id
    
    processing_msg = await message.answer("🤖 Сунъий интеллект чекни текширмоқда, илтимос кутиб туринг...")
    
    try:
        file_info = await bot.get_file(file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        image = Image.open(downloaded_file)

        prompt = """
        Sen moliyaviy cheklarni o'qydigan yordamchisan. Ushbu chek rasmini tahlil qil va faqat JSON formatida quyidagi ma'lumotlarni qaytar:
        {
          "amount": (chekdagi raqam ko'rinishidagi summa, masalan: 50000),
          "is_valid_receipt": (agar bu haqiqiy to'lov cheki yoki kvitansiya bo'lsa true, aks holda false)
        }
        Faqatgina toza JSON javob ber, boshqa matn yozma.
        """

        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[image, prompt]
        )
        
        text_response = response.text.strip()
        if text_response.startswith("```json"):
            text_response = text_response[7:-3].strip()
        elif text_response.startswith("```"):
            text_response = text_response[3:-3].strip()

        data = json.loads(text_response)
        extracted_amount = float(data.get("amount", 0))
        is_valid = data.get("is_valid_receipt", False)

        if is_valid and extracted_amount >= REQUIRED_AMOUNT:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🚀 Testlarni boshlash", web_app=WebAppInfo(url=WEB_APP_URL))]
                ]
            )
            await bot.edit_message_text(
                text=f"✅ **To'lov tasdiqlandi!**\n\n💰 Aniqlangan summa: `{int(extracted_amount)} so'm`\n🎉 Сизга мини-аппдан фойдаланиш ҳуқуқи берилди!",
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        else:
            await bot.edit_message_text(
                text=f"❌ **To'lov summasi yetarli emas yoki чек хато!**\n\n"
                     f"🔍 Chekдан топилган сумма: `{int(extracted_amount)} so'm`\n"
                     f"📌 Талаб қилинган сумма: `{REQUIRED_AMOUNT} so'm`\n\n"
                     f"Илтимос, тўғри чекни қайtadan юборинг.",
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                parse_mode="Markdown"
            )
    except Exception as e:
        logging.error(f"AI чекни ўқишда хатолик: {e}")
        await bot.edit_message_text(
            text="❌ Чекни ўқишда хатолик юз берди. Илтимос, қайта уриниб кўринг ёки администраторга мурожаат қилинг.",
            chat_id=message.chat.id,
            message_id=processing_msg.message_id
        )

# Webhook учун универсал эндпоинтлар:
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
