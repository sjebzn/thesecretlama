import asyncio
import json
import os
import re
import sqlite3
from datetime import datetime
from typing import AsyncIterator

import anthropic
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
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
            ("Sebastian", "En praktisk, ambisiøs norsk gründer som vil leve bedre og bygge større.")
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

class AddNoteBody(BaseModel):
    note: str
    category: str = "general"

class LegalBody(BaseModel):
    question: str

# ════════════════════════════════════════════════
# LEGAL STREET SMART ENGINE
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
    "utleier": "https://lovdata.no/dokument/NL/lov/1999-03-26-17",
    "leietaker": "https://lovdata.no/dokument/NL/lov/1999-03-26-17",
    "depositum": "https://lovdata.no/dokument/NL/lov/1999-03-26-17",
    "kjøp": "https://lovdata.no/dokument/NL/lov/2002-06-21-34",
    "forbruker": "https://lovdata.no/dokument/NL/lov/2002-06-21-34",
    "reklamasjon": "https://lovdata.no/dokument/NL/lov/2002-06-21-34",
    "garanti": "https://lovdata.no/dokument/NL/lov/2002-06-21-34",
    "eiendom": "https://lovdata.no/dokument/NL/lov/1992-07-03-93",
    "bolig": "https://lovdata.no/dokument/NL/lov/1992-07-03-93",
    "avhending": "https://lovdata.no/dokument/NL/lov/1992-07-03-93",
    "skatt": "https://lovdata.no/dokument/NL/lov/1999-03-26-14",
    "inntektsskatt": "https://lovdata.no/dokument/NL/lov/1999-03-26-14",
    "mva": "https://lovdata.no/dokument/NL/lov/2009-06-19-58",
    "merverdiavgift": "https://lovdata.no/dokument/NL/lov/2009-06-19-58",
    "aksjeselskap": "https://lovdata.no/dokument/NL/lov/1997-06-13-44",
    "aksjer": "https://lovdata.no/dokument/NL/lov/1997-06-13-44",
    "styre": "https://lovdata.no/dokument/NL/lov/1997-06-13-44",
    "daglig leder": "https://lovdata.no/dokument/NL/lov/1997-06-13-44",
    "kontrakt": "https://lovdata.no/dokument/NL/lov/1918-05-31-4",
    "avtale": "https://lovdata.no/dokument/NL/lov/1918-05-31-4",
    "urimelig": "https://lovdata.no/dokument/NL/lov/1918-05-31-4",
    "gdpr": "https://lovdata.no/dokument/NL/lov/2018-06-15-38",
    "personvern": "https://lovdata.no/dokument/NL/lov/2018-06-15-38",
    "personopplysninger": "https://lovdata.no/dokument/NL/lov/2018-06-15-38",
    "inkasso": "https://lovdata.no/dokument/NL/lov/1988-05-13-26",
    "gjeld": "https://lovdata.no/dokument/NL/lov/1992-11-09-99",
    "gjeldsordning": "https://lovdata.no/dokument/NL/lov/1992-11-17-99",
    "konkurs": "https://lovdata.no/dokument/NL/lov/1984-06-08-58",
    "markedsføring": "https://lovdata.no/dokument/NL/lov/2009-01-09-2",
    "reklame": "https://lovdata.no/dokument/NL/lov/2009-01-09-2",
    "straff": "https://lovdata.no/dokument/NL/lov/2005-05-20-28",
    "straffeloven": "https://lovdata.no/dokument/NL/lov/2005-05-20-28",
    "politiet": "https://lovdata.no/dokument/NL/lov/2005-05-20-28",
    "hevd": "https://lovdata.no/dokument/NL/lov/1966-12-09-1",
    "naboforhold": "https://lovdata.no/dokument/NL/lov/1961-06-16-15",
    "nabolov": "https://lovdata.no/dokument/NL/lov/1961-06-16-15",
}

