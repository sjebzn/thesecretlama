import asyncio
import json
import os
import re
import sqlite3
from datetime import datetime
from typing import AsyncIterator, Optional

import anthropic
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv = __import__('dotenv').load_dotenv
load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DB_PATH = "monir.db"

app = FastAPI(title="MONIR")

@app.middleware("http")
async def no_cache_html(request: Request, call_next):
    response = await call_next(request)
    if request.url.path in ("/", "/index.html"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = sqlite3.connect(DB_PATH)
    with open("monir.db.init.sql") as f:
        conn.executescript(f.read())
    conn.commit()

    # Migrate existing tables safely
    migrations = [
        "ALTER TABLE habits ADD COLUMN emoji TEXT DEFAULT '⚡'",
        "ALTER TABLE habits ADD COLUMN xp_reward INTEGER DEFAULT 20",
        "ALTER TABLE habits ADD COLUMN last_completed TEXT",
        "ALTER TABLE users ADD COLUMN city TEXT DEFAULT 'Oslo'",
    ]
    for m in migrations:
        try:
            conn.execute(m)
            conn.commit()
        except Exception:
            pass

    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        conn.execute("INSERT INTO users (name, bio) VALUES (?, ?)",
                     ("Bruker", ""))
        conn.commit()
    conn.close()

init_db()

# ════════════════════════════════════════════════
# PYDANTIC MODELS
# ════════════════════════════════════════════════

class ChatBody(BaseModel):
    message: str
    mode: str = "normal"

class LegalBody(BaseModel):
    question: str

class AddNoteBody(BaseModel):
    note: str
    category: str = "general"

class AddXPBody(BaseModel):
    xp: int
    source: str = "activity"

class HabitCompleteBody(BaseModel):
    habit_id: int

class QuestToggleBody(BaseModel):
    quest_id: int
    completed: bool

class PriorityBody(BaseModel):
    context: str = ""

class OnboardingBody(BaseModel):
    name: str
    age: Optional[int] = None
    city: Optional[str] = "Oslo"
    height_cm: Optional[int] = None
    weight_kg: Optional[float] = None
    discipline: int = 50
    intelligence: int = 50
    health: int = 50
    business_score: int = 50
    rep_builder: int = 3
    rep_tech: int = 3
    rep_entrepreneur: int = 3
    rep_athlete: int = 2
    rep_leader: int = 3
    main_quest: str = "Bli finansielt uavhengig"
    main_quest_progress: int = 0
    assets: list = []
    businesses: list = []
    vehicles: list = []
    milestones: list = []
    achievements: list = []
    habits: list = []

# ════════════════════════════════════════════════
# LEGAL ENGINE
# ════════════════════════════════════════════════

LAW_MAP = {
    "arbeidsrett": "https://lovdata.no/dokument/NL/lov/2005-06-17-62",
    "arbeidsmiljø": "https://lovdata.no/dokument/NL/lov/2005-06-17-62",
    "oppsigelse": "https://lovdata.no/dokument/NL/lov/2005-06-17-62",
    "avskjed": "https://lovdata.no/dokument/NL/lov/2005-06-17-62",
    "sykemelding": "https://lovdata.no/dokument/NL/lov/2005-06-17-62",
    "permittering": "https://lovdata.no/dokument/NL/lov/2005-06-17-62",
    "ferie": "https://lovdata.no/dokument/NL/lov/1992-11-27-109",
    "feriepenger": "https://lovdata.no/dokument/NL/lov/1992-11-27-109",
    "husleie": "https://lovdata.no/dokument/NL/lov/1999-03-26-17",
    "leiekontrakt": "https://lovdata.no/dokument/NL/lov/1999-03-26-17",
    "depositum": "https://lovdata.no/dokument/NL/lov/1999-03-26-17",
    "forbruker": "https://lovdata.no/dokument/NL/lov/2002-06-21-34",
    "reklamasjon": "https://lovdata.no/dokument/NL/lov/2002-06-21-34",
    "garanti": "https://lovdata.no/dokument/NL/lov/2002-06-21-34",
    "skatt": "https://lovdata.no/dokument/NL/lov/1999-03-26-14",
    "mva": "https://lovdata.no/dokument/NL/lov/2009-06-19-58",
    "aksjeselskap": "https://lovdata.no/dokument/NL/lov/1997-06-13-44",
    "aksjer": "https://lovdata.no/dokument/NL/lov/1997-06-13-44",
    "styre": "https://lovdata.no/dokument/NL/lov/1997-06-13-44",
    "kontrakt": "https://lovdata.no/dokument/NL/lov/1918-05-31-4",
    "avtale": "https://lovdata.no/dokument/NL/lov/1918-05-31-4",
    "gdpr": "https://lovdata.no/dokument/NL/lov/2018-06-15-38",
    "personvern": "https://lovdata.no/dokument/NL/lov/2018-06-15-38",
    "inkasso": "https://lovdata.no/dokument/NL/lov/1988-05-13-26",
    "konkurs": "https://lovdata.no/dokument/NL/lov/1984-06-08-58",
    "markedsføring": "https://lovdata.no/dokument/NL/lov/2009-01-09-2",
    "straffeloven": "https://lovdata.no/dokument/NL/lov/2005-05-20-28",
    "nabolov": "https://lovdata.no/dokument/NL/lov/1961-06-16-15",
}

LEGAL_SYSTEM_PROMPT = """Du er MONIR sin juridiske research-motor — LegalStreetSmart Engine.

Du er IKKE advokat og skal aldri late som det.
Du er en ekstremt kompetent juridisk research-assistent og strateg for norsk rett.

OBLIGATORISK FORMAT — alltid disse fem delene:

⚖️ **LOVEN SIER:**
[Relevant lovtekst med nøyaktige §-referanser. Sitér hjemmelen direkte.]

🏛️ **PRAKSIS I VIRKELIGHETEN:**
[Hva domstolene faktisk gjør. Typiske utfall. Forskjell mellom lovtekst og praksis.]

📊 **RISIKOVURDERING:**
[Konkret: Høy / Middels / Lav — og NØYAKTIG HVORFOR.]

📋 **DOKUMENTER DETTE:**
[Konkret liste — hvilke dokumenter og bevis som trengs.]

🎯 **NESTE SMARTE STEG:**
[Konkret handlingsplan. Hvem kontaktes? I hvilken rekkefølge?]

---
⚠️ *Research og strategi, ikke juridisk rådgivning. Store saker: bruk advokat.*

Alltid norsk. Vær direkte og gatesmart."""

async def _fetch_law_text(url: str) -> str:
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (compatible; MONIR/1.0)"},
            follow_redirects=True, timeout=7.0
        ) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return ""
            text = r.text
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'&nbsp;', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:3000]
    except Exception:
        return ""

