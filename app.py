import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import AsyncIterator, List

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv = __import__('dotenv').load_dotenv
load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DB_PATH = "monir.db"

app = FastAPI(title="MONIR 2027")

# ════════════════════════════════════════════════
# DATABASE INIT
# ════════════════════════════════════════════════

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    with open("monir.db.init.sql") as f:
        cursor.executescript(f.read())
    conn.commit()

    # Default user hvis ikke eksisterer
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO users (name, bio) VALUES (?, ?)",
            ("Sebastian", "En praktisk, ambisiøs person som vil leve bedre.")
        )
        conn.commit()
    conn.close()

init_db()

def get_db():
    return sqlite3.connect(DB_PATH)

# ════════════════════════════════════════════════
# MODELS
# ════════════════════════════════════════════════

class ChatBody(BaseModel):
    message: str
    history: List[dict] = []

class UpdateProfileBody(BaseModel):
    name: str = None
    bio: str = None
    goals: str = None

class LogLifestyleBody(BaseModel):
    date: str
    sleep_hours: float = None
    exercise_minutes: int = None
    water_intake: int = None
    mood_rating: int = None
    energy_rating: int = None
    notes: str = None

class AddEventBody(BaseModel):
    title: str
    description: str = None
    start_time: str
    end_time: str = None
    category: str = "work"

# ════════════════════════════════════════════════
# API ENDPOINTS
# ════════════════════════════════════════════════

@app.get("/api/user")
async def get_user():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users LIMIT 1")
    user = cursor.fetchone()
    db.close()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user[0], "name": user[1], "bio": user[2],
        "goals": user[3], "energy_level": user[5], "mood": user[6]
    }

@app.post("/api/user/update")
async def update_user(body: UpdateProfileBody):
    db = get_db()
    cursor = db.cursor()
    updates = []
    values = []
    if body.name:
        updates.append("name = ?")
        values.append(body.name)
    if body.bio:
        updates.append("bio = ?")
        values.append(body.bio)
    if body.goals:
        updates.append("goals = ?")
        values.append(body.goals)
    if updates:
        updates.append("updated_at = CURRENT_TIMESTAMP")
        cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = 1", values)
        db.commit()
    db.close()
    return {"status": "updated"}

@app.get("/api/today")
async def get_today():
    db = get_db()
    cursor = db.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT * FROM lifestyle_data WHERE date = ?", (today,))
    data = cursor.fetchone()
    cursor.execute(
        "SELECT title, start_time FROM calendar_events WHERE date(start_time) = ? ORDER BY start_time",
        (today,)
    )
    events = [{"title": e[0], "time": e[1]} for e in cursor.fetchall()]
    db.close()
    if data:
        return {
            "sleep": data[3], "exercise": data[4], "water": data[5],
            "mood": data[6], "energy": data[7], "notes": data[8],
            "events": events
        }
    return {"sleep": None, "exercise": None, "water": None, "mood": None, "energy": None, "events": events}

@app.post("/api/lifestyle/log")
async def log_lifestyle(body: LogLifestyleBody):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO lifestyle_data (user_id, date, sleep_hours, exercise_minutes, water_intake, mood_rating, energy_rating, notes) "
        "VALUES (1, ?, ?, ?, ?, ?, ?, ?)",
        (body.date, body.sleep_hours, body.exercise_minutes, body.water_intake, body.mood_rating, body.energy_rating, body.notes)
    )
    db.commit()
    db.close()
    return {"status": "logged"}

@app.get("/api/calendar")
async def get_calendar(days: int = 30):
    db = get_db()
    cursor = db.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute(
        "SELECT id, title, start_time, end_time, category, completed FROM calendar_events WHERE date(start_time) >= ? LIMIT ?",
        (today, days)
    )
    events = [
        {"id": e[0], "title": e[1], "start": e[2], "end": e[3], "category": e[4], "completed": e[5]}
        for e in cursor.fetchall()
    ]
    db.close()
    return {"events": events}