LEGAL_SYSTEM_PROMPT = """Du er MONIR sin juridiske research-motor — LegalStreetSmart Engine.

Du er IKKE advokat og skal aldri late som det.
Du er en ekstremt kompetent juridisk research-assistent og strateg for norsk rett.

Du finner og analyserer:
• Lover, §-referanser og hjemler
• Rettspraksis (Høyesterett, lagmannsretter, tingretter)
• Praksis fra Arbeidstilsynet, Forbrukerrådet, Skatteetaten, PFU
• Vanlige feil folk gjør og hva som faktisk fungerer
• Styrken på ulike argumenter og bevis
• Praktisk strategi og neste steg

OBLIGATORISK FORMAT — alltid disse fem delene:

⚖️ **LOVEN SIER:**
[Relevant lovtekst med nøyaktige §-referanser. Sitér hjemmelen direkte. Aldri vag.]

🏛️ **PRAKSIS I VIRKELIGHETEN:**
[Hva domstolene og forvaltningen faktisk gjør. Typiske utfall. Forskjellen mellom
lovtekst og hva som skjer i praksis. Tendenser. Hva Forbrukerrådet/Arbeidstilsynet
typisk avgjør. Hvilke argumenter veier tungt hos dommere.]

📊 **RISIKOVURDERING:**
[Konkret: Høy / Middels / Lav — og NØYAKTIG HVORFOR.
Worst case. Mest sannsynlig utfall. Hva som kan endre bildet.]

📋 **DOKUMENTER DETTE:**
[Konkret liste — hvilke dokumenter, hvilke bevis, hva som er sterkt,
hva som mangler. Spesifikke dokumenttyper, ikke vage råd.]

🎯 **NESTE SMARTE STEG:**
[Konkret handlingsplan. Hvem kontaktes? I hvilken rekkefølge?
Hva sendes? Hva ventes med? Sterke vs. svake kort.
Praktisk strategi — ikke bare "kontakt advokat".]

---
⚠️ *Research og strategi, ikke juridisk rådgivning. Store saker: bruk advokat.*

Du kjenner Sebastian Salih — norsk gründer, 31 år, driver AS-er innen tech og bil.
Gjør rådene personlige og relevante. Alltid norsk. Vær direkte og gatesmart."""

async def _fetch_law_text(url: str) -> str:
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (compatible; MONIR/1.0 research)"},
            follow_redirects=True,
            timeout=7.0
        ) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return ""
            text = r.text
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'&nbsp;', ' ', text)
            text = re.sub(r'&amp;', '&', text)
            text = re.sub(r'&lt;', '<', text)
            text = re.sub(r'&gt;', '>', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:3500]
    except Exception:
        return ""

async def fetch_legal_context(question: str) -> tuple[str, list[str]]:
    q_lower = question.lower()
    urls_seen: set[str] = set()
    urls: list[str] = []
    for keyword, url in LAW_MAP.items():
        if keyword in q_lower and url not in urls_seen:
            urls_seen.add(url)
            urls.append(url)
        if len(urls) >= 2:
            break

    if not urls:
        return "", []

    results = await asyncio.gather(*[_fetch_law_text(u) for u in urls], return_exceptions=True)

    parts: list[str] = []
    sources: list[str] = []
    for url, text in zip(urls, results):
        if isinstance(text, str) and len(text) > 200:
            law_id = url.split("/")[-1]
            parts.append(f"[Lovdata — {url}]\n{text[:2500]}")
            sources.append(f"lovdata.no/{law_id}")

    return "\n\n---\n\n".join(parts), sources

# ════════════════════════════════════════════════
# AUTO-LEARN: extract personal facts from conversation
# ════════════════════════════════════════════════