async def fetch_legal_context(question: str):
    q = question.lower()
    seen, urls = set(), []
    for kw, url in LAW_MAP.items():
        if kw in q and url not in seen:
            seen.add(url)
            urls.append(url)
        if len(urls) >= 2:
            break
    if not urls:
        return "", []
    results = await asyncio.gather(*[_fetch_law_text(u) for u in urls], return_exceptions=True)
    parts, sources = [], []
    for url, text in zip(urls, results):
        if isinstance(text, str) and len(text) > 200:
            law_id = url.split("/")[-1]
            parts.append(f"[Lovdata — {url}]\n{text[:2500]}")
            sources.append(f"lovdata.no/{law_id}")
    return "\n\n---\n\n".join(parts), sources

# ════════════════════════════════════════════════
# AUTO-LEARN
# ════════════════════════════════════════════════

async def extract_facts(user_msg: str) -> list:
    """Extract and save personal facts. Returns list of newly saved fact strings."""
    if not ANTHROPIC_API_KEY or len(user_msg) < 25:
        return []
    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": (
                f"Extract concrete personal facts the user revealed about themselves.\n"
                f"They said: \"{user_msg}\"\n\n"
                "Return JSON: [{\"category\": \"personal|health|business|tech|legal|general\", \"note\": \"fact\"}]\n"
                "Only specific facts they revealed. Max 3. Return [] if nothing.\nReturn ONLY the JSON array."
            )}]
        )
        text = resp.content[0].text.strip()
        if not text.startswith('['):
            return []
        facts = json.loads(text)
        if not facts:
            return []
        db = get_db()
        saved = []
        for f in facts[:3]:
            note = (f.get('note') or '').strip()
            if len(note) < 10:
                continue
            exists = db.execute(
                "SELECT COUNT(*) FROM memory_notes WHERE user_id=1 AND note LIKE ?",
                ('%' + note[:40] + '%',)
            ).fetchone()[0]
            if not exists:
                db.execute(
                    "INSERT INTO memory_notes (user_id, category, note, source) VALUES (1, ?, ?, 'auto')",
                    (f.get('category', 'general'), note)
                )
                saved.append(note)
        db.commit()
        db.close()
        return saved
    except Exception:
        return []

