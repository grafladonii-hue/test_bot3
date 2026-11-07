import os
import json
import logging
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler
import psycopg2
from typing import List, Optional

logging.basicConfig(level=logging.INFO)
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# VPS PostgreSQL базаси созламалари
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

# --- МОДЕЛЛАР ---
class TournamentCreate(BaseModel):
    title: str
    test_key: str
    start_time: datetime
    duration_minutes: int = 2

class AnswerSubmit(BaseModel):
    tournament_id: int
    user_id: int
    question_index: int
    selected_option: int

# 1. Турнирлар рўйхатини мини-аппга етказиб берувчи endpoint
@app.get("/api/tournaments")
def get_tournaments():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, title, test_key, start_time, duration_minutes, status FROM tournaments")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        tournaments = []
        for row in rows:
            tournaments.append({
                "id": row[0],
                "title": row[1],
                "test_key": row[2],
                "start_time": str(row[3]),
                "duration_minutes": row[4],
                "status": row[5]
            })
        return {"status": "success", "tournaments": tournaments}
    except Exception as e:
        logging.error(f"Tournaments get error: {e}")
        return {"status": "error", "message": str(e), "tournaments": []}

# 2. Админ турнир яратиши ва тестни вақти келгунча яшириши
@app.post("/api/admin/create-tournament")
def create_tournament(data: TournamentCreate):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Testni vaqti kelguncha yashirish (is_public ni False qilish)
        cur.execute("UPDATE tests SET is_public = FALSE WHERE test_key = %s", (data.test_key,))
        
        # Turnirni qo'shish
        cur.execute("""
            INSERT INTO tournaments (title, test_key, start_time, duration_minutes, status)
            VALUES (%s, %s, %s, %s, 'waiting')
        """, (data.title, data.test_key, data.start_time.isoformat(), data.duration_minutes))
        
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": "Жамоавий тест режалаштирилди ва вақти келгунча яширилди!"}
    except Exception as e:
        logging.error(f"Create tournament error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Ёрдамчи функция: VPS базасидан тўғри жавобни топиш
def get_correct_option_index(test_key: str, question_index: int) -> int:
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # test_key bo'yicha savolarni olish
        cur.execute("SELECT correct, options FROM questions WHERE test_id = %s", (test_key,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        if rows and question_index < len(rows):
            # rows[question_index][0] - correct index
            return int(rows[question_index][0])
    except Exception as e:
        print(f"Хатолик тўғри жавобни топишда: {e}")
    return 0

# 3. Иштирокчининг жавобини қабул қилиш ва текшириш
@app.post("/api/tournament/submit-answer")
def submit_answer(data: AnswerSubmit):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT id, test_key, status FROM tournaments WHERE id = %s", (data.tournament_id,))
        tour = cur.fetchone()
        
        if not tour or tour[2] != "active":
            cur.close()
            conn.close()
            raise HTTPException(status_code=400, detail="Турнир фаол эмас ёки тугаган!")
        
        test_key = tour[1]
        
        # Oldin javob berganligini tekshirish
        cur.execute("""
            SELECT id FROM tournament_user_answers 
            WHERE tournament_id = %s AND user_id = %s AND question_index = %s
        """, (data.tournament_id, data.user_id, data.question_index))
        existing = cur.fetchone()
        
        if existing:
            cur.close()
            conn.close()
            raise HTTPException(status_code=400, detail="Бу саволга аллақачон жавоб бергансиз!")

        correct_option_index = get_correct_option_index(test_key, data.question_index)
        is_correct = (data.selected_option == correct_option_index)

        cur.execute("""
            INSERT INTO tournament_user_answers (tournament_id, user_id, question_index, selected_option, is_correct)
            VALUES (%s, %s, %s, %s, %s)
        """, (data.tournament_id, data.user_id, data.question_index, data.selected_option, is_correct))
        
        conn.commit()
        cur.close()
        conn.close()

        return {
            "status": "success",
            "is_correct": is_correct,
            "correct_option": correct_option_index
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logging.error(f"Submit answer error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 4. Турнир рейтинг (Leaderboard) натижаlarini олиш endpoint'и
@app.get("/api/tournament/{tournament_id}/leaderboard")
def get_tournament_leaderboard(tournament_id: int):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id, is_correct FROM tournament_user_answers WHERE tournament_id = %s", (tournament_id,))
        answers = cur.fetchall()
        cur.close()
        conn.close()
        
        if not answers:
            return {"status": "success", "leaderboard": []}
        
        user_scores = {}
        for row in answers:
            uid = row[0]
            is_cor = row[1]
            if uid not in user_scores:
                user_scores[uid] = {"user_id": uid, "score": 0, "correct_count": 0}
            
            if is_cor:
                user_scores[uid]["score"] += 1
                user_scores[uid]["correct_count"] += 1
                
        sorted_leaderboard = sorted(user_scores.values(), key=lambda x: x["score"], reverse=True)
        
        for index, item in enumerate(sorted_leaderboard):
            item["rank"] = index + 1
            
        return {"status": "success", "leaderboard": sorted_leaderboard}
        
    except Exception as e:
        return {"status": "error", "message": str(e), "leaderboard": []}

# 5. Фон жараёни: Турнирларнинг бошланиш ва тугаш вақтини автоматик бошқариш
def manage_tournaments_lifecycle():
    try:
        now = datetime.now().astimezone()
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Waiting -> Active
        cur.execute("SELECT id, start_time, test_key FROM tournaments WHERE status = 'waiting'")
        waiting_tournaments = cur.fetchall()
        for tour in waiting_tournaments:
            t_id, start_str, test_key = tour[0], tour[1], tour[2]
            start_t = datetime.fromisoformat(str(start_str))
            if now >= start_t:
                cur.execute("UPDATE tournaments SET status = 'active' WHERE id = %s", (t_id,))
                conn.commit()

        # Active -> Finished
        cur.execute("SELECT id, start_time, duration_minutes, test_key FROM tournaments WHERE status = 'active'")
        active_tournaments = cur.fetchall()
        for tour in active_tournaments:
            t_id, start_str, duration, test_key = tour[0], tour[1], tour[2], tour[3]
            start_t = datetime.fromisoformat(str(start_str))
            dur_mins = duration if duration else 2
            end_t = start_t + timedelta(minutes=dur_mins)
            
            if now >= end_t:
                cur.execute("UPDATE tournaments SET status = 'finished' WHERE id = %s", (t_id,))
                cur.execute("UPDATE tests SET is_public = TRUE WHERE test_key = %s", (test_key,))
                conn.commit()
                
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"Lifecycle error: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(manage_tournaments_lifecycle, 'interval', seconds=30)
scheduler.start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
