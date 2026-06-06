-- MONIR Life Operating System v3.0

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  bio TEXT,
  goals TEXT,
  city TEXT DEFAULT 'Oslo',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS character_stats (
  user_id INTEGER PRIMARY KEY,
  level INTEGER DEFAULT 1,
  xp INTEGER DEFAULT 0,
  xp_next INTEGER DEFAULT 1000,
  discipline INTEGER DEFAULT 50,
  intelligence INTEGER DEFAULT 50,
  health INTEGER DEFAULT 50,
  business_score INTEGER DEFAULT 50,
  rep_builder INTEGER DEFAULT 2,
  rep_tech INTEGER DEFAULT 2,
  rep_entrepreneur INTEGER DEFAULT 2,
  rep_athlete INTEGER DEFAULT 2,
  rep_leader INTEGER DEFAULT 2,
  main_quest TEXT DEFAULT 'Define your life quest',
  main_quest_progress INTEGER DEFAULT 0,
  height_cm INTEGER,
  weight_kg REAL,
  age INTEGER DEFAULT 0,
  net_worth_trend TEXT DEFAULT '+0%',
  onboarded INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS assets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  category TEXT DEFAULT 'general',
  emoji TEXT DEFAULT '📦',
  status TEXT DEFAULT 'locked',
  description TEXT,
  sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS businesses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  level INTEGER DEFAULT 1,
  value_stars INTEGER DEFAULT 3,
  revenue_stars INTEGER DEFAULT 3,
  complexity_stars INTEGER DEFAULT 3,
  next_action TEXT,
  status TEXT DEFAULT 'active',
  sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS vehicles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  model_detail TEXT,
  condition_pct INTEGER DEFAULT 80,
  notes TEXT,
  sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS quests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  title TEXT NOT NULL,
  completed INTEGER DEFAULT 0,
  xp_reward INTEGER DEFAULT 100,
  sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS achievements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  emoji TEXT DEFAULT '🏆',
  unlocked INTEGER DEFAULT 0,
  xp_reward INTEGER DEFAULT 200,
  sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS habits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  emoji TEXT DEFAULT '⚡',
  frequency TEXT DEFAULT 'DAGLIG',
  xp_reward INTEGER DEFAULT 20,
  streak INTEGER DEFAULT 0,
  last_completed TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS habit_completions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  habit_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lifestyle_data (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  date TEXT NOT NULL,
  sleep_hours REAL,
  exercise_minutes INTEGER,
  water_intake INTEGER,
  mood_rating INTEGER,
  energy_rating INTEGER,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS chat_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS memory_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  category TEXT DEFAULT 'general',
  note TEXT NOT NULL,
  source TEXT DEFAULT 'manual',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS goals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  category TEXT,
  target_date DATE,
  progress INTEGER DEFAULT 0,
  status TEXT DEFAULT 'active',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