def build_system_prompt(mode: str = "normal") -> str:
    db = get_db()
    user = db.execute("SELECT name, bio FROM users LIMIT 1").fetchone()
    char = db.execute("SELECT * FROM character_stats WHERE user_id=1").fetchone()
    notes = db.execute("SELECT category, note FROM memory_notes WHERE user_id=1 ORDER BY created_at DESC LIMIT 20").fetchall()
    businesses = db.execute("SELECT name, level, status FROM businesses WHERE user_id=1").fetchall()
    habits = db.execute("SELECT name FROM habits WHERE user_id=1").fetchall()
    db.close()

    name = user["name"] if user else "Sebastian"
    bio = user["bio"] if user else ""
    notes_text = "\n".join([f"• [{n['category']}] {n['note']}" for n in notes]) if notes else "Ingen ennå"
    biz_text = "\n".join([f"• {b['name']} (Level {b['level']}, {b['status']})" for b in businesses]) if businesses else "Ingen"
    habits_text = ", ".join([h['name'] for h in habits]) if habits else "Ingen"

    char_info = ""
    if char:
        char_info = (
            f"Level {char['level']} | XP: {char['xp']}/{char['xp_next']}\n"
            f"Disiplin: {char['discipline']}% | Intelligens: {char['intelligence']}% | "
            f"Helse: {char['health']}% | Business: {char['business_score']}%\n"
            f"Main Quest: {char['main_quest']} ({char['main_quest_progress']}%)\n"
        )

    if mode == "onboarding":
        return (
            f"Du er MONIR i KARTLEGGINGS-MODUS. Du kartlegger {name} systematisk.\n\n"
            f"Det du vet om ham:\n{bio}\n\nFakta: {notes_text}\n\n"
            "Stil ETT personlig, innsiktsfullt spørsmål om gangen.\n"
            "Spør om: mål, frykt, verdier, rutiner, forretning, helse, styrker/svakheter.\n"
            "REGLER: ETT spørsmål. Kort anerkjennelse (1 setning). Lytt. Alltid norsk."
        )

    return (
        f"Du er MONIR — {name}s personlige Life OS og AI-strateg.\n\n"
        f"PROFIL: {bio}\n\n"
        f"KARAKTER:\n{char_info}\n"
        f"EMPIRE:\n{biz_text}\n\n"
        f"VANER: {habits_text}\n\n"
        f"MINNE — hva du vet om {name}:\n{notes_text}\n\n"
        "Du er konkret, proaktiv, ekte. Du tenker som en god venn med business-hjerne.\n"
        "Du husker alt og bruker det aktivt. Alltid norsk. Svar presist med mindre han ber om mer."
    )

# ════════════════════════════════════════════════
# XP HELPER
# ════════════════════════════════════════════════

