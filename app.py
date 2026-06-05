import json
import os
from typing import AsyncIterator, List

import anthropic
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID", "")
META_BASE = "https://graph.facebook.com/v21.0"

app = FastAPI(title="Meta Ads AI")

# ─────────────────────────── Meta Graph helpers ────────────────────────────

async def graph_get(path: str, params: dict = None) -> dict:
    p = {"access_token": META_ACCESS_TOKEN, **(params or {})}
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{META_BASE}/{path}", params=p)
        return r.json()


def account_id() -> str:
    aid = META_AD_ACCOUNT_ID
    return f"act_{aid}" if not aid.startswith("act_") else aid


# ─────────────────────────── Tool definitions ──────────────────────────────

TOOLS = [
    {
        "name": "get_account_overview",
        "description": (
            "Henter overordnet ytelse for annonsekontoen: total forbruk, impressioner, "
            "klikk, CTR, CPC, rekkevidde og konverteringer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date_preset": {
                    "type": "string",
                    "description": "today | yesterday | last_7d | last_30d | this_month | last_month",
                    "default": "last_30d",
                }
            },
        },
    },
    {
        "name": "get_campaigns",
        "description": "Lister alle kampanjer med status, budsjett og grunnleggende ytelsestall.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_preset": {"type": "string", "default": "last_30d"},
                "status": {
                    "type": "string",
                    "description": "ACTIVE | PAUSED | ALL",
                    "default": "ALL",
                },
            },
        },
    },
    {
        "name": "get_campaign_insights",
        "description": "Henter detaljert innsikt for én spesifikk kampanje.",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string"},
                "date_preset": {"type": "string", "default": "last_30d"},
            },
            "required": ["campaign_id"],
        },
    },
    {
        "name": "get_top_ads",
        "description": "Returnerer topp-annonser sortert etter forbruk eller klikk.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "description": "spend | clicks | ctr",
                    "default": "spend",
                },
                "date_preset": {"type": "string", "default": "last_30d"},
            },
        },
    },
    {
        "name": "get_spend_trend",
        "description": "Henter daglig forbruk de siste N dagene for å vise trend.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 30}
            },
        },
    },
]

# ─────────────────────────── Mock data (demo mode) ─────────────────────────

MOCK: dict = {
    "get_account_overview": {
        "_demo": True,
        "data": [{
            "spend": "18 432.00",
            "impressions": "3 847 291",
            "clicks": "62 184",
            "ctr": "1.62",
            "cpc": "0.30",
            "cpm": "4.79",
            "reach": "2 183 456",
            "actions": [
                {"action_type": "purchase", "value": "1 241"},
                {"action_type": "add_to_cart", "value": "5 823"},
                {"action_type": "link_click", "value": "62 184"},
            ],
            "action_values": [{"action_type": "purchase", "value": "124 320.00"}],
        }],
    },
    "get_campaigns": {
        "_demo": True,
        "data": [
            {"id": "1001", "name": "Sommersalg 2024 – Konvertering", "status": "ACTIVE",
             "objective": "OUTCOME_SALES", "daily_budget": "20000",
             "insights": {"data": [{"spend": "6 421.30", "impressions": "1 087 432",
                                     "clicks": "21 234", "ctr": "1.95", "cpc": "0.30"}]}},
            {"id": "1002", "name": "Brand Awareness Q2", "status": "ACTIVE",
             "objective": "OUTCOME_AWARENESS", "daily_budget": "15000",
             "insights": {"data": [{"spend": "4 210.80", "impressions": "1 745 678",
                                     "clicks": "14 543", "ctr": "0.83", "cpc": "0.29"}]}},
            {"id": "1003", "name": "Retargeting – Handlekurv", "status": "ACTIVE",
             "objective": "OUTCOME_SALES", "daily_budget": "10000",
             "insights": {"data": [{"spend": "5 190.40", "impressions": "756 234",
                                     "clicks": "18 876", "ctr": "2.50", "cpc": "0.28"}]}},
            {"id": "1004", "name": "Nykundeakvisisjon – Lookalike", "status": "PAUSED",
             "objective": "OUTCOME_SALES", "daily_budget": "25000",
             "insights": {"data": [{"spend": "2 609.50", "impressions": "257 947",
                                     "clicks": "7 531", "ctr": "2.92", "cpc": "0.35"}]}},
        ],
    },
    "get_top_ads": {
        "_demo": True,
        "data": [
            {"id": "ad_001", "name": "Sommertilbud – video 15s", "status": "ACTIVE",
             "insights": {"data": [{"spend": "3 100.00", "impressions": "520 000",
                                     "clicks": "9 500", "ctr": "1.83", "cpc": "0.33"}]}},
            {"id": "ad_002", "name": "Produktkarusell – dame", "status": "ACTIVE",
             "insights": {"data": [{"spend": "2 450.00", "impressions": "380 000",
                                     "clicks": "7 200", "ctr": "1.89", "cpc": "0.34"}]}},
            {"id": "ad_003", "name": "Statisk bilde – salg 50%", "status": "ACTIVE",
             "insights": {"data": [{"spend": "1 870.30", "impressions": "187 432",
                                     "clicks": "5 100", "ctr": "2.72", "cpc": "0.37"}]}},
        ],
    },
    "get_spend_trend": {
        "_demo": True,
        "data": [
            {"date": "2024-05-07", "spend": "580"},
            {"date": "2024-05-08", "spend": "620"},
            {"date": "2024-05-09", "spend": "510"},
            {"date": "2024-05-10", "spend": "480"},
            {"date": "2024-05-11", "spend": "420"},
            {"date": "2024-05-12", "spend": "590"},
            {"date": "2024-05-13", "spend": "640"},
            {"date": "2024-05-14", "spend": "700"},
            {"date": "2024-05-15", "spend": "720"},
            {"date": "2024-05-16", "spend": "695"},
            {"date": "2024-05-17", "spend": "730"},
            {"date": "2024-05-18", "spend": "680"},
            {"date": "2024-05-19", "spend": "520"},
            {"date": "2024-05-20", "spend": "490"},
            {"date": "2024-05-21", "spend": "760"},
            {"date": "2024-05-22", "spend": "810"},
            {"date": "2024-05-23", "spend": "795"},
            {"date": "2024-05-24", "spend": "755"},
            {"date": "2024-05-25", "spend": "820"},
            {"date": "2024-05-26", "spend": "780"},
            {"date": "2024-05-27", "spend": "610"},
            {"date": "2024-05-28", "spend": "590"},
            {"date": "2024-05-29", "spend": "840"},
            {"date": "2024-05-30", "spend": "870"},
            {"date": "2024-05-31", "spend": "830"},
            {"date": "2024-06-01", "spend": "890"},
            {"date": "2024-06-02", "spend": "860"},
            {"date": "2024-06-03", "spend": "775"},
            {"date": "2024-06-04", "spend": "710"},
            {"date": "2024-06-05", "spend": "432"},
        ],
    },
}

