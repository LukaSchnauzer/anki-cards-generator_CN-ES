-- ChinoSRS SQLite schema
-- Unidad de generación: palabra × tipo de tarjeta (sentence/pattern/audio).
-- Cada tarjeta tiene UNA oración (o una por lectura, si la palabra es polífona).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS words (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    hanzi                 TEXT NOT NULL,
    traditional           TEXT,
    radical               TEXT,
    hsk_level             INTEGER,
    export_level          INTEGER,               -- override de a qué mazo/modelo exportar (NULL = usar hsk_level). El chip visible en la tarjeta SIEMPRE usa hsk_level, nunca esto — ver export.py
    word_prep_status      TEXT NOT NULL DEFAULT 'pending',  -- pending|failed|needs_human — mismo mecanismo de tope que cards.review_status, pero a nivel palabra (word_prep no genera tarjetas)
    word_prep_attempts    INTEGER NOT NULL DEFAULT 0,       -- rondas de regenerate_word_prep fallidas consecutivas desde el último éxito
    hsk_standard          TEXT,                  -- 'new' | 'old'
    frequency_rank        INTEGER,
    pos_json              TEXT,                  -- JSON list, ej. ["nz"]
    source_meanings_json  TEXT,                  -- meanings crudos de complete.json, para auditoría
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (hanzi, hsk_level)
);

CREATE TABLE IF NOT EXISTS readings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id       INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    pinyin        TEXT NOT NULL,
    is_primary    INTEGER NOT NULL DEFAULT 0,     -- 1 = pronunciación más común
    meaning_es    TEXT,
    meaning_zh    TEXT,
    register      TEXT,                           -- reg:colloquial | reg:neutral | reg:formal | reg:literary
    tags_seed     TEXT,                            -- tags gramaticales, separados por ';'
    source        TEXT NOT NULL DEFAULT 'seed' CHECK (source IN ('seed', 'llm')),  -- 'seed' = sin verificar (viene del JSON fuente), 'llm' = generado/corregido
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS collocations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id     INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    pattern_zh  TEXT NOT NULL,                    -- ej. "推 + 门"
    gloss_es    TEXT,
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cards (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id        INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    card_type      TEXT NOT NULL CHECK (card_type IN ('sentence', 'pattern', 'audio')),
    status         TEXT NOT NULL DEFAULT 'pending',        -- pending|generated|guardrail_failed|guardrail_passed|ready
    review_status  TEXT NOT NULL DEFAULT 'pending',        -- pending|flagged_bad|needs_human (needs_human = agotó el tope de regenerate --flagged, requiere intervención)
    review_notes   TEXT,
    regen_attempts INTEGER NOT NULL DEFAULT 0,             -- rondas de regenerate_card fallidas consecutivas desde el último éxito
    anki_note_id   INTEGER,                                -- noteId de AnkiConnect una vez exportada (NULL = nunca exportada)
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (word_id, card_type)
);

CREATE TABLE IF NOT EXISTS card_examples (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id          INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    reading_id       INTEGER REFERENCES readings(id) ON DELETE SET NULL,
    example_zh       TEXT NOT NULL,
    example_es       TEXT NOT NULL,
    example_pinyin   TEXT,                        -- pinyin completo de la oración
    -- breakdown_json: [{"hanzi":..,"pinyin":..,"grammar_role":..,"meaning":..,"usage_note":..|null}, ...]
    breakdown_json   TEXT,
    grammar_notes    TEXT,                        -- JSON: string[] con notas de estructura gramatical de la oración (colapsable, junto al desglose)
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audio_files (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    scope            TEXT NOT NULL CHECK (scope IN ('word', 'sentence')),
    reading_id       INTEGER REFERENCES readings(id) ON DELETE CASCADE,        -- scope='word'
    card_example_id  INTEGER REFERENCES card_examples(id) ON DELETE CASCADE,   -- scope='sentence'
    speed            TEXT NOT NULL DEFAULT 'normal' CHECK (speed IN ('normal', 'slow')),
    engine           TEXT NOT NULL,                -- gtts | azure | elevenlabs
    file_path        TEXT NOT NULL,
    alignment_json   TEXT,                         -- alineación por carácter de ElevenLabs (characters + start/end), NULL si el motor no la da
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (
        (scope = 'word' AND reading_id IS NOT NULL AND card_example_id IS NULL) OR
        (scope = 'sentence' AND card_example_id IS NOT NULL AND reading_id IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS generation_phases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id     INTEGER REFERENCES words(id) ON DELETE CASCADE,   -- para fases a nivel de palabra (ej. word_prep)
    card_id     INTEGER REFERENCES cards(id) ON DELETE CASCADE,   -- para fases a nivel de tarjeta (ej. draft, guardrail)
    phase       TEXT NOT NULL,                     -- ej. word_prep | draft | guardrail | audio | breakdown
    status      TEXT NOT NULL DEFAULT 'pending',    -- pending|running|passed|failed
    attempt     INTEGER NOT NULL DEFAULT 1,
    notes       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK ((word_id IS NOT NULL) != (card_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_readings_word_id ON readings(word_id);
CREATE INDEX IF NOT EXISTS idx_collocations_word_id ON collocations(word_id);
CREATE INDEX IF NOT EXISTS idx_cards_word_id ON cards(word_id);
CREATE INDEX IF NOT EXISTS idx_cards_status ON cards(status);
CREATE INDEX IF NOT EXISTS idx_cards_review_status ON cards(review_status);
CREATE INDEX IF NOT EXISTS idx_card_examples_card_id ON card_examples(card_id);
CREATE INDEX IF NOT EXISTS idx_audio_files_reading_id ON audio_files(reading_id);
CREATE INDEX IF NOT EXISTS idx_audio_files_card_example_id ON audio_files(card_example_id);
CREATE INDEX IF NOT EXISTS idx_generation_phases_card_id ON generation_phases(card_id);
CREATE INDEX IF NOT EXISTS idx_generation_phases_word_id ON generation_phases(word_id);