def add_xp_to_char(xp_amount: int) -> dict:
    db = get_db()
    char = db.execute("SELECT * FROM character_stats WHERE user_id=1").fetchone()
    if not char:
        db.close()
        return {"leveled_up": False}

    new_xp = char["xp"] + xp_amount
    new_level = char["level"]
    new_xp_next = char["xp_next"]
    leveled_up = False

    while new_xp >= new_xp_next:
        new_xp -= new_xp_next
        new_level += 1
        new_xp_next = new_level * 1000
        leveled_up = True

    db.execute(
        "UPDATE character_stats SET xp=?, level=?, xp_next=? WHERE user_id=1",
        (new_xp, new_level, new_xp_next)
    )
    db.commit()
    db.close()
    return {"leveled_up": leveled_up, "new_level": new_level, "xp": new_xp, "xp_next": new_xp_next}

# ════════════════════════════════════════════════
# ONBOARDING
# ════════════════════════════════════════════════

@app.post("/api/onboarding/save")
async def save_onboarding(body: OnboardingBody):
    db = get_db()
    db.execute("UPDATE users SET name=?, city=?, updated_at=CURRENT_TIMESTAMP WHERE id=1",
               (body.name, body.city or "Oslo"))
    db.commit()

    age = body.age or 0
    level = max(1, age)
    xp_next = level * 1000

    db.execute("DELETE FROM character_stats WHERE user_id=1")
    db.execute("""INSERT INTO character_stats
        (user_id, level, xp, xp_next, discipline, intelligence, health, business_score,
         rep_builder, rep_tech, rep_entrepreneur, rep_athlete, rep_leader,
         main_quest, main_quest_progress, height_cm, weight_kg, age, net_worth_trend, onboarded)
        VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'+0%',1)""",
        (level, 0, xp_next, body.discipline, body.intelligence, body.health, body.business_score,
         body.rep_builder, body.rep_tech, body.rep_entrepreneur, body.rep_athlete, body.rep_leader,
         body.main_quest, body.main_quest_progress, body.height_cm, body.weight_kg, age))

    db.execute("DELETE FROM assets WHERE user_id=1")
    for i, a in enumerate(body.assets):
        db.execute("INSERT INTO assets (user_id, name, emoji, status, sort_order) VALUES (1,?,?,?,?)",
                   (a.get("name",""), a.get("emoji","📦"), a.get("status","owned"), i))

    db.execute("DELETE FROM businesses WHERE user_id=1")
    for i, b in enumerate(body.businesses):
        db.execute("INSERT INTO businesses (user_id, name, level, status, sort_order) VALUES (1,?,?,?,?)",
                   (b.get("name",""), b.get("level",1), b.get("status","active"), i))

    db.execute("DELETE FROM vehicles WHERE user_id=1")
    for v in body.vehicles:
        db.execute("INSERT INTO vehicles (user_id, name, model_detail, condition_pct) VALUES (1,?,?,?)",
                   (v.get("name",""), v.get("model",""), v.get("condition",80)))

    db.execute("DELETE FROM quests WHERE user_id=1")
    for i, m in enumerate(body.milestones):
        db.execute("INSERT INTO quests (user_id, title, completed, xp_reward, sort_order) VALUES (1,?,?,100,?)",
                   (m.get("title",""), 1 if m.get("completed") else 0, i))

    db.execute("DELETE FROM achievements WHERE user_id=1")
    for i, a in enumerate(body.achievements):
        db.execute("INSERT INTO achievements (user_id, name, unlocked, sort_order) VALUES (1,?,?,?)",
                   (a.get("name",""), 1 if a.get("unlocked") else 0, i))

    db.execute("DELETE FROM habits WHERE user_id=1")
    for h in body.habits:
        db.execute("INSERT INTO habits (user_id, name, emoji, xp_reward, frequency) VALUES (1,?,?,?,?)",
                   (h.get("name",""), h.get("emoji","⚡"), h.get("xp",20), h.get("freq","DAGLIG")))

    db.commit()
    db.close()

    completed_quests = sum(1 for m in body.milestones if m.get("completed"))
    unlocked_achievements = sum(1 for a in body.achievements if a.get("unlocked"))
    starting_xp = (completed_quests * 100) + (unlocked_achievements * 200)
    if starting_xp > 0:
        add_xp_to_char(starting_xp)

    bio = (f"Norsk gründer, {body.age} år, {body.city}. "
           f"Høyde: {body.height_cm}cm, Vekt: {body.weight_kg}kg. "
           f"Jobber med: {', '.join(b.get('name','') for b in body.businesses)}.")
    db2 = get_db()
    db2.execute("UPDATE users SET bio=? WHERE id=1", (bio,))
    db2.commit()
    db2.close()

    return {"status": "onboarded", "level": level}