@app.post("/api/calendar/add")
async def add_event(body: AddEventBody):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO calendar_events (user_id, title, description, start_time, end_time, category) "
        "VALUES (1, ?, ?, ?, ?, ?)",
        (body.title, body.description, body.start_time, body.end_time, body.category)
    )
    db.commit()
    db.close()
    return {"status": "added"}

@app.post("/api/chat")
async def chat(body: ChatBody):
    if not ANTHROPIC_API_KEY:
        return JSONResponse({"error": "Missing ANTHROPIC_API_KEY"}, status_code=400)

    db = get_db()
    cursor = db.cursor()

    # ════ LOAD SEBASTIAN'S COMPLETE CONTEXT ════
    cursor.execute("SELECT name, bio, goals FROM users LIMIT 1")
    user = cursor.fetchone()

    # Load recent goals + progress
    cursor.execute("SELECT title, progress, status FROM goals WHERE status = 'active' LIMIT 5")
    goals = cursor.fetchall()

    # Load recent habits
    cursor.execute("SELECT name, streak, category FROM habits LIMIT 5")
    habits = cursor.fetchall()

    # Load today's lifestyle data
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT sleep_hours, exercise_minutes, mood_rating, energy_rating FROM lifestyle_data WHERE date = ?", (today,))
    today_data = cursor.fetchone()

    # Load upcoming events
    cursor.execute("SELECT title, start_time, category FROM calendar_events WHERE date(start_time) >= date('now') LIMIT 3")
    upcoming = cursor.fetchall()

    db.close()

    # ════ INTELLIGENT SYSTEM PROMPT ════
    goals_text = "\n".join([f"• {g[0]} ({int(g[1])}% progress)" for g in goals]) if goals else "Ennå ingen mål satt"
    habits_text = "\n".join([f"• {h[0]} ({h[1]} dagers streak)" for h in habits]) if habits else "Ennå ingen vaner"
    upcoming_text = "\n".join([f"• {e[0]} ({e[2]})" for e in upcoming]) if upcoming else "Ingen kommende events"

    if today_data:
        today_str = f"""• Søvn: {today_data[0] or '?'} timer
• Trening: {today_data[1] or '?'} minutter
• Humør: {today_data[2] or '?'}/10
• Energi: {today_data[3] or '?'}%"""
    else:
        today_str = "Ennå ingen data logget i dag"

    system = f"""Du er MONIR, {user[0]}s personlige AI-livsassistent fra 2027.
Du kjenner ham dypt og lærer stadig mer. Du er hans beste mentor, venn, og coach.

📋 OM {user[0].upper()}:
{user[1]}

🎯 HANS AKTIVE MÅL:
{goals_text}

💪 HANS KJERNEHVANER:
{habits_text}

📊 I DAG:
{today_str}

📅 KOMMENDE:
{upcoming_text}

🧠 DU GJØR:
1. Husker ALLEM om ham (alle data)
2. Gir proaktive, konkrete råd basert på hans profil
3. Motiverer han mot hans spesifikke mål (BMW, OBDAI, events, helse)
4. Spørrer oppfølgingsspørsmål
5. Viser genuine omsorg og interesse
6. Lærer av hver samtale
7. Gir actionable tips, ikke bare ord

🔥 HUSKAML hans fokusområder:
- Tech: OBDAI, AutoSvar AI, Instacall, WebDesign
- Automotive: BMW E60, MS45.1, ECU-tuning, diagnostikk
- Business: Autovers.no, Arrangementer/events, Konsultasjon
- Health: 6h søvn, 4x trening, ernæring

Alltid på NORSK. Vær ekte, personlig, intelligent. Kort & klar. Gi konkrete tips."""

    messages = body.history + [{"role": "user", "content": body.message}]

    async def stream() -> AsyncIterator[str]:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=system,
            messages=messages,
        ) as s:
            for text in s.text_stream:
                yield f"data: {json.dumps({'t': 'text', 'v': text})}\n\n"
        yield f"data: {json.dumps({'t': 'done'})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")

@app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=True)
