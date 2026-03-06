CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    age INTEGER NOT NULL,
    diagnosis TEXT NOT NULL,
    treatment TEXT NOT NULL,
    medical_notes TEXT NOT NULL,
    consultation_date TEXT NOT NULL,
    ai_summary_cache TEXT,
    ai_summary_fingerprint TEXT,
    ai_summary_model TEXT,
    ai_summary_cached_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