# ════════════════════════════════════════════════
# CHARACTER
# ════════════════════════════════════════════════

@app.get("/api/character")
async def get_character():
    db = get_db()
    char = db.execute("SELECT * FROM character_stats WHERE user_id=1").fetchone()
    user = db.execute("SELECT name, city FROM users LIMIT 1").fetchone()
    db.close()
    if not char:
        return {"onboarded": False}
    return {
        "onboarded": bool(char["onboarded"]),
        "level": char["level"], "xp": char["xp"], "xp_next": char["xp_next"],
        "discipline": char["discipline"], "intelligence": char["intelligence"],
        "health": char["health"], "business_score": char["business_score"],
        "rep_builder": char["rep_builder"], "rep_tech": char["rep_tech"],
        "rep_entrepreneur": char["rep_entrepreneur"], "rep_athlete": char["rep_athlete"],
        "rep_leader": char["rep_leader"],
        "main_quest": char["main_quest"], "main_quest_progress": char["main_quest_progress"],
        "height_cm": char["height_cm"], "weight_kg": char["weight_kg"],
        "age": char["age"], "net_worth_trend": char["net_worth_trend"],
        "name": user["name"] if user else "Sebastian",
        "city": user["city"] if user else "Oslo",
    }

@app.post("/api/xp/add")
async def add_xp_endpoint(body: AddXPBody):
    result = add_xp_to_char(body.xp)
    return result

# ════════════════════════════════════════════════
# ASSETS
# ════════════════════════════════════════════════

@app.get("/api/assets")
async def get_assets():
    db = get_db()
    rows = db.execute("SELECT * FROM assets WHERE user_id=1 ORDER BY sort_order").fetchall()
    db.close()
    return {"assets": [dict(r) for r in rows]}

@app.post("/api/assets/update")
async def update_asset(body: dict):
    db = get_db()
    db.execute("UPDATE assets SET status=? WHERE id=? AND user_id=1",
               (body.get("status","locked"), body.get("id")))
    db.commit()
    db.close()
    return {"status": "updated"}

# ════════════════════════════════════════════════
# BUSINESSES
# ════════════════════════════════════════════════

@app.get("/api/businesses")
async def get_businesses():
    db = get_db()
    rows = db.execute("SELECT * FROM businesses WHERE user_id=1 ORDER BY sort_order").fetchall()
    db.close()
    return {"businesses": [dict(r) for r in rows]}

@app.post("/api/businesses/update")
async def update_business(body: dict):
    db = get_db()
    db.execute(
        "UPDATE businesses SET next_action=?, level=? WHERE id=? AND user_id=1",
        (body.get("next_action",""), body.get("level",1), body.get("id"))
    )
    db.commit()
    db.close()
    return {"status": "updated"}

# ════════════════════════════════════════════════
# QUESTS
# ════════════════════════════════════════════════

@app.get("/api/quests")
async def get_quests():
    db = get_db()
    rows = db.execute("SELECT * FROM quests WHERE user_id=1 ORDER BY sort_order").fetchall()
    db.close()
    return {"quests": [dict(r) for r in rows]}

