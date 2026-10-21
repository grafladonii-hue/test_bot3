import json
import os

class AnswerSubmit(BaseModel):
    tournament_id: int
    user_id: int
    question_index: int
    selected_option: int

# Ёрдамчи функция: questions.json ёки базадан тўғри жавобни топиш
def get_correct_option_index(test_key: str, question_index: int) -> int:
    try:
        # Агар саволлар локал JSON файлда сақланса (масалан: questions.json)
        if os.path.exists("questions.json"):
            with open("questions.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                # Берилган test_key бўйича тестни топамиз
                test_set = data.get(test_key, [])
                if question_index < len(test_set):
                    # Савол ичидаги тўғри жавоб индекси (масалан, 'correct' ёки 'answer_index')
                    return test_set[question_index].get("correct_option", 0)
        
        # Агар тестлар Supabase базасидаги tests жадвалида сақланса, шу ердан сўров қиламиз:
        # res = supabase.table("tests").select("questions_data").eq("test_key", test_key).single().execute()
        # questions = res.data["questions_data"]
        # return questions[question_index]["correct_option"]
        
    except Exception as e:
        print(f"Хатолик тўғри жавобни топишда: {e}")
    
    return 0  # Агар топилмаса дефолт қиймат

@app.post("/api/tournament/submit-answer")
def submit_answer(data: AnswerSubmit):
    # 1. Турнир ҳали фаол ҳолатда эканлигини текшириш
    tour = supabase.table("tournaments").select("*").eq("id", data.tournament_id).single().execute()
    if not tour.data or tour.data["status"] != "active":
        raise HTTPException(status_code=400, detail="Турнир фаол эмас ёки тугаган!")
    
    # 2. Бу саволга фойдаланувчи олдин жавоб берган-бермаганини текшириш
    existing = supabase.table("tournament_user_answers") \
        .select("*") \
        .eq("tournament_id", data.tournament_id) \
        .eq("user_id", data.user_id) \
        .eq("question_index", data.question_index) \
        .execute()
    
    if existing.data:
        raise HTTPException(status_code=400, detail="Бу саволга аллақачон жавоб бергансиз!")

    # 3. Тест калитини оламиз ва тўғри жавобни аниқлаймиз
    test_key = tour.data["test_key"]
    correct_option_index = get_correct_option_index(test_key, data.question_index)
    
    is_correct = (data.selected_option == correct_option_index)

    # 4. Жавобни базага сақлаш
    supabase.table("tournament_user_answers").insert({
        "tournament_id": data.tournament_id,
        "user_id": data.user_id,
        "question_index": data.question_index,
        "selected_option": data.selected_option,
        "is_correct": is_correct
    }).execute()

    # Агар жавоб тўғри бўлса, фойдаланувчининг баллини ҳам янгилаб қўйиш мумкин
    if is_correct:
        # Балл қўшиш логикаси (ихтиёрий)
        pass

    return {
        "status": "success",
        "is_correct": is_correct,
        "correct_option": correct_option_index
    }
