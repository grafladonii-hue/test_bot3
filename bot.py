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
import google.generativeai as genai
from PIL import Image

logging.basicConfig(level=logging.INFO)

TOKEN = "8788215308:AAHc0btjQsQj2MUYSbD1F5iyblTE_iKuDHs"
GROUP_ID = -1003919402335
WEB_APP_URL = "https://test-mini-app-3.vercel.app"
WEBHOOK_URL = f"{WEB_APP_URL}/api/webhook"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
REQUIRED_AMOUNT = 50000

genai.configure(api_key=GEMINI_API_KEY)
# Энг тўғри ва ҳозирги кунда ишлайдиган модель номи
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

BASE_DIR = Path(__file__).resolve().parent

bot = Bot(token=TOKEN)
dp = Dispatcher()

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await bot.set_webhook(WEBHOOK_URL)
        logging.info(f"Webhook муваффақиятли ўрнатилди: {WEBHOOK_URL}")
    except Exception as e:
        logging.error(f"Webhook ўрнатишда хатолик: {e}")
    yield

app = FastAPI(lifespan=lifespan)

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
                [InlineKeyboardButton(text="📝 Тестларни бошлаш", web_app=WebAppInfo(url=WEB_APP_URL))]
            ]
        )
        await message.answer(
            "Хуш келибсиз, Demotestlar.uz (Бахтиёр Каржабов Демо тестлар платформаси)га!\n\n"
            "Сиз ёпиқ гуруҳ аъзосисиз. Тестларни ишлаш учун қуйидаги тугмани босинг:",
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

        prompt = (
            "Analyze this payment receipt image. Extract the numeric payment amount "
            "and determine if it is a valid receipt. "
            "Return ONLY a raw JSON object with keys: amount (number) and is_valid_receipt (boolean). "
            "No markdown, no backticks, no extra text."
        )

        response = gemini_model.generate_content([image, prompt])
        text_response = response.text.strip()
        
        if "```" in text_response:
            text_response = text_response.replace("```json", "").replace("```", "").strip()

        data = json.loads(text_response)
        extracted_amount = float(data.get("amount", 0))
        is_valid = data.get("is_valid_receipt", False)

        if is_valid and extracted_amount >= REQUIRED_AMOUNT:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🚀 Тестларни бошлаш", web_app=WebAppInfo(url=WEB_APP_URL))]
                ]
            )
            await bot.edit_message_text(
                text=f"✅ **Тўлов тасдиқланди!**\n\n💰 Аниқланган сумма: `{int(extracted_amount)} сўм`\n🎉 Сизга мини-аппдан фойдаланиш ҳуқуқи берилди!",
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        else:
            await bot.edit_message_text(
                text=f"❌ **Тўлов суммаси етарли эмас ёки чек хато!**\n\n"
                     f"🔍 Чекдан топилган сумма: `{int(extracted_amount)} сўм`\n"
                     f"📌 Талаб қилинган сумма: `{REQUIRED_AMOUNT} сўм`\n\n"
                     f"Илтимос, тўғри чекни қайtadan юборинг.",
                chat_id=message.chat.id,
                message_id=processing_msg.message_id,
                parse_mode="Markdown"
            )
    except Exception as e:
        logging.error(f"AI чекни ўқишда хатолик: {e}")
        await bot.edit_message_text(
            text=f"❌ Чекни ўқишда хатолик: {str(e)[:100]}",
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
