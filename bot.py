import os
import json
import re
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from google import genai
from PIL import Image
import psycopg2
import pypdf

logging.basicConfig(level=logging.INFO)

TOKEN = "8788215308:AAHc0btjQsQj2MUYSbD1F5iyblTE_iKuDHs"
GROUP_ID = -1003919402335
WEB_APP_URL = "https://test-mini-app-3.vercel.app"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
REQUIRED_AMOUNT = 50000

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

DB_HOST = "83.69.139.120"
DB_NAME = "demotestlardb"
DB_USER = "postgres"
DB_PASSWORD = "12345"
DB_PORT = 5432

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )

BASE_DIR = Path(__file__).resolve().parent

bot = Bot(token=TOKEN)
dp = Dispatcher()

def clean_txn_id(txn_id) -> str:
    if not txn_id:
        return ""
    cleaned = re.sub(r'[^a-zA-Z0-9]', '', str(txn_id)).strip().lower()
    if cleaned in ["null", "none", "undefined", "false", "true", ""]:
        return ""
    return cleaned

def is_user_approved(user_id: int) -> bool:
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM approved_users WHERE user_id = %s", (user_id,))
        res = cur.fetchone()
        cur.close()
        conn.close()
        return res is not None
    except Exception as e:
        logging.error(f"PostgreSQL хатоси: {e}")
        return False

def save_approved_user(user_id: int):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO approved_users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING",
            (user_id,)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"PostgreSQL сақлаш хатоси: {e}")

def is_receipt_used(txn_id) -> bool:
    cleaned = clean_txn_id(txn_id)
    if not cleaned:
        return False
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT txn_id FROM used_receipts WHERE txn_id = %s", (cleaned,))
        res = cur.fetchone()
        cur.close()
        conn.close()
        return res is not None
    except Exception as e:
        logging.error(f"PostgreSQL чек текшириш хатоси: {e}")
        return False

def save_used_receipt(txn_id):
    cleaned = clean_txn_id(txn_id)
    if not cleaned:
        return
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO used_receipts (txn_id) VALUES (%s) ON CONFLICT (txn_id) DO NOTHING",
            (cleaned,)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"PostgreSQL чек сақлаш хатоси: {e}")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def load_data():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, test_id, reading_text, image_url, question, options, correct, test_title 
            FROM questions
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        tests_dict = {}
        for row in rows:
            q_id, test_id, reading_text, image_url, question_text, options, correct_opt, test_title = row
            
            t_key = str(test_id)
            if t_key not in tests_dict:
                title = test_title if test_title else f"Demo test ({t_key})"
                tests_dict[t_key] = {
                    "title": title,
                    "questions": []
                }
            
            if isinstance(options, str):
                try:
                    options = json.loads(options)
                except:
                    options = []

            tests_dict[t_key]["questions"].append({
                "id": q_id,
                "reading_text": reading_text,
                "image_url": image_url,
                "question": question_text,
                "options": options,
                "correct": correct_opt
            })
            
        return tests_dict
    except Exception as e:
        logging.error(f"Базадан тестларни ўқиш хатоси: {e}")
        return {}

@app.get("/api/tests")
def get_tests():
    return load_data()

async def check_membership(user_id: int, bot: Bot) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
            return True
    except Exception as e:
        logging.error(f"Аъзоликни текшириш хатоси: {e}")
    return False

async def check_and_auto_approve_group_member(user_id: int, bot: Bot) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
            save_approved_user(user_id)
            return True
    except Exception as e:
        logging.error(f"Гуруҳ аъзолигини текшириш ва авто-қўшиш хатоси: {e}")
    return False

@dp.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject = None):
    if message.chat.type != "private":
        return

    user_id = message.from_user.id
    app_url = WEB_APP_URL

    await check_and_auto_approve_group_member(user_id, bot)
    
    is_vip = is_user_approved(user_id) or str(user_id) == "644092713"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Иловани очиш (Mini App)", web_app=WebAppInfo(url=app_url))]
        ]
    )
    
    if is_vip:
        await message.answer(
            "Ассалому алайкум! Сизда **VIP обуна фаол** ✅\n\n"
            "Барча тестлар ва имкониятлардан чеклаувларсиз фойдаланишингиз мумкин. Иловани очиш учун қуйидаги тугмани босинг:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "Ассалому алайкум! Demotestlar.uz платформасига хуш келибсиз.\n\n"
            "Дастлабки **3 та тест бепул** тақдим этилади.\n\n"
            "🔒 Барча тестларни тўлиқ очиш учун ёпиқ гуруҳимиз аъзоси бўлинг ёки қуйидаги картага **50 000 сўм** ўтказиб, тўлов чекини шу ерга юборинг:\n\n"
            "💳 **Карта рақами:** `9860120155197128`\n"
            "👤 **Қабул қилувчи:** Бахтиёр Каржабов\n\n"
            "⚠️ Тўлов қилганингиздан сўнг чекни юборсангиз, бот автоматик равишда текшириб тестларни очиб беради.",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

@dp.message(F.photo)
async def handle_payment_screenshot(message: types.Message):
    if message.chat.type != "private":
        return

    user_id = message.from_user.id
     
    if await check_membership(user_id, bot) or is_user_approved(user_id):
        await message.answer("Сизда аллақачон фаол VIP обуна мавжуд!")
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
            model='gemini-3.5-flash-lite',
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

@dp.message(F.document)
async def handle_payment_document(message: types.Message):
    if message.chat.type != "private":
        return

    user_id = message.from_user.id
     
    if await check_membership(user_id, bot) or is_user_approved(user_id):
        await message.answer("Сизда аллақачон фаол VIP обуна мавжуд!")
        return

    doc = message.document
    file_name = doc.file_name.lower() if doc.file_name else ""
    
    if not file_name.endswith('.pdf'):
        await message.answer("❌ Илтимос, банк чекини **PDF** форматда ёки **расм** кўринишида юборинг.", parse_mode="Markdown")
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
            model='gemini-3.5-flash-lite',
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
             
            vip_keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⭐ VIP obuna", web_app=WebAppInfo(url=WEB_APP_URL))]
                ]
            )

            await bot.edit_message_text(
                text=f"✅ **Тўлов тасдиқланди!**\n\n💰 Сумма: `{int(extracted_amount)} сўм`\n🧾 Чек ID: `{txn_id}`\n\nБарча тестлар очилди!",
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=vip_keyboard,
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

@app.get("/")
async def root():
    html_path = BASE_DIR / "index.html"
    if html_path.exists():
        return FileResponse(html_path)
    return JSONResponse({"status": "Bot ишламоқда"}, status_code=200)

if __name__ == "__main__":
    import uvicorn
    import asyncio

    async def main():
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("Webhook ўчирилди. Long Polling бошланяпти...")
        
        polling_task = asyncio.create_task(dp.start_polling(bot))
        
        config = uvicorn.Config(app=app, host="0.0.0.0", port=8000, log_level="info")
        server = uvicorn.Server(config)
        
        await server.serve()
        polling_task.cancel()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Сервер фойдаланувчи томонидан тўхтатилди.")
