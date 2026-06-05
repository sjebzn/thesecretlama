import json
import os
import sqlite3
from datetime import datetime
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
    mode: str = "normal"

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

class AddNoteBody(BaseModel):
    note: str
    category: str = "general"

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

@app.get("/api/notes")
async def get_notes():
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT id, category, note, created_at FROM memory_notes WHERE user_id = 1 ORDER BY created_at DESC LIMIT 50"
    )
    notes = [{"id": n[0], "category": n[1], "note": n[2], "at": n[3]} for n in cursor.fetchall()]
    db.close()
    return {"notes": notes}

@app.post("/api/notes/add")
async def add_note(body: AddNoteBody):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO memory_notes (user_id, category, note) VALUES (1, ?, ?)",
        (body.category, body.note)
    )
    db.commit()
    db.close()
    return {"status": "saved"}

@app.delete("/api/notes/{note_id}")
async def delete_note(note_id: int):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM memory_notes WHERE id = ? AND user_id = 1", (note_id,))
    db.commit()
    db.close()
    return {"status": "deleted"}

@app.post("/api/chat")
async def chat(body: ChatBody):
    if not ANTHROPIC_API_KEY:
        return JSONResponse({"error": "Missing ANTHROPIC_API_KEY"}, status_code=400)

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT name, bio, goals FROM users LIMIT 1")
    user = cursor.fetchone()

    cursor.execute("SELECT title, progress, status FROM goals WHERE status = 'active' LIMIT 5")
    goals = cursor.fetchall()

    cursor.execute("SELECT name, streak, category FROM habits LIMIT 5")
    habits = cursor.fetchall()

    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT sleep_hours, exercise_minutes, mood_rating, energy_rating FROM lifestyle_data WHERE date = ?", (today,))
    today_data = cursor.fetchone()

    cursor.execute("SELECT title, start_time, category FROM calendar_events WHERE date(start_time) >= date('now') LIMIT 3")
    upcoming = cursor.fetchall()

    cursor.execute("SELECT category, note FROM memory_notes WHERE user_id = 1 ORDER BY created_at DESC LIMIT 20")
    saved_notes = cursor.fetchall()

    db.close()

    goals_text = "\n".join([f"• {g[0]} ({int(g[1])}%)" for g in goals]) if goals else "Ingen mål"
    habits_text = "\n".join([f"• {h[0]} ({h[1]} dager)" for h in habits]) if habits else "Ingen vaner"
    upcoming_text = "\n".join([f"• {e[0]}" for e in upcoming]) if upcoming else "Ingen events"
    notes_text = "\n".join([f"• [{n[0].upper()}] {n[1]}" for n in saved_notes]) if saved_notes else "Ingen lagrede fakta ennå"

    if today_data:
        today_str = f"Søvn: {today_data[0]}h, Trening: {today_data[1]}min, Humør: {today_data[2]}/10"
    else:
        today_str = "Ingen data i dag"

    if body.mode == "onboarding":
        system = (
            "Du er MONIR i DYBDEKARTLEGGINGS-MODUS. Din oppgave er å bli kjent med Sebastian "
            "ved å stille ham personlige, innsiktsfulle spørsmål ÉN om gangen.\n\n"
            f"Det du allerede vet:\n{user[1]}\n\n"
            "Temaer å utforske: livsvisjon, frykt, verdier, relasjoner, motivasjon, "
            "BMW-passion, forretningsdrømmer, helse-mål, daglige rutiner, styrker/svakheter, "
            "hva som gjør ham glad eller frustrert, 5-årsbildet, hva han trenger hjelp med.\n\n"
            "REGLER: Still ETT spørsmål om gangen. Anerkjenn svaret genuint og kort (1 setning). "
            "Still deretter neste spørsmål. Du er her for å LYTTE, ikke snakke mye. "
            "Maks 2 setninger per svar fra deg — resten er spørsmål.\n"
            "Alltid norsk. Vær ekte, nysgjerrig og empatisk."
        )
    else:
        system = "Du er MONIR, Sebastians personlige AI-assistent fra 2027. Du kjenner ham dypt.\n\n"
        system += f"SEBASTIAN:\n{user[1]}\n\n"
        system += f"MÅL:\n{goals_text}\n\n"
        system += f"VANER:\n{habits_text}\n\n"
        system += f"I DAG: {today_str}\n\n"
        system += f"KOMMENDE: {upcoming_text}\n\n"
        system += f"MINNE (fakta du har lært om Sebastian):\n{notes_text}\n\n"
        system += "Gi proaktive råd, motiver, husk alt, hjelp. Fokus: BMW, OBDAI, Autovers, helse, events.\n"
        system += "Alltid norsk. Vær ekte og konkret."

    messages = body.history + [{"role": "user", "content": body.message}]

    async def stream() -> AsyncIterator[str]:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        async with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=system,
            messages=messages,
        ) as s:
            async for text in s.text_stream:
                yield f"data: {json.dumps({'t': 'text', 'v': text})}\n\n"
        yield f"data: {json.dumps({'t': 'done'})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=True)