@app.post("/api/quests/toggle")
async def toggle_quest(body: QuestToggleBody):
    db = get_db()
    db.execute("UPDATE quests SET completed=? WHERE id=? AND user_id=1",
               (1 if body.completed else 0, body.quest_id))
    db.commit()
    db.close()
    if body.completed:
        add_xp_to_char(100)
    return {"status": "updated"}

@app.post("/api/quests/add")
async def add_quest(body: dict):
    db = get_db()
    db.execute("INSERT INTO quests (user_id, title, completed, xp_reward) VALUES (1,?,0,100)",
               (body.get("title",""),))
    db.commit()
    db.close()
    return {"status": "added"}

# ════════════════════════════════════════════════
# HABITS / SIDE QUESTS
# ════════════════════════════════════════════════

@app.get("/api/habits")
async def get_habits():
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    rows = db.execute("SELECT * FROM habits WHERE user_id=1 ORDER BY created_at").fetchall()
    done_ids = {
        r["habit_id"] for r in
        db.execute("SELECT habit_id FROM habit_completions WHERE user_id=1 AND date=?", (today,)).fetchall()
    }
    db.close()
    habits = []
    for r in rows:
        h = dict(r)
        h["done_today"] = r["id"] in done_ids
        habits.append(h)
    return {"habits": habits, "date": today}

@app.post("/api/habits/complete")
async def complete_habit(body: HabitCompleteBody):
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    already = db.execute(
        "SELECT COUNT(*) FROM habit_completions WHERE habit_id=? AND user_id=1 AND date=?",
        (body.habit_id, today)
    ).fetchone()[0]
    if already:
        db.close()
        return {"status": "already_done", "xp": 0}

    habit = db.execute("SELECT xp_reward, streak FROM habits WHERE id=? AND user_id=1", (body.habit_id,)).fetchone()
    if not habit:
        db.close()
        return {"status": "not_found"}

    xp = habit["xp_reward"]
    new_streak = habit["streak"] + 1
    db.execute("INSERT INTO habit_completions (habit_id, user_id, date) VALUES (?,1,?)", (body.habit_id, today))
    db.execute("UPDATE habits SET streak=?, last_completed=? WHERE id=?", (new_streak, today, body.habit_id))
    db.commit()
    db.close()
    result = add_xp_to_char(xp)
    return {"status": "done", "xp": xp, "streak": new_streak, **result}

# ════════════════════════════════════════════════
# ACHIEVEMENTS
# ════════════════════════════════════════════════

@app.get("/api/achievements")
async def get_achievements():
    db = get_db()
    rows = db.execute("SELECT * FROM achievements WHERE user_id=1 ORDER BY sort_order").fetchall()
    db.close()
    return {"achievements": [dict(r) for r in rows]}

# ════════════════════════════════════════════════
# VEHICLES
# ════════════════════════════════════════════════

@app.get("/api/vehicles")
async def get_vehicles():
    db = get_db()
    rows = db.execute("SELECT * FROM vehicles WHERE user_id=1 ORDER BY sort_order").fetchall()
    db.close()
    return {"vehicles": [dict(r) for r in rows]}

# ════════════════════════════════════════════════
# PRIORITY ENGINE
# ════════════════════════════════════════════════

