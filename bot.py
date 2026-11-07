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
from pydantic import BaseModel
from typing import List, Optional

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
            "INSERT INTO approved_users (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
            (user_id,)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"PostgreSQL сақлаш хатоси: {e}")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- АСОСИЙ ТЕСТЛАРНИ БАЗАДАН МИНИ-АППГА ЮКЛАБ БЕРУВЧИ ENDPOINT ---
@app.get("/api/tests")
def get_tests():
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

class QuestionModel(BaseModel):
    test_id: str
    test_title: Optional[str] = "Demo test"
    reading_text: Optional[str] = ""
    image_url: Optional[str] = ""
    question: str
    options: List[str]
    correct: int

@app.post("/api/save")
async def save_question(q: QuestionModel):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        options_json = json.dumps(q.options, ensure_ascii=False)
        cur.execute("""
            INSERT INTO questions (test_id, reading_text, image_url, question, options, correct, test_title)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (q.test_id, q.reading_text, q.image_url, q.question, options_json, q.correct, q.test_title))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Savol muvaffaqiyatli qo'shildi"}
    except Exception as e:
        logging.error(f"Savolni saqlash хатоси: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.delete("/api/delete/{question_id}")
async def delete_question(question_id: int):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM questions WHERE id = %s", (question_id,))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Savol o'chirildi"}
    except Exception as e:
        logging.error(f"Savolni o'chirish хатоси: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.chat.type != "private":
        return

    user_id = message.from_user.id
    app_url = WEB_APP_URL
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
            "👤 **Қабул қилувчи:** Бахтиёр Каржабов",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

@app.get("/")
async def root():
    return JSONResponse({"status": "Bot va API muvaffaqiyatli ishlamoqda"}, status_code=200)

if __name__ == "__main__":
    import uvicorn
    import asyncio

    async def main():
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("Webhook ўчирилди. Long Polling ва FastAPI бошланяпти...")
        
        config = uvicorn.Config(app=app, host="0.0.0.0", port=8000, log_level="info", loop="asyncio")
        server = uvicorn.Server(config)
        
        await asyncio.gather(
            server.serve(),
            dp.start_polling(bot)
        )

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Сервер тўхтатилди.")
