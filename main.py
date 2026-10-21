from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import json
import os

# Модель: Админ томонидан турнир яратиш учун (дефолт вақт 2 дақиқага созланди)
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
        response = supabase.table("tournaments").select("*").execute()
        return {"status": "success", "tournaments": response.data}
    except Exception as e:
        return {"status": "error", "message": str(e), "tournaments": []}

# 2. Админ турнир яратиши ва тестни вақти келгунча яшириши
@app.post("/api/admin/create-tournament")
def create_tournament(data: TournamentCreate):
    supabase.table("tests").update({"is_public": False}).eq("test_key", data.test_key).execute()

    response = supabase.table("tournaments").insert({
        "title": data.title,
        "test_key": data.test_key,
        "start_time": data.start_time.isoformat(),
        "duration_minutes": data.duration_minutes,
        "status": "waiting"
    }).execute()
    
    return {"status": "success", "message": "Жамоавий тест режалаштирилди ва вақти келгунча яширилди!"}

# Ёрдамчи функция: Тўғри жавобни топиш
def get_correct_option_index(test_key: str, question_index: int) -> int:
    try:
        if os.path.exists("questions.json"):
            with open("questions.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                test_set = data.get(test_key, [])
                if question_index < len(test_set):
                    return test_set[question_index].get("correct_option", 0)
    except Exception as e:
        print(f"Хатолик тўғри жавобни топишда: {e}")
    return 0

# 3. Иштирокчининг жавобини қабул қилиш ва текшириш
@app.post("/api/tournament/submit-answer")
def submit_answer(data: AnswerSubmit):
    tour = supabase.table("tournaments").select("*").eq("id", data.tournament_id).single().execute()
    if not tour.data or tour.data["status"] != "active":
        raise HTTPException(status_code=400, detail="Турнир фаол эмас ёки тугаган!")
    
    existing = supabase.table("tournament_user_answers") \
        .select("*") \
        .eq("tournament_id", data.tournament_id) \
        .eq("user_id", data.user_id) \
        .eq("question_index", data.question_index) \
        .execute()
    
    if existing.data:
        raise HTTPException(status_code=400, detail="Бу саволга аллақачон жавоб бергансиз!")

    test_key = tour.data["test_key"]
    correct_option_index = get_correct_option_index(test_key, data.question_index)
    
    is_correct = (data.selected_option == correct_option_index)

    supabase.table("tournament_user_answers").insert({
        "tournament_id": data.tournament_id,
        "user_id": data.user_id,
        "question_index": data.question_index,
        "selected_option": data.selected_option,
        "is_correct": is_correct
    }).execute()

    return {
        "status": "success",
        "is_correct": is_correct,
        "correct_option": correct_option_index
    }

# 4. Турнир рейтинг (Leaderboard) натижаларини олиш endpoint'и
@app.get("/api/tournament/{tournament_id}/leaderboard")
def get_tournament_leaderboard(tournament_id: int):
    try:
        answers = supabase.table("tournament_user_answers") \
            .select("user_id, is_correct") \
            .eq("tournament_id", tournament_id) \
            .execute()
        
        if not answers.data:
            return {"status": "success", "leaderboard": []}
        
        user_scores = {}
        for row in answers.data:
            uid = row["user_id"]
            if uid not in user_scores:
                user_scores[uid] = {"user_id": uid, "score": 0, "correct_count": 0}
            
            if row["is_correct"]:
                user_scores[uid]["score"] += 1
                user_scores[uid]["correct_count"] += 1
                
        sorted_leaderboard = sorted(user_scores.values(), key=lambda x: x["score"], reverse=True)
        
        for index, item in enumerate(sorted_leaderboard):
            item["rank"] = index + 1
            
        return {"status": "success", "leaderboard": sorted_leaderboard}
        
    except Exception as e:
        return {"status": "error", "message": str(e), "leaderboard": []}

# 5. Фон жараёни: Турнирларнинг бошланиш ва тугаш вақтини автоматик бошқариш (Дефолт 2 дақиқа)
def manage_tournaments_lifecycle():
    now = datetime.now().astimezone()
    
    waiting_tournaments = supabase.table("tournaments").select("*").eq("status", "waiting").execute()
    for tour in waiting_tournaments.data:
        start_t = datetime.fromisoformat(tour["start_time"])
        if now >= start_t:
            supabase.table("tournaments").update({"status": "active"}).eq("id", tour["id"]).execute()

    active_tournaments = supabase.table("tournaments").select("*").eq("status", "active").execute()
    for tour in active_tournaments.data:
        start_t = datetime.fromisoformat(tour["start_time"])
        duration = tour.get("duration_minutes", 2)
        end_t = start_t + timedelta(minutes=duration)
        
        if now >= end_t:
            supabase.table("tournaments").update({"status": "finished"}).eq("id", tour["id"]).execute()
            supabase.table("tests").update({"is_public": True}).eq("test_key", tour["test_key"]).execute()

scheduler = BackgroundScheduler()
scheduler.add_job(manage_tournaments_lifecycle, 'interval', seconds=30)
scheduler.start()
