#!/usr/bin/env python3
"""
MONIR 2027 — Initialize Sebastian Salih's Complete Profile
All his data, projects, skills, and goals
"""

import sqlite3
from datetime import datetime, timedelta

DB_PATH = "monir.db"

def init_sebastian():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Clear existing data
    cursor.execute("DELETE FROM users")
    cursor.execute("DELETE FROM goals")
    cursor.execute("DELETE FROM habits")
    cursor.execute("DELETE FROM calendar_events")

    # ════════════════════════════════════════════════
    # USER PROFILE
    # ════════════════════════════════════════════════

    cursor.execute("""
        INSERT INTO users (name, bio, goals, timezone, mood)
        VALUES (?, ?, ?, ?, ?)
    """, (
        "Sebastian Salih",
        """Norsk gründer (31), BMW-entusiast, programvareutvikler.
Eier AS etablert 2023 med fokus på eventos, netthandel, og teknologiløsninger.
Spesialist innen BMW-diagnostikk, ECU-tuning, og kunstig intelligens.
Brenner for å bygge, automatisere, og innovere.""",
        """• Perfeksjonere OBDAI (BMW diagnose-system)
• Skalere Autovers.no til markedsleder
• Lage AutoSvar AI (intelligente kundesvar)
• Bygge sterkere NettsideFor (Instacall)
• Oppnå 6 timers søvn daglig
• Trene 4x per uke (styrke + kardio)
• Nettverke med innovatører og investorer""",
        "Europe/Oslo",
        "focused"
    ))

    # ════════════════════════════════════════════════
    # GOALS
    # ════════════════════════════════════════════════

    goals = [
        ("OBDAI Production Release", "Lanse OBDAI som kommersiell B2B diagnose-løsning", "tech", "2026-06-30", 45),
        ("Autovers 50k Revenue", "Nettbutikken skal generere €50k årlig", "business", "2026-12-31", 30),
        ("BMW MS45.1 Full Tuning Suite", "Komplett tuning-pakke for E60 M54", "automotive", "2026-08-31", 60),
        ("Health Baseline", "Etabler routine: 6h søvn, 4x trening, riktig ernæring", "health", "2026-03-31", 20),
        ("Event Portfolio Build", "Gjennomfør 3 large-scale events", "business", "2026-12-31", 10),
        ("AutoSvar AI Launch", "Integrer AI-kundesvar på alle plattformer", "tech", "2026-05-31", 25),
    ]

    for title, desc, cat, target, progress in goals:
        cursor.execute("""
            INSERT INTO goals (user_id, title, description, category, target_date, progress, status)
            VALUES (1, ?, ?, ?, ?, ?, 'active')
        """, (title, desc, cat, target, progress))

    # ════════════════════════════════════════════════
    # HABITS
    # ════════════════════════════════════════════════

    habits = [
        ("Morning Code Review", "tech", "daily", 12),
        ("BMW Diagnostics Session", "automotive", "4x/week", 8),
        ("Workout", "health", "4x/week", 5),
        ("Event Planning", "business", "3x/week", 4),
        ("Learn AI/ML Advancements", "tech", "3x/week", 6),
    ]

    for name, cat, freq, streak in habits:
        cursor.execute("""
            INSERT INTO habits (user_id, name, category, frequency, streak, last_completed)
            VALUES (1, ?, ?, ?, ?, datetime('now'))
        """, (name, cat, freq, streak))

    # ════════════════════════════════════════════════
    # CALENDAR EVENTS (Next 30 days)
    # ════════════════════════════════════════════════

    now = datetime.now()
    events = [
        ("OBDAI Code Sprint", "Work on live data streaming + RPM dashboard", "tech", now + timedelta(days=2)),
        ("Autovers Inventory Review", "Q1 stock analysis", "business", now + timedelta(days=3)),
        ("BMW Tuning Session", "MS45.1 torque curve optimization", "automotive", now + timedelta(days=5)),
        ("Event Planning Meeting", "Festival production kickoff", "business", now + timedelta(days=7)),
        ("Fitness Focus Week", "Full body strength training", "health", now + timedelta(days=1)),
        ("AutoSvar AI Integration", "Connect Claude API to website", "tech", now + timedelta(days=10)),
        ("BMW E60 Deep Dive", "Study ECU communication protocols", "automotive", now + timedelta(days=14)),
    ]

    for title, desc, cat, start in events:
        cursor.execute("""
            INSERT INTO calendar_events (user_id, title, description, start_time, category)
            VALUES (1, ?, ?, ?, ?)
        """, (title, desc, start.isoformat(), cat))

    # ════════════════════════════════════════════════
    # LIFESTYLE DATA (Last 7 days)
    # ════════════════════════════════════════════════

    for i in range(7):
        date = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        cursor.execute("""
            INSERT INTO lifestyle_data (user_id, date, sleep_hours, exercise_minutes, water_intake, mood_rating, energy_rating, notes)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date,
            5.5 + (i % 3) * 0.5,  # 5.5-6.5 hours
            45 + (i % 2) * 30,     # 45-75 minutes
            6 + (i % 3),           # 6-8 glasses
            7 + (i % 3),           # 7-9 mood
            75 + (i % 2) * 10,     # 75-85% energy
            f"Day {i}: Working on OBDAI & Autovers"
        ))

    conn.commit()
    conn.close()
    print("✅ Sebastian Salih's profile initialized!")
    print("   • 6 major goals loaded")
    print("   • 5 core habits set")
    print("   • 7 events scheduled")
    print("   • 7 days lifestyle data")
    print("\n🚀 MONIR is ready to know Sebastian!")

if __name__ == "__main__":
    init_sebastian()