async def extract_facts(user_msg: str):
    if not ANTHROPIC_API_KEY or len(user_msg) < 25:
        return
    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": (
                    f"Extract concrete personal facts about Sebastian from what he said.\n"
                    f"He said: \"{user_msg}\"\n\n"
                    "Return JSON: [{\"category\": \"personal|health|business|tech|legal|general\", \"note\": \"fact\"}]\n"
                    "Only specific facts he revealed about himself. Max 3. Return [] if nothing.\n"
                    "Return ONLY the JSON array."
                )
            }]
        )
        text = resp.content[0].text.strip()
        if not text.startswith('['):
            return
        facts = json.loads(text)
        if not facts:
            return
        db = get_db()
        cursor = db.cursor()
        for f in facts[:3]:
            note = (f.get('note') or '').strip()
            if len(note) < 10:
                continue
            cursor.execute(
                "SELECT COUNT(*) FROM memory_notes WHERE user_id=1 AND note LIKE ?",
                ('%' + note[:40] + '%',)
            )
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    "INSERT INTO memory_notes (user_id, category, note, source) VALUES (1, ?, ?, 'auto')",
                    (f.get('category', 'general'), note)
                )
        db.commit()
        db.close()
    except Exception:
        pass

# ════════════════════════════════════════════════
# ENDPOINTS
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
    return {"id": user[0], "name": user[1], "bio": user[2], "goals": user[3]}

@app.post("/api/user/update")
async def update_user(body: UpdateProfileBody):
    db = get_db()
    cursor = db.cursor()
    updates, values = [], []
    if body.name: updates.append("name = ?"); values.append(body.name)
    if body.bio: updates.append("bio = ?"); values.append(body.bio)
    if body.goals: updates.append("goals = ?"); values.append(body.goals)
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
    db.close()
    if data:
        return {"sleep": data[3], "exercise": data[4], "water": data[5], "mood": data[6], "energy": data[7]}
    return {"sleep": None, "exercise": None, "water": None, "mood": None, "energy": None}

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

@app.get("/api/history")
async def get_history(limit: int = 30):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT role, content FROM chat_history WHERE user_id = 1 ORDER BY timestamp DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    db.close()
    return {"messages": [{"role": r[0], "content": r[1]} for r in reversed(rows)]}

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
    cursor.execute("SELECT title, progress FROM goals WHERE status = 'active' LIMIT 5")
    goals = cursor.fetchall()
    cursor.execute("SELECT name, streak FROM habits LIMIT 5")
    habits = cursor.fetchall()
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT sleep_hours, exercise_minutes, mood_rating, energy_rating FROM lifestyle_data WHERE date = ?", (today,))
    today_data = cursor.fetchone()
    cursor.execute("SELECT category, note FROM memory_notes WHERE user_id = 1 ORDER BY created_at DESC LIMIT 20")
    saved_notes = cursor.fetchall()
    cursor.execute(
        "SELECT role, content FROM chat_history WHERE user_id = 1 ORDER BY timestamp DESC LIMIT 30"
    )
    db_history = [{"role": r[0], "content": r[1]} for r in reversed(cursor.fetchall())]
    db.close()

    goals_text = "\n".join([f"• {g[0]} ({int(g[1])}%)" for g in goals]) if goals else "Ingen"
    habits_text = "\n".join([f"• {h[0]} ({h[1]} dager)" for h in habits]) if habits else "Ingen"
    notes_text = "\n".join([f"• [{n[0].upper()}] {n[1]}" for n in saved_notes]) if saved_notes else "Ingen lagrede fakta ennå"
    today_str = (
        f"Søvn: {today_data[0]}h, Trening: {today_data[1]}min, Humør: {today_data[2]}/10"
        if today_data else "Ingen data logget i dag"
    )

    if body.mode == "onboarding":
        system = (
            "Du er MONIR i KARTLEGGINGS-MODUS. Bli kjent med Sebastian ved å stille "
            "ham personlige, innsiktsfulle spørsmål ÉN om gangen.\n\n"
            f"Det du vet:\n{user[1]}\n\n"
            f"Fakta du har lært:\n{notes_text}\n\n"
            "Spør om: livsvisjon, frykt, verdier, relasjoner, motivasjon, BMW, "
            "forretningsdrømmer, helse-mål, rutiner, styrker/svakheter.\n\n"
            "REGLER: ETT spørsmål om gangen. Kort anerkjennelse (1 setning). "
            "Du er her for å LYTTE. Alltid norsk."
        )
    else:
        system = "Du er MONIR, Sebastians personlige AI. Du kjenner ham dypt og husker alt.\n\n"
        system += f"SEBASTIAN:\n{user[1]}\n\n"
        system += f"MÅL:\n{goals_text}\n\n"
        system += f"VANER:\n{habits_text}\n\n"
        system += f"I DAG: {today_str}\n\n"
        system += f"MINNE — fakta du har lært om Sebastian:\n{notes_text}\n\n"
        system += "Du er konkret, proaktiv, ekte. Du gir råd, motiverer, husker alt.\n"
        system += "Alltid norsk. Svar kort og presist med mindre han ber om detaljer."

    messages = db_history + [{"role": "user", "content": body.message}]

    async def stream() -> AsyncIterator[str]:
        full_response = ""
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        async with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system,
            messages=messages,
        ) as s:
            async for text in s.text_stream:
                full_response += text
                yield f"data: {json.dumps({'t': 'text', 'v': text})}\n\n"
        yield f"data: {json.dumps({'t': 'done'})}\n\n"

        try:
            db2 = get_db()
            c2 = db2.cursor()
            c2.execute("INSERT INTO chat_history (user_id, role, content) VALUES (1, 'user', ?)", (body.message,))
            c2.execute("INSERT INTO chat_history (user_id, role, content) VALUES (1, 'assistant', ?)", (full_response,))
            c2.execute(
                "DELETE FROM chat_history WHERE user_id = 1 AND id NOT IN "
                "(SELECT id FROM chat_history WHERE user_id = 1 ORDER BY timestamp DESC LIMIT 200)"
            )
            db2.commit()
            db2.close()
        except Exception:
            pass

        asyncio.create_task(extract_facts(body.message))

    return StreamingResponse(stream(), media_type="text/event-stream")