# ─────────────────────────── Tool execution ────────────────────────────────

async def run_tool(name: str, inputs: dict) -> dict:
    demo = not (META_ACCESS_TOKEN and META_AD_ACCOUNT_ID)
    if demo:
        return MOCK.get(name, {"data": [], "_demo": True})

    aid = account_id()
    dp = inputs.get("date_preset", "last_30d")

    if name == "get_account_overview":
        return await graph_get(f"{aid}/insights", {
            "fields": "spend,impressions,clicks,ctr,cpc,cpm,reach,actions,action_values",
            "date_preset": dp, "level": "account",
        })
    if name == "get_campaigns":
        params = {
            "fields": "id,name,status,objective,daily_budget,lifetime_budget,"
                      "insights{spend,impressions,clicks,ctr,cpc}",
            "date_preset": dp,
        }
        s = inputs.get("status", "ALL")
        if s != "ALL":
            params["effective_status"] = json.dumps([s])
        return await graph_get(f"{aid}/campaigns", params)
    if name == "get_campaign_insights":
        return await graph_get(f"{inputs['campaign_id']}/insights", {
            "fields": "campaign_name,spend,impressions,clicks,ctr,cpc,cpm,reach,frequency,actions,action_values",
            "date_preset": dp,
        })
    if name == "get_top_ads":
        return await graph_get(f"{aid}/ads", {
            "fields": "id,name,status,insights{spend,impressions,clicks,ctr,cpc}",
            "date_preset": dp, "limit": 10,
        })
    if name == "get_spend_trend":
        days = inputs.get("days", 30)
        return await graph_get(f"{aid}/insights", {
            "fields": "spend", "time_increment": "1",
            "date_preset": f"last_{days}d", "level": "account",
        })
    return {"error": "unknown tool"}


# ─────────────────────────── API routes ────────────────────────────────────

@app.get("/api/status")
async def status():
    return {
        "meta": bool(META_ACCESS_TOKEN and META_AD_ACCOUNT_ID),
        "ai": bool(ANTHROPIC_API_KEY),
        "demo": not bool(META_ACCESS_TOKEN and META_AD_ACCOUNT_ID),
    }


@app.get("/api/dashboard")
async def dashboard():
    overview, campaigns, trend = await asyncio.gather(
        run_tool("get_account_overview", {"date_preset": "last_30d"}),
        run_tool("get_campaigns", {"date_preset": "last_30d"}),
        run_tool("get_spend_trend", {"days": 30}),
    )
    return {"overview": overview, "campaigns": campaigns, "trend": trend}


class ChatBody(BaseModel):
    message: str
    history: List[dict] = []


@app.post("/api/chat")
async def chat(body: ChatBody):
    if not ANTHROPIC_API_KEY:
        return JSONResponse({"error": "Mangler ANTHROPIC_API_KEY"}, status_code=400)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    system = (
        "Du er en ekspert Meta Ads AI-assistent med sanntids tilgang til annonsekonto-data. "
        "Svar alltid på norsk med mindre brukeren skriver engelsk. "
        "Når du henter data – analyser og gi konkrete, handlingsrettede råd. "
        "Vær direkte, profesjonell og analytisk. Bruk tall og prosenter for å underbygge poengene dine. "
        "Avslutt gjerne med 1-2 konkrete anbefalinger."
    )

    messages = body.history + [{"role": "user", "content": body.message}]

    async def stream() -> AsyncIterator[str]:
        msgs = list(messages)
        while True:
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                system=system,
                messages=msgs,
                tools=TOOLS,
            ) as s:
                final = s.get_final_message()

            tool_uses = [b for b in final.content if b.type == "tool_use"]

            # Stream text blocks
            for block in final.content:
                if block.type == "text" and block.text:
                    yield f"data: {json.dumps({'t': 'text', 'v': block.text})}\n\n"

            if not tool_uses:
                yield f"data: {json.dumps({'t': 'done'})}\n\n"
                break

            # Execute tools
            msgs.append({"role": "assistant", "content": final.content})
            results = []
            for tu in tool_uses:
                yield f"data: {json.dumps({'t': 'tool', 'v': tu.name})}\n\n"
                result = await run_tool(tu.name, tu.input)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
            msgs.append({"role": "user", "content": results})

    return StreamingResponse(stream(), media_type="text/event-stream")


# Serve frontend – import asyncio before mounting
import asyncio  # noqa: E402 (used above in gather)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=True)
