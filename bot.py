import os
import json
import re
import logging
import asyncio
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from google import genai
from PIL import Image
import psycopg2
from psycopg2.extras import Json
from pydantic import BaseModel
from typing import List, Optional

logging.basicConfig(level=logging.INFO)

TOKEN = "8788215308:AAFge-oUPtzNEvCR38C2kyxsOrR_GQZ6u6c"
if not TOKEN:
    raise RuntimeError("BOT_TOKEN топилмади!")

GROUP_ID = -1003919402335
WEB_APP_URL = "https://test-mini-app-3.vercel.app"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
REQUIRED_AMOUNT = 50000

gemini_client = (
    genai.Client(api_key=GEMINI_API_KEY)
    if GEMINI_API_KEY else None
)

# PostgreSQL VPS
DB_HOST = "localhost"
DB_NAME = "appdb"
DB_USER = "appuser"
DB_PASSWORD = "StrongPass2026"
DB_PORT = 5432

if not DB_PASSWORD:
    raise RuntimeError("POSTGRES_PASSWORD топилмади!")


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT,
        connect_timeout=10
    )


BASE_DIR = Path(__file__).resolve().parent

bot = Bot(token=TOKEN)
dp = Dispatcher()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def clean_txn_id(txn_id) -> str:
    if not txn_id:
        return ""

    cleaned = re.sub(
        r'[^a-zA-Z0-9]', '', str(txn_id)
    ).strip().lower()

    if cleaned in [
        "null", "none", "undefined",
        "false", "true", ""
    ]:
        return ""

    return cleaned


def is_user_approved(user_id: int) -> bool:
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user_id FROM approved_users WHERE user_id = %s",
                    (user_id,)
                )
                return cur.fetchone() is not None

    except Exception as e:
        logging.error(f"PostgreSQL хатоси: {e}")
        return False


def save_approved_user(user_id: int):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO approved_users (user_id)
                    VALUES (%s)
                    ON CONFLICT DO NOTHING
                    """,
                    (user_id,)
                )

    except Exception as e:
        logging.error(f"VIP сақлаш хатоси: {e}")


@app.get("/api/tests")
def get_tests():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, test_id, reading_text,
                           image_url, question, options,
                           correct, test_title
                    FROM questions
                    ORDER BY id
                """)
                rows = cur.fetchall()

        tests_dict = {}

        for row in rows:
            (
                q_id, test_id, reading_text,
                image_url, question_text,
                options, correct_opt, test_title
            ) = row

            t_key = str(test_id)

            if t_key not in tests_dict:
                tests_dict[t_key] = {
                    "title": test_title or f"Demo test ({t_key})",
                    "questions": []
                }

            if isinstance(options, str):
                try:
                    options = json.loads(options)
                except Exception:
                    options = []

            tests_dict[t_key]["questions"].append({
                "id": q_id,
                "reading_text": reading_text,
                "readingText": reading_text,
                "image_url": image_url,
                "imageUrl": image_url,
                "question": question_text,
                "question_text": question_text,
                "options": options,
                "correct": correct_opt,
                "correct_option": correct_opt
            })

        return tests_dict

    except Exception as e:
        logging.error(f"Тестларни ўқиш хатоси: {e}")
        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )


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
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO questions (
                        test_id, reading_text, image_url,
                        question, options, correct, test_title
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    q.test_id,
                    q.reading_text,
                    q.image_url,
                    q.question,
                    Json(q.options),
                    q.correct,
                    q.test_title
                ))

        return {
            "status": "success",
            "message": "Savol muvaffaqiyatli qo'shildi"
        }

    except Exception as e:
        logging.error(f"Саволни сақлаш хатоси: {e}")
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500
        )


@app.delete("/api/delete/{question_id}")
async def delete_question(question_id: int):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM questions WHERE id = %s",
                    (question_id,)
                )

        return {
            "status": "success",
            "message": "Savol o'chirildi"
        }

    except Exception as e:
        logging.error(f"Саволни ўчириш хатоси: {e}")
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500
        )


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.chat.type != "private":
        return

    user_id = message.from_user.id
    is_vip = (
        is_user_approved(user_id)
        or str(user_id) == "644092713"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Иловани очиш (Mini App)",
                    web_app=WebAppInfo(url=WEB_APP_URL)
                )
            ]
        ]
    )

    if is_vip:
        await message.answer(
            "Ассалому алайкум! Сизда **VIP обуна фаол** ✅\n\n"
            "Барча тестлар ва имкониятлардан "
            "чекловларсиз фойдаланишингиз мумкин.",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "Ассалому алайкум! Demotestlar.uz платформасига "
            "хуш келибсиз.\n\n"
            "Дастлабки **3 та тест бепул** тақдим этилади.\n\n"
            "🔒 Барча тестларни очиш учун ёпиқ гуруҳимиз "
            "аъзоси бўлинг ёки 50 000 сўм тўлов қилинг.\n\n"
            "💳 **Карта рақами:** `9860120155197128`\n"
            "👤 **Қабул қилувчи:** Бахтиёр Каржабов",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )


@dp.message(F.photo)
async def handle_payment_screenshot(message: types.Message):
    if message.chat.type != "private":
        return

    user_id = message.from_user.id

    if is_user_approved(user_id):
        await message.answer(
            "Сизда аллақачон фаол VIP обуна мавжуд!"
        )
        return

    photo = message.photo[-1]
    processing_msg = await message.answer(
        "⏳ Чек расми текширилмоқда..."
    )

    try:
        if not gemini_client:
            await processing_msg.edit_text(
                "Gemini API калити созланмаган."
            )
            return

        file_info = await bot.get_file(photo.file_id)
        downloaded_file = await bot.download_file(
            file_info.file_path
        )

        image = Image.open(downloaded_file)

        prompt = (
            "Read this receipt. Extract amount (number) "
            "and transaction ID / check number (string or null). "
            "Return ONLY raw JSON without markdown: "
            '{"amount": 0, "transaction_id": "id_or_null"}'
        )

        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[image, prompt]
        )

        logging.info("Gemini жавоби: %s", response.text)

        await processing_msg.edit_text(
            "Чек таҳлил қилинди. Автоматик тўлов тасдиғи "
            "ҳозирча кодга уланмаган."
        )

    except Exception as e:
        logging.error(f"Gemini хатоси: {e}")
        await processing_msg.edit_text(
            "Чекни текширишда хатолик юз берди."
        )


@app.get("/")
async def root():
    return JSONResponse({
        "status": "Bot va API muvaffaqiyatli ishlamoqda"
    })


if __name__ == "__main__":
    import uvicorn

    async def main():
        await bot.delete_webhook(drop_pending_updates=True)

        logging.info(
            "Webhook ўчирилди. Bot ва API ишга тушмоқда..."
        )

        config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=8000,
            log_level="info"
        )

        server = uvicorn.Server(config)

        await asyncio.gather(
            server.serve(),
            dp.start_polling(bot)
        )

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Сервер тўхтатилди.")