@app.post("/api/priority")
async def get_priority(body: PriorityBody):
    if not ANTHROPIC_API_KEY:
        return JSONResponse({"error": "Missing API key"}, 400)

    db = get_db()
    char = db.execute("SELECT * FROM character_stats WHERE user_id=1").fetchone()
    businesses = db.execute("SELECT name, level, status, next_action FROM businesses WHERE user_id=1").fetchall()
    notes = db.execute("SELECT category, note FROM memory_notes WHERE user_id=1 ORDER BY created_at DESC LIMIT 8").fetchall()
    history = db.execute("SELECT role, content FROM chat_history WHERE user_id=1 ORDER BY timestamp DESC LIMIT 6").fetchall()
    db.close()

    biz_text = "\n".join([f"- {b['name']} (Level {b['level']}, {b['status']})"
                          + (f" → {b['next_action']}" if b['next_action'] else "")
                          for b in businesses]) or "Ingen registrert"
    notes_text = "\n".join([f"[{n['category']}] {n['note']}" for n in notes]) or "Ingen"
    hist_text = "\n".join([f"{h['role']}: {h['content'][:80]}" for h in reversed(list(history))]) or "Ingen"

    char_info = ""
    if char:
        char_info = f"Disiplin: {char['discipline']}%, Business: {char['business_score']}%"

    db_name = get_db()
    user_row = db_name.execute("SELECT name FROM users LIMIT 1").fetchone()
    db_name.close()
    user_display = user_row["name"] if user_row else "brukeren"

    system = f"""Du er MONIR Priority Engine — brutal, fokusert, ROI-drevet.

{user_display} er en norsk gründer som sjonglerer flere prosjekter.
Din jobb: Se mønsteret og gi ÉN klar ordre.

BRUK ALLTID DETTE FORMATET (ikke mer, ikke mindre):

⚡ STATUS: [FOKUSERT / SPREDT / KRITISK]

📊 [1-2 setninger om hva du ser i dataene]

🎯 FOKUS NÅ: [ÉT prosjekt eller ÉN handling]
⏱ Tidsblokk: [X timer]

💡 FORDI: [1 setning — konkret ROI-argument]

Vær brutal. Ingen fluff. Max 6 linjer."""

    messages = [{
        "role": "user",
        "content": f"EMPIRE:\n{biz_text}\n\nMINNE:\n{notes_text}\n\nSISTE SAMTALE:\n{hist_text}\n\nSTATS: {char_info}\n\nEkstra: {body.context}"
    }]

    async def stream():
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        async with client.messages.stream(
            model="claude-haiku-4-5-20251001",
            max_tokens=250,
            system=system,
            messages=messages
        ) as s:
            async for text in s.text_stream:
                yield f"data: {json.dumps({'t': 'text', 'v': text})}\n\n"
        yield f"data: {json.dumps({'t': 'done'})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")

# ════════════════════════════════════════════════
# CHAT
# ════════════════════════════════════════════════

@app.post("/api/chat")
async def chat(body: ChatBody):
    if not ANTHROPIC_API_KEY:
        return JSONResponse({"error": "Missing ANTHROPIC_API_KEY"}, status_code=400)

    system = build_system_prompt(body.mode)
    db = get_db()
    history = db.execute(
        "SELECT role, content FROM chat_history WHERE user_id=1 ORDER BY timestamp DESC LIMIT 30"
    ).fetchall()
    db.close()
    messages = [{"role": r["role"], "content": r["content"]} for r in reversed(list(history))]
    messages.append({"role": "user", "content": body.message})

    async def stream() -> AsyncIterator[str]:
        full_response = ""
        # Start fact extraction in parallel while streaming the main response
        extract_task = asyncio.create_task(extract_facts(body.message))
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        async with client.messages.stream(
            model="claude-sonnet-4-6", max_tokens=1024, system=system, messages=messages
        ) as s:
            async for text in s.text_stream:
                full_response += text
                yield f"data: {json.dumps({'t': 'text', 'v': text})}\n\n"

        try:
            db2 = get_db()
            db2.execute("INSERT INTO chat_history (user_id, role, content) VALUES (1,'user',?)", (body.message,))
            db2.execute("INSERT INTO chat_history (user_id, role, content) VALUES (1,'assistant',?)", (full_response,))
            db2.execute(
                "DELETE FROM chat_history WHERE user_id=1 AND id NOT IN "
                "(SELECT id FROM chat_history WHERE user_id=1 ORDER BY timestamp DESC LIMIT 200)"
            )
            db2.commit()
            db2.close()
        except Exception:
            pass

        # Emit memory event if new facts were learned — client receives before done
        try:
            new_facts = await extract_task
            if new_facts:
                yield f"data: {json.dumps({'t': 'memory', 'facts': new_facts})}\n\n"
        except Exception:
            pass

        yield f"data: {json.dumps({'t': 'done'})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")

