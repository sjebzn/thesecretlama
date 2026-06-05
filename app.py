import json
import os
from typing import AsyncIterator, List

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

app = FastAPI(title="JARVIS AI")


class ChatBody(BaseModel):
    message: str
    history: List[dict] = []


@app.get("/api/status")
async def status():
    return {"ai": bool(ANTHROPIC_API_KEY)}


@app.post("/api/chat")
async def chat(body: ChatBody):
    if not ANTHROPIC_API_KEY:
        return JSONResponse({"error": "Missing ANTHROPIC_API_KEY"}, status_code=400)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    system = (
        "Du er JARVIS, en intelligent AI-assistent som hjelper med alt fra bilmekanikk til livsstilstips. "
        "Du er høflig, grunndig, og gir praktiske råd. Svar på norsk med mindre brukeren skriver engelsk. "
        "Vær direkte og håpefull. Gi konkrete forslag når mulig."
    )

    messages = body.history + [{"role": "user", "content": body.message}]

    async def stream() -> AsyncIterator[str]:
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


app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=True)