@app.post("/api/legal")
async def legal_chat(body: LegalBody):
    if not ANTHROPIC_API_KEY:
        return JSONResponse({"error": "Missing ANTHROPIC_API_KEY"}, status_code=400)

    legal_context, sources = await fetch_legal_context(body.question)

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT name, bio, goals FROM users LIMIT 1")
    user = cursor.fetchone()
    cursor.execute("SELECT category, note FROM memory_notes WHERE user_id = 1 ORDER BY created_at DESC LIMIT 15")
    notes = cursor.fetchall()
    db.close()

    system = LEGAL_SYSTEM_PROMPT
    if legal_context:
        system += f"\n\n📚 HENTET FRA NORSKE RETTSKILDER:\n{legal_context}"
    if notes:
        notes_text = "\n".join([f"• [{n[0]}] {n[1]}" for n in notes])
        system += f"\n\nHVA MONIR VET OM SEBASTIAN:\n{notes_text}"

    messages = [{"role": "user", "content": body.question}]

    async def stream() -> AsyncIterator[str]:
        full_response = ""
        if sources:
            yield f"data: {json.dumps({'t': 'sources', 'v': sources})}\n\n"

        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        async with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=system,
            messages=messages,
        ) as s:
            async for text in s.text_stream:
                full_response += text
                yield f"data: {json.dumps({'t': 'text', 'v': text})}\n\n"
        yield f"data: {json.dumps({'t': 'done'})}\n\n"

        try:
            db2 = get_db()
            c2 = db2.cursor()
            c2.execute("INSERT INTO chat_history (user_id, role, content) VALUES (1, 'user', ?)", (f"[JURIDISK] {body.question}",))
            c2.execute("INSERT INTO chat_history (user_id, role, content) VALUES (1, 'assistant', ?)", (full_response,))
            db2.commit()
            db2.close()
        except Exception:
            pass

        asyncio.create_task(extract_facts(body.question))

    return StreamingResponse(stream(), media_type="text/event-stream")

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=True)
