-- ═══════════════════════════════════════════════════
-- KING Supabase Schema
-- Run this entire file in Supabase SQL Editor
-- Project: Dashboard → SQL Editor → New Query → paste → Run
-- ═══════════════════════════════════════════════════

-- ── Conversation History ─────────────────────────────
CREATE TABLE IF NOT EXISTS conversation_history (
    id          BIGSERIAL PRIMARY KEY,
    role        TEXT NOT NULL CHECK (role IN ('user', 'king')),
    content     TEXT NOT NULL,
    lang        TEXT NOT NULL DEFAULT 'en',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── User Memory ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_memory (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Reminders ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reminders (
    id          BIGSERIAL PRIMARY KEY,
    text        TEXT NOT NULL,
    remind_at   TIMESTAMPTZ NOT NULL,
    done        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Notes ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notes (
    id          BIGSERIAL PRIMARY KEY,
    title       TEXT,
    content     TEXT NOT NULL,
    tags        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Ego State ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ego_state (
    id          INTEGER PRIMARY KEY DEFAULT 1,
    mood        TEXT NOT NULL DEFAULT 'dormant',
    counter     INTEGER NOT NULL DEFAULT 0,
    threshold   INTEGER NOT NULL DEFAULT 10,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT single_row CHECK (id = 1)
);

INSERT INTO ego_state (id, mood, counter, threshold)
VALUES (1, 'dormant', 0, 10)
ON CONFLICT (id) DO NOTHING;

-- ── Master Mission ────────────────────────────────────
CREATE TABLE IF NOT EXISTS master_mission (
    id                  BIGSERIAL PRIMARY KEY,
    mission_statement   TEXT,
    declared_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    standards           JSONB DEFAULT '[]',
    non_negotiables     JSONB DEFAULT '[]',
    current_phase       TEXT,
    last_reviewed       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Chronicle Entries ─────────────────────────────────
CREATE TABLE IF NOT EXISTS chronicle_entries (
    id          BIGSERIAL PRIMARY KEY,
    type        TEXT NOT NULL CHECK (type IN (
                    'ARC_START','ARC_END','VICTORY','FAILURE',
                    'PATTERN','MILESTONE','REVELATION','MYTHOLOGY'
                )),
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    arc_name    TEXT,
    title       TEXT,
    content     TEXT NOT NULL,
    emotion_tag TEXT,
    significance INTEGER NOT NULL DEFAULT 5
                CHECK (significance BETWEEN 1 AND 10),
    pattern_tag TEXT
);

-- ── Arcs ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS arcs (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at    TIMESTAMPTZ,
    outcome     TEXT,
    summary     TEXT
);

-- ── Mythology ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mythology (
    id          BIGSERIAL PRIMARY KEY,
    entry_id    BIGINT REFERENCES chronicle_entries(id),
    title       TEXT NOT NULL,
    summary     TEXT NOT NULL,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Pattern Library ───────────────────────────────────
CREATE TABLE IF NOT EXISTS pattern_library (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    first_seen  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    frequency   INTEGER NOT NULL DEFAULT 1,
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status      TEXT NOT NULL DEFAULT 'active'
);

-- ── Instinct Patterns ─────────────────────────────────
CREATE TABLE IF NOT EXISTS instinct_patterns (
    id                  BIGSERIAL PRIMARY KEY,
    pattern_name        TEXT NOT NULL UNIQUE,
    trigger_description TEXT NOT NULL,
    confidence          REAL NOT NULL DEFAULT 0.5,
    times_detected      INTEGER NOT NULL DEFAULT 1,
    last_triggered      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── State History ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS state_history (
    id              BIGSERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    detected_state  TEXT NOT NULL,
    signals         JSONB DEFAULT '{}'
);

-- ── Danger Flags ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS danger_flags (
    id          BIGSERIAL PRIMARY KEY,
    flag_type   TEXT NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved    BOOLEAN NOT NULL DEFAULT FALSE,
    context     TEXT
);

-- ── Indexes ───────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_conv_created
    ON conversation_history (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_reminders_remind_at
    ON reminders (remind_at) WHERE done = FALSE;

CREATE INDEX IF NOT EXISTS idx_chronicle_timestamp
    ON chronicle_entries (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_pattern_freq
    ON pattern_library (frequency DESC);

-- ── Row Level Security (disable for private use) ──────
-- KING is single-user. RLS disabled for simplicity.
-- If you want to enable it, add policies using the anon key.

ALTER TABLE conversation_history DISABLE ROW LEVEL SECURITY;
ALTER TABLE user_memory DISABLE ROW LEVEL SECURITY;
ALTER TABLE reminders DISABLE ROW LEVEL SECURITY;
ALTER TABLE notes DISABLE ROW LEVEL SECURITY;
ALTER TABLE ego_state DISABLE ROW LEVEL SECURITY;
ALTER TABLE master_mission DISABLE ROW LEVEL SECURITY;
ALTER TABLE chronicle_entries DISABLE ROW LEVEL SECURITY;
ALTER TABLE arcs DISABLE ROW LEVEL SECURITY;
ALTER TABLE mythology DISABLE ROW LEVEL SECURITY;
ALTER TABLE pattern_library DISABLE ROW LEVEL SECURITY;
ALTER TABLE instinct_patterns DISABLE ROW LEVEL SECURITY;
ALTER TABLE state_history DISABLE ROW LEVEL SECURITY;
ALTER TABLE danger_flags DISABLE ROW LEVEL SECURITY;
