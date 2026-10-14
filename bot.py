import os
import json
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

logging.basicConfig(level=logging.INFO)

TOKEN = "8979824672:AAEJZ3CHylCvNcoaUHdOt_mmxfcroVWpQk0"
GROUP_ID = -1003919402335  # Бот ушбу гуруҳда алоҳида АДМИН бўлиши шарт!
WEB_APP_URL = "https://test-mini-app-3.vercel.app"

BASE_DIR = Path(__file__).resolve().parent

bot = Bot(token=TOKEN)
dp = Dispatcher()
app = FastAPI()

# --- TESTLAR BAZASI (Serverless учун хавфсиз хотира) ---
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
    # Vercel Serverless муҳитида файлга қайта ёзишда хатолик чиқмаслиги учун:
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Файлга ёзишда хатолик: {e}")
    return {"status": "ok"}

# --- TELEGRAM BOT БЎЛИМИ ---
async def check_membership(user_id: int, bot: Bot) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
            return True
    except Exception as e:
        logging.error(f"Аъзоликни текширишда хатолик: {e}")
        return True
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
            "Testlarni ishlash учун қуйидаги тугмани босинг:",
            reply_markup=keyboard
        )
    else:
        await message.answer(
            "❌ Kechirasiz, siz bizning yopiq guruhimiz a'zosi emassiz.\n\n"
            "Testlarni ishlash учун аввал ёпиқ гуруҳимизга қўшилинг!"
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