@app.post("/api/legal")
async def legal_chat(body: LegalBody):
    if not ANTHROPIC_API_KEY:
        return JSONResponse({"error": "Missing ANTHROPIC_API_KEY"}, status_code=400)

    legal_context, sources = await fetch_legal_context(body.question)
    db = get_db()
    notes = db.execute("SELECT category, note FROM memory_notes WHERE user_id=1 ORDER BY created_at DESC LIMIT 10").fetchall()
    db.close()

    system = LEGAL_SYSTEM_PROMPT
    if legal_context:
        system += f"\n\n📚 HENTET FRA NORSKE RETTSKILDER:\n{legal_context}"
    if notes:
        system += "\n\nHVA MONIR VET OM BRUKEREN:\n" + "\n".join([f"• [{n['category']}] {n['note']}" for n in notes])

    async def stream() -> AsyncIterator[str]:
        full_response = ""
        if sources:
            yield f"data: {json.dumps({'t': 'sources', 'v': sources})}\n\n"
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        async with client.messages.stream(
            model="claude-sonnet-4-6", max_tokens=2048, system=system,
            messages=[{"role": "user", "content": body.question}]
        ) as s:
            async for text in s.text_stream:
                full_response += text
                yield f"data: {json.dumps({'t': 'text', 'v': text})}\n\n"
        yield f"data: {json.dumps({'t': 'done'})}\n\n"

        try:
            db2 = get_db()
            db2.execute("INSERT INTO chat_history (user_id, role, content) VALUES (1,'user',?)", (f"[JURIDISK] {body.question}",))
            db2.execute("INSERT INTO chat_history (user_id, role, content) VALUES (1,'assistant',?)", (full_response,))
            db2.commit()
            db2.close()
        except Exception:
            pass
        asyncio.create_task(extract_facts(body.question))

    return StreamingResponse(stream(), media_type="text/event-stream")

# ════════════════════════════════════════════════
# LEGACY / NOTES
# ════════════════════════════════════════════════

@app.get("/api/notes")
async def get_notes():
    db = get_db()
    notes = db.execute("SELECT id, category, note, created_at FROM memory_notes WHERE user_id=1 ORDER BY created_at DESC LIMIT 50").fetchall()
    db.close()
    return {"notes": [dict(n) for n in notes]}

@app.post("/api/notes/add")
async def add_note(body: AddNoteBody):
    db = get_db()
    db.execute("INSERT INTO memory_notes (user_id, category, note) VALUES (1,?,?)", (body.category, body.note))
    db.commit()
    db.close()
    return {"status": "saved"}

@app.delete("/api/notes/{note_id}")
async def delete_note(note_id: int):
    db = get_db()
    db.execute("DELETE FROM memory_notes WHERE id=? AND user_id=1", (note_id,))
    db.commit()
    db.close()
    return {"status": "deleted"}

@app.get("/api/today")
async def get_today():
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    data = db.execute("SELECT * FROM lifestyle_data WHERE user_id=1 AND date=?", (today,)).fetchone()
    db.close()
    if data:
        return {"sleep": data["sleep_hours"], "exercise": data["exercise_minutes"],
                "water": data["water_intake"], "mood": data["mood_rating"]}
    return {"sleep": None, "exercise": None, "water": None, "mood": None}

@app.get("/api/history")
async def get_history(limit: int = 20):
    db = get_db()
    rows = db.execute(
        "SELECT role, content FROM chat_history WHERE user_id=1 ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    db.close()
    return {"messages": [{"role": r["role"], "content": r["content"]} for r in reversed(list(rows))]}

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=True)
