import os
import logging
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

logging.basicConfig(level=logging.INFO)

TOKEN = "8979824672:AAEJZ3CHylCvNcoaUHdOt_mmxfcroVWpQk0"
GROUP_ID = -1003919402335  # Бот ушбу гуруҳда алоҳида АДМИН бўлиши шарт!
WEB_APP_URL = "https://test-mini-app-3.vercel.app"

bot = Bot(token=TOKEN)
dp = Dispatcher()
app = FastAPI()

async def check_membership(user_id: int, bot: Bot) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
            return True
    except Exception as e:
        logging.error(f"Аъзоликни текширишда хатолик: {e}")
        # Агар гуруҳ текширувида хатолик бўлса (масалан бот админ бўлмаса), 
        # фойдаланувчини блокда қолдирмаслик учун True қайтариб туриш тавсия этилади:
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
            "Testlarni ishlash uchun quyidagi tugmani bosing:",
            reply_markup=keyboard
        )
    else:
        await message.answer(
            "❌ Kechirasiz, siz bizning yopiq guruhimiz a'zosi emassiz.\n\n"
            "Testlarni ishlash uchun avval yopiq guruhimizga qo'shiling!"
        )

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
    return {"status": "Bot ishlamoqda"}
