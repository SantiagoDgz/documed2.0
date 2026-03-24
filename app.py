from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, flash, g, redirect, render_template, request, session, url_for

BASE_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BASE_DIR / "database"
DATABASE_PATH = DATABASE_DIR / "patients.db"
KNOWLEDGE_DIR = BASE_DIR / "knowledge"

SEARCH_STOPWORDS = {
    "para",
    "como",
    "este",
    "esta",
    "estos",
    "estas",
    "sobre",
    "desde",
    "entre",
    "donde",
    "cuando",
    "porque",
    "puede",
    "pueden",
    "debe",
    "deben",
    "solo",
    "general",
    "clinico",
    "clinica",
    "riesgo",
    "paciente",
    "tratamiento",
    "consulta",
}

LAB_PANEL_SECTIONS: list[dict[str, Any]] = [
    {
        "title": "Hemograma",
        "fields": [
            {
                "id": "glucosa",
                "name": "Glucosa",
                "unit": "mg/dL",
                "reference": "70-100",
                "placeholder": "Ej: 95",
            },
            {
                "id": "hemoglobina",
                "name": "Hemoglobina",
                "unit": "g/dL",
                "reference": "12-17.5",
                "placeholder": "Ej: 14.5",
            },
            {
                "id": "hematocrito",
                "name": "Hematocrito",
                "unit": "%",
                "reference": "36-46",
                "placeholder": "Ej: 42",
            },
        ],
    },
    {
        "title": "Funcion Renal",
        "fields": [
            {
                "id": "creatinina",
                "name": "Creatinina",
                "unit": "mg/dL",
                "reference": "0.7-1.3",
                "placeholder": "Ej: 1.0",
            },
            {
                "id": "sodio",
                "name": "Sodio",
                "unit": "mEq/L",
                "reference": "136-145",
                "placeholder": "Ej: 140",
            },
            {
                "id": "potasio",
                "name": "Potasio",
                "unit": "mEq/L",
                "reference": "3.5-5",
                "placeholder": "Ej: 4.2",
            },
        ],
    },
    {
        "title": "Presion Arterial",
        "fields": [
            {
                "id": "presion_sistolica",
                "name": "P. Sistolica",
                "unit": "mmHg",
                "reference": "90-120",
                "placeholder": "Ej: 110",
            },
            {
                "id": "presion_diastolica",
                "name": "P. Diastolica",
                "unit": "mmHg",
                "reference": "60-80",
                "placeholder": "Ej: 70",
            },
        ],
    },
    {
        "title": "Perfil Lipidico",
        "fields": [
            {
                "id": "colesterol_total",
                "name": "Colesterol Total",
                "unit": "mg/dL",
                "reference": "<200",
                "placeholder": "Ej: 180",
            },
            {
                "id": "trigliceridos",
                "name": "Trigliceridos",
                "unit": "mg/dL",
                "reference": "<150",
                "placeholder": "Ej: 120",
            },
            {
                "id": "hdl",
                "name": "HDL",
                "unit": "mg/dL",
                "reference": ">40",
                "placeholder": "Ej: 50",
            },
            {
                "id": "ldl",
                "name": "LDL",
                "unit": "mg/dL",
                "reference": "<100",
                "placeholder": "Ej: 90",
            },
        ],
    },
    {
        "title": "Funcion Hepatica",
        "fields": [
            {
                "id": "bilirrubina",
                "name": "Bilirrubina",
                "unit": "mg/dL",
                "reference": "0.2-1.3",
                "placeholder": "Ej: 0.8",
            },
            {
                "id": "ast",
                "name": "AST",
                "unit": "U/L",
                "reference": "10-40",
                "placeholder": "Ej: 30",
            },
            {
                "id": "alt",
                "name": "ALT",
                "unit": "U/L",
                "reference": "7-56",
                "placeholder": "Ej: 28",
            },
            {
                "id": "albumina",
                "name": "Albumina",
                "unit": "g/dL",
                "reference": "3.5-5",
                "placeholder": "Ej: 4.2",
            },
        ],
    },
    {
        "title": "Minerales",
        "fields": [
            {
                "id": "calcio",
                "name": "Calcio",
                "unit": "mg/dL",
                "reference": "8.5-10.2",
                "placeholder": "Ej: 9.2",
            },
            {
                "id": "fosforo",
                "name": "Fosforo",
                "unit": "mg/dL",
                "reference": "2.5-4.5",
                "placeholder": "Ej: 3.5",
            },
        ],
    },
]

LAB_PANEL_FIELDS = {
    field["id"]: field
    for section in LAB_PANEL_SECTIONS
    for field in section["fields"]
}

knowledge_cache: dict[str, Any] = {
    "signature": None,
    "chunks": [],
}

disease_catalog_cache: dict[str, Any] = {
    "signature": None,
    "entries": [],
}

load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "documed-dev-key")
app.config["DATABASE"] = str(DATABASE_PATH)
app.config["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY") or os.getenv("XAI_API_KEY", "")
app.config["GROQ_MODEL"] = os.getenv("GROQ_MODEL", "")
app.config["GROQ_PROVIDER"] = os.getenv("GROQ_PROVIDER", "auto")


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_: Any) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(app.config["DATABASE"])
    db.execute(
        """
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
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS laboratory_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            test_name TEXT NOT NULL,
            result_value TEXT NOT NULL,
            units TEXT,
            reference_range TEXT,
            interpretation_notes TEXT,
            lab_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS prescriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            medication TEXT NOT NULL,
            presentation TEXT,
            dosage TEXT NOT NULL,
            frequency TEXT NOT NULL,
            duration TEXT NOT NULL,
            instructions TEXT NOT NULL,
            prescription_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS health_trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            metric_type TEXT NOT NULL,
            value REAL NOT NULL,
            unit TEXT NOT NULL,
            measurement_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        )
        """
    )

    # Lightweight migration for existing databases created before cache columns.
    columns = {
        row[1]
        for row in db.execute("PRAGMA table_info(patients)").fetchall()
    }
    migration_columns = {
        "ai_summary_cache": "TEXT",
        "ai_summary_fingerprint": "TEXT",
        "ai_summary_model": "TEXT",
        "ai_summary_cached_at": "TEXT",
    }
    for column_name, column_type in migration_columns.items():
        if column_name not in columns:
            db.execute(f"ALTER TABLE patients ADD COLUMN {column_name} {column_type}")

    db.commit()
    db.close()


def parse_patient_form(form: dict[str, str]) -> dict[str, Any]:
    name = form.get("name", "").strip()
    age_raw = form.get("age", "").strip()
    diagnosis = form.get("diagnosis", "").strip()
    treatment = form.get("treatment", "").strip()
    medical_notes = form.get("medical_notes", "").strip()
    consultation_date = form.get("consultation_date", "").strip()

    errors: list[str] = []

    if not name:
        errors.append("El nombre del paciente es obligatorio.")

    try:
        age = int(age_raw)
        if age < 0 or age > 120:
            errors.append("La edad debe estar entre 0 y 120.")
    except ValueError:
        age = -1
        errors.append("La edad debe ser un numero valido.")

    if not diagnosis:
        errors.append("El diagnostico es obligatorio.")
    if not treatment:
        errors.append("El tratamiento es obligatorio.")
    if not medical_notes:
        errors.append("Las notas medicas son obligatorias.")

    if not consultation_date:
        errors.append("La fecha de consulta es obligatoria.")
    else:
        try:
            datetime.strptime(consultation_date, "%Y-%m-%d")
        except ValueError:
            errors.append("La fecha de consulta no tiene un formato valido.")

    return {
        "data": {
            "name": name,
            "age": age,
            "diagnosis": diagnosis,
            "treatment": treatment,
            "medical_notes": medical_notes,
            "consultation_date": consultation_date,
        },
        "errors": errors,
    }


def parse_laboratory_form(form: Any) -> dict[str, Any]:
    patient_id_raw = form.get("patient_id", "").strip()
    custom_test_name = form.get("custom_test_name", "").strip()
    custom_result_value = form.get("custom_result_value", "").strip()
    custom_units = form.get("custom_units", "").strip()
    custom_reference_range = form.get("custom_reference_range", "").strip()
    interpretation_notes = form.get("interpretation_notes", "").strip()
    lab_date = form.get("lab_date", "").strip()

    errors: list[str] = []

    try:
        patient_id = int(patient_id_raw)
        if patient_id <= 0:
            errors.append("Paciente invalido para el analisis.")
    except ValueError:
        patient_id = -1
        errors.append("Debes seleccionar un paciente valido.")

    lab_entries: list[dict[str, str]] = []
    for field in LAB_PANEL_FIELDS.values():
        value = form.get(f"lab_{field['id']}", "").strip()
        if not value:
            continue
        lab_entries.append(
            {
                "test_name": field["name"],
                "result_value": value,
                "units": field["unit"],
                "reference_range": field["reference"],
            }
        )

    if custom_test_name and custom_result_value:
        lab_entries.append(
            {
                "test_name": custom_test_name,
                "result_value": custom_result_value,
                "units": custom_units,
                "reference_range": custom_reference_range,
            }
        )
    elif custom_test_name and not custom_result_value:
        errors.append("Si agregas otro analisis, tambien debes escribir su resultado.")

    if not lab_entries:
        errors.append("Ingresa al menos un resultado de laboratorio.")

    if not lab_date:
        errors.append("La fecha de laboratorio es obligatoria.")
    else:
        try:
            datetime.strptime(lab_date, "%Y-%m-%d")
        except ValueError:
            errors.append("La fecha del laboratorio no tiene formato valido.")

    return {
        "data": {
            "patient_id": patient_id,
            "lab_entries": lab_entries,
            "custom_test_name": custom_test_name,
            "interpretation_notes": interpretation_notes,
            "lab_date": lab_date,
        },
        "errors": errors,
    }


def parse_prescription_form(form: dict[str, str]) -> dict[str, Any]:
    patient_id_raw = form.get("patient_id", "").strip()
    medication = form.get("medication", "").strip()
    presentation = form.get("presentation", "").strip()
    dosage = form.get("dosage", "").strip()
    frequency = form.get("frequency", "").strip()
    duration = form.get("duration", "").strip()
    instructions = form.get("instructions", "").strip()
    prescription_date = form.get("prescription_date", "").strip()

    errors: list[str] = []

    try:
        patient_id = int(patient_id_raw)
        if patient_id <= 0:
            errors.append("Paciente invalido para la receta.")
    except ValueError:
        patient_id = -1
        errors.append("Debes seleccionar un paciente valido.")

    if not medication:
        errors.append("El medicamento es obligatorio.")
    if not dosage:
        errors.append("La dosis es obligatoria.")
    if not frequency:
        errors.append("La frecuencia es obligatoria.")
    if not duration:
        errors.append("La duracion es obligatoria.")
    if not instructions:
        errors.append("Las indicaciones son obligatorias.")
    if not prescription_date:
        errors.append("La fecha de receta es obligatoria.")
    else:
        try:
            datetime.strptime(prescription_date, "%Y-%m-%d")
        except ValueError:
            errors.append("La fecha de receta no tiene formato valido.")

    return {
        "data": {
            "patient_id": patient_id,
            "medication": medication,
            "presentation": presentation,
            "dosage": dosage,
            "frequency": frequency,
            "duration": duration,
            "instructions": instructions,
            "prescription_date": prescription_date,
        },
        "errors": errors,
    }


def parse_reference_range(range_text: str) -> tuple[float, float] | None:
    cleaned = normalize_text(range_text).replace(",", ".")
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*[-a]\s*(-?\d+(?:\.\d+)?)", cleaned)
    if not match:
        return None

    low = float(match.group(1))
    high = float(match.group(2))
    if low > high:
        low, high = high, low
    return (low, high)


def analyze_lab_result(lab_row: sqlite3.Row) -> tuple[str, str]:
    result_raw = str(lab_row["result_value"])
    range_raw = str(lab_row["reference_range"] or "")
    parsed_range = parse_reference_range(range_raw)

    numeric_match = re.search(r"-?\d+(?:[\.,]\d+)?", result_raw)
    if not numeric_match or parsed_range is None:
        return (
            "No cuantificable",
            "Resultado o rango de referencia no numerico. Requiere interpretacion clinica directa.",
        )

    value = float(numeric_match.group(0).replace(",", "."))
    low, high = parsed_range

    if value < low:
        return (
            "Fuera de rango (bajo)",
            f"Valor {value} por debajo del rango de referencia ({low}-{high}).",
        )
    if value > high:
        return (
            "Fuera de rango (alto)",
            f"Valor {value} por encima del rango de referencia ({low}-{high}).",
        )
    return (
        "En rango",
        f"Valor {value} dentro del rango de referencia ({low}-{high}).",
    )


def build_lab_summary_prompt(lab_row: sqlite3.Row, patient_name: str) -> str:
    status, range_note = analyze_lab_result(lab_row)
    return (
        "Resume este analisis de laboratorio para personal medico en maximo 6 lineas. "
        "No des diagnostico definitivo ni tratamiento farmacologico obligatorio. "
        "Incluye: hallazgo principal, posible riesgo orientativo y recomendacion de seguimiento.\n\n"
        f"Paciente: {patient_name}\n"
        f"Estudio: {lab_row['test_name']}\n"
        f"Resultado: {lab_row['result_value']} {lab_row['units'] or ''}\n"
        f"Rango de referencia: {lab_row['reference_range'] or 'No informado'}\n"
        f"Interpretacion base automatica: {status} | {range_note}\n"
        f"Notas del laboratorio: {lab_row['interpretation_notes'] or 'Sin notas adicionales.'}"
    )


def summarize_lab_with_ai(lab_row: sqlite3.Row, patient_name: str) -> tuple[str, str]:
    prompt = build_lab_summary_prompt(lab_row, patient_name)
    messages = [
        {
            "role": "system",
            "content": (
                "Eres un asistente clinico para analisis de laboratorios. "
                "Solo apoyo orientativo para personal medico. "
                "No emitas diagnostico definitivo ni receta."
            ),
        },
        {
            "role": "user",
            "content": prompt,
        },
    ]
    content, status = call_llm_chat(messages, max_tokens=300, temperature=0.2)

    if content:
        return content, status

    fallback_status, fallback_note = analyze_lab_result(lab_row)
    fallback = (
        f"Resumen local de laboratorio ({fallback_status}).\n"
        f"Paciente: {patient_name}.\n"
        f"Estudio: {lab_row['test_name']} - Resultado: {lab_row['result_value']} {lab_row['units'] or ''}.\n"
        f"Rango: {lab_row['reference_range'] or 'No informado'}.\n"
        f"Interpretacion orientativa: {fallback_note}\n"
        "Sugerencia: correlacionar con cuadro clinico, repetir o ampliar estudios segun criterio medico."
    )
    return fallback, f"{status} | Fallback local de laboratorio"


def build_patient_lab_summary_prompt(
    lab_rows: list[sqlite3.Row],
    patient_name: str,
    lab_date: str,
    chat_question: str,
) -> str:
    lines: list[str] = []
    for row in lab_rows:
        status, range_note = analyze_lab_result(row)
        lines.append(
            f"- {row['test_name']}: {row['result_value']} {row['units'] or ''} | "
            f"Rango: {row['reference_range'] or 'No informado'} | "
            f"Interpretacion: {status} ({range_note})"
        )

    compact_results = "\n".join(lines)
    return (
        "Analiza en conjunto este panel de laboratorio para personal medico. "
        "No des diagnostico definitivo ni tratamiento farmacologico. "
        "Responde en maximo 10 lineas con: hallazgos globales, parametros alterados, "
        "riesgo orientativo y sugerencia de seguimiento.\n\n"
        f"Paciente: {patient_name}\n"
        f"Fecha de laboratorio: {lab_date}\n"
        f"Cantidad de parametros: {len(lab_rows)}\n"
        f"Consulta del medico: {chat_question}\n\n"
        "Resultados:\n"
        f"{compact_results}"
    )


def summarize_patient_labs_with_ai(
    lab_rows: list[sqlite3.Row],
    patient_name: str,
    lab_date: str,
    chat_question: str,
) -> tuple[str, str]:
    prompt = build_patient_lab_summary_prompt(lab_rows, patient_name, lab_date, chat_question)
    messages = [
        {
            "role": "system",
            "content": (
                "Eres un asistente clinico para analisis de laboratorios. "
                "Solo apoyo orientativo para personal medico. "
                "No emitas diagnostico definitivo ni receta."
            ),
        },
        {
            "role": "user",
            "content": prompt,
        },
    ]
    content, status = call_llm_chat(messages, max_tokens=500, temperature=0.2)

    if content:
        return content, status

    high_flags: list[str] = []
    low_flags: list[str] = []
    in_range = 0
    not_quantifiable = 0

    for row in lab_rows:
        row_status, row_note = analyze_lab_result(row)
        if row_status == "Fuera de rango (alto)":
            high_flags.append(f"{row['test_name']}: {row['result_value']} ({row_note})")
        elif row_status == "Fuera de rango (bajo)":
            low_flags.append(f"{row['test_name']}: {row['result_value']} ({row_note})")
        elif row_status == "En rango":
            in_range += 1
        else:
            not_quantifiable += 1

    fallback_lines = [
        "Resumen local de panel de laboratorio (paciente completo).",
        f"Paciente: {patient_name}.",
        f"Fecha evaluada: {lab_date}.",
        f"Parametros evaluados: {len(lab_rows)} (en rango: {in_range}, no cuantificables: {not_quantifiable}).",
    ]

    if high_flags:
        fallback_lines.append("Alteraciones elevadas:")
        fallback_lines.extend(f"- {item}" for item in high_flags[:6])
    if low_flags:
        fallback_lines.append("Alteraciones disminuidas:")
        fallback_lines.extend(f"- {item}" for item in low_flags[:6])
    if not high_flags and not low_flags:
        fallback_lines.append("No se detectaron alteraciones numericas fuera de rango en este panel.")

    fallback_lines.append(
        "Sugerencia: correlacionar con cuadro clinico y definir seguimiento segun criterio medico."
    )

    fallback = "\n".join(fallback_lines)
    return fallback, f"{status} | Fallback local de panel"


def summarize_notes(notes: str) -> str:
    cleaned = " ".join(notes.split())
    if len(cleaned) <= 160:
        return cleaned
    return f"{cleaned[:157]}..."


def detect_llm_provider() -> str:
    preferred = normalize_text(app.config.get("GROQ_PROVIDER", "auto"))
    if preferred in {"xai", "groq"}:
        return preferred

    api_key = app.config["GROQ_API_KEY"].strip()
    if api_key.startswith("gsk_"):
        return "groq"
    return "xai"


def get_model_candidates() -> list[str]:
    provider = detect_llm_provider()
    preferred_model = app.config.get("GROK_MODEL", "").strip()

    if provider == "groq":
        defaults = [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
        ]
    else:
        defaults = [
            "grok-3-mini",
            "grok-3-beta",
            "grok-2-latest",
        ]

    models = [preferred_model] + defaults if preferred_model else defaults
    deduped: list[str] = []
    for model in models:
        if model and model not in deduped:
            deduped.append(model)
    return deduped


def call_llm_chat(
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
) -> tuple[str | None, str]:
    api_key = app.config["GROQ_API_KEY"].strip()
    if not api_key:
        return None, "API key no configurada"

    provider = detect_llm_provider()
    endpoint = (
        "https://api.groq.com/openai/v1/chat/completions"
        if provider == "groq"
        else "https://api.x.ai/v1/chat/completions"
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error = f"No se pudo completar la llamada ({provider})."
    for model in get_model_candidates():
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            response = requests.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=25,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
            if content:
                return content, f"LLM activo: {provider} ({model})"
        except requests.RequestException as exc:
            detail = ""
            if getattr(exc, "response", None) is not None:
                try:
                    detail = exc.response.text[:220]
                except Exception:
                    detail = ""
            last_error = f"Fallo {provider}/{model}: {detail or str(exc)}"
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            last_error = f"Respuesta invalida de {provider}/{model}: {exc}"

    return None, last_error


def summarize_with_grok(notes: str) -> str | None:
    prompt = (
        "Resume el siguiente texto clinico en maximo 2 lineas, "
        "en espanol y con foco medico practico para seguimiento:\n\n"
        f"{notes}"
    )
    messages = [
        {
            "role": "system",
            "content": "Eres un asistente clinico para resumen medico breve.",
        },
        {
            "role": "user",
            "content": prompt,
        },
    ]
    content, _status = call_llm_chat(messages, max_tokens=160, temperature=0.2)
    return content


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_text.lower().split())


def tokenize_for_search(text: str) -> set[str]:
    normalized = normalize_text(text)
    raw_tokens = re.split(r"[^a-z0-9]+", normalized)
    return {
        token
        for token in raw_tokens
        if len(token) >= 3 and token not in SEARCH_STOPWORDS
    }


def build_knowledge_chunks(content: str, source: str) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    current_title = "Guia general"

    for block in content.split("\n\n"):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        if lines[0].startswith("#"):
            current_title = lines[0].lstrip("# ").strip() or current_title
            lines = lines[1:]
            if not lines:
                continue

        text = " ".join(lines)
        if len(text) < 50:
            continue

        chunks.append(
            {
                "source": source,
                "title": current_title,
                "text": text,
                "tokens": tokenize_for_search(text),
            }
        )

    return chunks


def get_knowledge_chunks() -> list[dict[str, Any]]:
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(
        [
            path
            for path in KNOWLEDGE_DIR.iterdir()
            if path.is_file() and path.suffix.lower() in {".md", ".txt"}
        ],
        key=lambda item: item.name.lower(),
    )

    signature = tuple((path.name, path.stat().st_mtime_ns, path.stat().st_size) for path in files)
    if knowledge_cache["signature"] == signature:
        return knowledge_cache["chunks"]

    all_chunks: list[dict[str, Any]] = []
    for file_path in files:
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError:
            continue
        all_chunks.extend(build_knowledge_chunks(content, file_path.name))

    knowledge_cache["signature"] = signature
    knowledge_cache["chunks"] = all_chunks
    return all_chunks


def get_disease_catalog_entries() -> list[dict[str, str]]:
    catalog_path = KNOWLEDGE_DIR / "disease_risk_catalog.txt"
    if not catalog_path.exists():
        return []

    stat = catalog_path.stat()
    signature = (catalog_path.name, stat.st_mtime_ns, stat.st_size)
    if disease_catalog_cache["signature"] == signature:
        return disease_catalog_cache["entries"]

    entries: list[dict[str, str]] = []
    try:
        content = catalog_path.read_text(encoding="utf-8")
    except OSError:
        return []

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 2:
            continue

        term = normalize_text(parts[0])
        level = normalize_text(parts[1])
        note = parts[2].strip() if len(parts) >= 3 else ""

        if not term or level not in {"alto", "medio", "bajo"}:
            continue

        entries.append({"term": term, "level": level, "note": note})

    disease_catalog_cache["signature"] = signature
    disease_catalog_cache["entries"] = entries
    return entries


def find_catalog_matches(text: str) -> list[dict[str, str]]:
    text_tokens = tokenize_for_search(text)
    matches: list[dict[str, str]] = []

    for entry in get_disease_catalog_entries():
        term = entry["term"]
        term_tokens = tokenize_for_search(term)

        if term in text:
            matches.append(entry)
            continue

        if not term_tokens:
            continue

        overlap = term_tokens.intersection(text_tokens)
        overlap_ratio = len(overlap) / max(len(term_tokens), 1)

        # Flexible matching for diagnosis variants and word-order differences.
        if overlap_ratio >= 0.75:
            matches.append(entry)

    return matches


def retrieve_medical_knowledge(
    question: str,
    patient_context: dict[str, Any] | None,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    chunks = get_knowledge_chunks()
    if not chunks:
        return []

    query_parts = [question]
    if patient_context is not None:
        query_parts.extend(
            [
                str(patient_context.get("diagnosis", "")),
                str(patient_context.get("medical_notes", "")),
                str(patient_context.get("risk", "")),
            ]
        )

    query_tokens = tokenize_for_search(" ".join(query_parts))
    if not query_tokens:
        return []

    ranked: list[dict[str, Any]] = []
    for chunk in chunks:
        overlap = query_tokens.intersection(chunk["tokens"])
        if not overlap:
            continue

        ranked.append(
            {
                "source": chunk["source"],
                "title": chunk["title"],
                "snippet": chunk["text"][:300],
                "score": len(overlap),
                "matched_terms": sorted(list(overlap))[:8],
            }
        )

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:top_k]


def assess_risk_details(patient: sqlite3.Row) -> dict[str, Any]:
    # Combined risk mode: diagnosis + clinical context.
    diagnosis_text = normalize_text(str(patient["diagnosis"]))
    clinical_context_text = normalize_text(
        f"{patient['diagnosis']} {patient['treatment']} {patient['medical_notes']}"
    )

    high_risk_terms = [
        "sepsis",
        "shock",
        "shock septico",
        "estado critico",
        "cancer",
        "carcinoma",
        "tumor maligno",
        "neoplasia maligna",
        "metastasis",
        "metastasico",
        "leucemia",
        "linfoma",
        "sarcoma",
        "glioblastoma",
        "terminal",
        "enfermedad mortal",
        "mortal",
        "pronostico reservado",
        "riesgo de muerte",
        "muerte",
        "infarto",
        "sindrome coronario agudo",
        "acv",
        "ictus",
        "evento vascular cerebral",
        "hemorragia",
        "hemorragia masiva",
        "embolia pulmonar",
        "tromboembol",
        "insuficiencia respiratoria",
        "insuficiencia respiratoria aguda",
        "falla organica",
        "falla multiorganica",
        "falla hepatica",
        "falla renal aguda",
        "coma",
        "aneurisma",
        "alto riesgo",
        "riesgo vital",
    ]
    medium_risk_terms = [
        "diabetes",
        "hipertension",
        "cardiaco",
        "insuficiencia cardiaca",
        "renal cronica",
        "enfermedad renal",
        "epoc",
        "asma",
        "neumonia",
        "autoinmune",
        "inmunosuprimido",
        "cirrosis",
        "obesidad",
        "embarazo de riesgo",
    ]
    destabilization_terms = [
        "descompensado",
        "deterioro",
        "hipoxemia",
        "saturacion baja",
        "dolor toracico",
        "disnea",
        "sangrado activo",
        "urgente",
        "estado critico",
        "inestable",
    ]

    catalog_matches = find_catalog_matches(clinical_context_text)
    catalog_high = [m for m in catalog_matches if m["level"] == "alto"]
    catalog_medium = [m for m in catalog_matches if m["level"] == "medio"]

    high_matches = [term for term in high_risk_terms if term in clinical_context_text]
    medium_matches = [term for term in medium_risk_terms if term in clinical_context_text]
    destabilization_matches = [
        term for term in destabilization_terms if term in clinical_context_text
    ]

    high_matches.extend(match["term"] for match in catalog_high)
    medium_matches.extend(match["term"] for match in catalog_medium)

    # Deduplicate while preserving order.
    high_matches = list(dict.fromkeys(high_matches))
    medium_matches = list(dict.fromkeys(medium_matches))

    score = 0
    score += min(len(medium_matches), 3)
    score += min(len(destabilization_matches), 2)

    age = int(patient["age"])
    if age >= 75:
        score += 2
    elif age >= 65:
        score += 1

    reasons: list[str] = []
    if high_matches:
        reasons.extend(f"termino de alto riesgo detectado: {term}" for term in high_matches[:3])

    if catalog_matches:
        catalog_terms = ", ".join(match["term"] for match in catalog_matches[:4])
        reasons.append(f"catalogo clinico detecto: {catalog_terms}")

    if len(medium_matches) >= 2:
        reasons.append("multiples comorbilidades registradas")
    elif len(medium_matches) == 1:
        reasons.append(f"comorbilidad registrada: {medium_matches[0]}")

    if destabilization_matches:
        reasons.append(
            "signos de descompensacion: " + ", ".join(destabilization_matches[:3])
        )

    if age >= 75:
        reasons.append("edad avanzada >= 75")
    elif age >= 65:
        reasons.append("edad de riesgo >= 65")

    if high_matches:
        level = "Alto"
    elif score >= 4:
        level = "Alto"
    elif score >= 2:
        level = "Medio"
    else:
        level = "Bajo"

    if not reasons:
        reasons.append("sin hallazgos de riesgo mayor en texto clinico")

    return {
        "level": level,
        "reasons": reasons,
        "high_matches": high_matches,
        "medium_matches": medium_matches,
        "destabilization_matches": destabilization_matches,
        "catalog_matches": catalog_matches,
    }


def build_patient_context(patient: sqlite3.Row) -> dict[str, Any]:
    risk_details = assess_risk_details(patient)
    return {
        "id": str(patient["id"]),
        "name": patient["name"],
        "age": str(patient["age"]),
        "diagnosis": patient["diagnosis"],
        "treatment": patient["treatment"],
        "medical_notes": patient["medical_notes"],
        "consultation_date": patient["consultation_date"],
        "risk": risk_details["level"],
        "risk_reasons": risk_details["reasons"],
        "follow_up": follow_up_reminder(patient),
    }


def local_staff_chat_fallback(
    question: str,
    patient_context: dict[str, Any] | None,
    knowledge_refs: list[dict[str, Any]],
    chat_history: list[dict[str, str]],
) -> str:
    intro = (
        "Asistente para personal medico: solo apoyo clinico general, "
        "sin diagnostico definitivo ni recetas."
    )

    question_normalized = normalize_text(question)
    ask_for_explanation = any(
        keyword in question_normalized
        for keyword in ["explica", "explicame", "resumen", "que tiene", "enfermedad"]
    )
    ask_for_follow_up = any(
        keyword in question_normalized
        for keyword in ["seguimiento", "control", "proximo", "monitor", "reevalu"]
    )
    ask_for_alerts = any(
        keyword in question_normalized
        for keyword in ["alerta", "bandera", "urgente", "red flag", "emergencia"]
    )

    if patient_context is None:
        refs_text = "\n".join(
            f"- {ref['title']} ({ref['source']}): {ref['snippet']}"
            for ref in knowledge_refs[:2]
        )
        if not refs_text:
            refs_text = "- Sin referencias cargadas en knowledge/."

        dynamic_hint = ""
        if ask_for_alerts:
            dynamic_hint = (
                "\nAlertas generales prioritarias:\n"
                "- Deterioro hemodinamico\n"
                "- Compromiso respiratorio\n"
                "- Alteracion neurologica aguda\n"
                "- Sangrado activo o sospecha de sepsis\n"
            )
        elif ask_for_follow_up:
            dynamic_hint = (
                "\nSugerencia de seguimiento general:\n"
                "- Definir ventana de reevaluacion segun evolucion\n"
                "- Registrar respuesta clinica y adherencia en cada control\n"
            )

        return (
            f"{intro}\n\n"
            "Sugerencias:\n"
            "- Si deseas analisis orientado a riesgo de un paciente, selecciona un expediente en el chat.\n"
            "- Prioriza revision de signos de alarma, evolucion temporal y adherencia al tratamiento.\n"
            "- Usa protocolos de tu institucion para tomar decisiones clinicas finales.\n\n"
            f"{dynamic_hint}\n"
            "Referencias usadas:\n"
            f"{refs_text}\n\n"
            f"Consulta recibida: {question[:220]}"
        )

    risk = patient_context["risk"]
    reasons = patient_context.get("risk_reasons", [])

    risk_actions = {
        "Alto": [
            "Priorizar valoracion clinica presencial y monitorizacion estrecha.",
            "Revisar red flags y criterios de referencia urgente de forma inmediata.",
            "Confirmar adherencia, interacciones y contraindicaciones del plan actual.",
        ],
        "Medio": [
            "Programar control cercano para reevaluar evolucion clinica.",
            "Vigilar progresion de sintomas y parametros objetivos de seguimiento.",
            "Ajustar plan de seguimiento segun respuesta y comorbilidades.",
        ],
        "Bajo": [
            "Mantener seguimiento protocolizado y educacion al paciente.",
            "Reforzar signos de alarma para consulta anticipada.",
            "Documentar evolucion y adherencia en proximos controles.",
        ],
    }

    red_flags = [
        "deterioro respiratorio o saturacion en descenso",
        "dolor toracico persistente o inestabilidad hemodinamica",
        "alteracion neurologica aguda",
        "sangrado activo o signos de sepsis",
    ]

    explanation = (
        f"El cuadro actual se interpreta con prioridad {risk.lower()} por los hallazgos registrados."
    )
    if ask_for_explanation:
        explanation = (
            f"Resumen clinico orientativo: el paciente presenta un contexto asociado a riesgo {risk.lower()}, "
            "segun diagnostico, notas y condiciones registradas en el expediente."
        )

    reasons_text = "\n".join(f"- {reason}" for reason in reasons[:4])
    actions_text = "\n".join(f"- {item}" for item in risk_actions.get(risk, risk_actions["Bajo"]))
    red_flags_text = "\n".join(f"- {flag}" for flag in red_flags)
    references_text = "\n".join(
        f"- {ref['title']} ({ref['source']})"
        for ref in knowledge_refs[:3]
    )
    if not references_text:
        references_text = "- Sin referencias cargadas en knowledge/."

    question_tokens = tokenize_for_search(question)
    actionable_lines: list[str] = []
    for ref in knowledge_refs:
        snippet_sentences = re.split(r"(?<=[\.!?])\s+", ref["snippet"])
        for sentence in snippet_sentences:
            sentence_tokens = tokenize_for_search(sentence)
            if question_tokens.intersection(sentence_tokens):
                cleaned = sentence.strip()
                if len(cleaned) > 35:
                    actionable_lines.append(cleaned)
            if len(actionable_lines) >= 2:
                break
        if len(actionable_lines) >= 2:
            break

    if not actionable_lines and knowledge_refs:
        actionable_lines.append(knowledge_refs[0]["snippet"])

    focused_reference_guidance = "\n".join(f"- {line}" for line in actionable_lines[:2])
    if not focused_reference_guidance:
        focused_reference_guidance = "- Sin lineas especificas recuperadas para esta consulta."

    prior_user_messages = [m["content"] for m in chat_history if m.get("role") == "user"]
    conversation_context = ""
    if len(prior_user_messages) >= 2:
        conversation_context = (
            "Contexto conversacional: esta respuesta considera tambien la pregunta previa del medico.\n"
        )

    focus_sections: list[str] = []
    if ask_for_follow_up:
        focus_sections.append(
            "Plan de seguimiento sugerido:\n"
            f"- {patient_context['follow_up']}\n"
            "- Definir ventana de reevaluacion segun evolucion clinica y comorbilidades."
        )
    if ask_for_alerts or risk == "Alto":
        focus_sections.append(
            "Alertas prioritarias:\n"
            f"{red_flags_text}"
        )

    extra_focus = "\n\n".join(focus_sections)
    if extra_focus:
        extra_focus = f"\n\n{extra_focus}"

    return (
        f"{intro}\n\n"
        f"{conversation_context}"
        f"Paciente: {patient_context['name']} (ID {patient_context['id']})\n"
        f"Diagnostico registrado: {patient_context['diagnosis']}\n"
        f"Tratamiento registrado: {patient_context['treatment']}\n"
        f"Riesgo estimado actual: {risk}\n"
        f"Seguimiento sugerido: {patient_context['follow_up']}\n\n"
        f"{explanation}\n\n"
        "Motivos del riesgo:\n"
        f"{reasons_text}\n\n"
        "Sugerencias:\n"
        f"{actions_text}\n\n"
        "Alertas clinicas (red flags):\n"
        f"{red_flags_text}\n\n"
        f"{extra_focus}"
        "Respuesta enfocada en tu consulta:\n"
        f"{focused_reference_guidance}\n\n"
        "Referencias usadas:\n"
        f"{references_text}\n\n"
        f"Consulta recibida: {question[:220]}\n\n"
        "Nota: esta salida no constituye diagnostico ni prescripcion."
    )


def chat_with_grok_for_staff(
    chat_history: list[dict[str, str]],
    patient_context: dict[str, Any] | None,
    knowledge_refs: list[dict[str, Any]],
) -> tuple[str | None, str]:
    if not app.config["GROK_API_KEY"].strip():
        return None, "API key no configurada"

    system_prompt = (
        "Eres un asistente clinico digital para personal medico. "
        "Responde solo como apoyo y triaje orientativo. "
        "PROHIBIDO: dar diagnostico definitivo, recetas, dosis o prescripciones. "
        "Debes incluir: 1) Riesgo estimado (Bajo/Medio/Alto), "
        "2) Sugerencias de seguimiento, 3) Alertas o red flags. "
        "Incluye respuesta desarrollada y util para trabajo clinico: "
        "motivos del riesgo, hallazgos clave, proximos pasos y criterios de escalamiento. "
        "Usa secciones con titulos claros y bullets cuando sea posible. "
        "Aclara siempre que la decision final la toma el profesional tratante."
    )

    context_block = ""
    if patient_context is not None:
        context_block = (
            "\nContexto de paciente seleccionado:\n"
            f"ID: {patient_context['id']}\n"
            f"Nombre: {patient_context['name']}\n"
            f"Edad: {patient_context['age']}\n"
            f"Diagnostico registrado: {patient_context['diagnosis']}\n"
            f"Tratamiento registrado: {patient_context['treatment']}\n"
            f"Notas medicas: {patient_context['medical_notes']}\n"
            f"Fecha de consulta: {patient_context['consultation_date']}\n"
            f"Riesgo local calculado: {patient_context['risk']}\n"
            f"Motivos del riesgo local: {', '.join(patient_context.get('risk_reasons', []))}\n"
            f"Seguimiento local sugerido: {patient_context['follow_up']}\n"
        )

    references_block = ""
    if knowledge_refs:
        refs_lines = [
            f"- [{ref['source']}] {ref['title']}: {ref['snippet']}"
            for ref in knowledge_refs
        ]
        references_block = "\nReferencias clinicas recuperadas:\n" + "\n".join(refs_lines)

    # Keep a compact conversation window to avoid provider context overflow.
    recent_messages = chat_history[-6:]
    compact_messages: list[dict[str, str]] = []
    for item in recent_messages:
        role = item.get("role", "user")
        content = item.get("content", "").strip()
        if not content:
            continue
        compact_messages.append({"role": role, "content": content[:700]})

    messages = [{"role": "system", "content": system_prompt + context_block + references_block}]
    messages.extend(compact_messages)

    content, status = call_llm_chat(messages, max_tokens=450, temperature=0.2)
    if content:
        return content, status

    # Retry with minimal context when full conversation fails.
    last_user = ""
    for item in reversed(chat_history):
        if item.get("role") == "user" and item.get("content", "").strip():
            last_user = item["content"].strip()[:900]
            break

    if not last_user:
        return None, status

    minimal_messages = [
        {"role": "system", "content": system_prompt + context_block + references_block},
        {"role": "user", "content": last_user},
    ]
    retry_content, retry_status = call_llm_chat(
        minimal_messages,
        max_tokens=450,
        temperature=0.2,
    )
    if retry_content:
        return retry_content, f"{retry_status} | Reintento de contexto reducido"

    return None, f"{status} | {retry_status}"


def build_summary_fingerprint(patient: sqlite3.Row) -> str:
    base_text = "|".join(
        [
            str(patient["diagnosis"]).strip().lower(),
            str(patient["treatment"]).strip().lower(),
            str(patient["medical_notes"]).strip().lower(),
        ]
    )
    return hashlib.sha256(base_text.encode("utf-8")).hexdigest()


def detect_risk(patient: sqlite3.Row) -> str:
    return str(assess_risk_details(patient)["level"])


def follow_up_reminder(patient: sqlite3.Row) -> str:
    try:
        consultation = datetime.strptime(patient["consultation_date"], "%Y-%m-%d")
    except ValueError:
        return "Revisar fecha de consulta"

    days_since = (datetime.now() - consultation).days
    if days_since > 90:
        return "Programar seguimiento prioritario"
    if days_since > 30:
        return "Sugerido control de seguimiento"
    return "Seguimiento en curso"


@app.route("/")
def index() -> str:
    db = get_db()
    total_patients = db.execute("SELECT COUNT(*) AS count FROM patients").fetchone()["count"]
    recent_patients = db.execute(
        """
        SELECT id, name, diagnosis, consultation_date
        FROM patients
        ORDER BY consultation_date DESC
        LIMIT 5
        """
    ).fetchall()

    return render_template(
        "index.html",
        total_patients=total_patients,
        recent_patients=recent_patients,
    )


@app.route("/patients/register", methods=["GET", "POST"])
def register_patient() -> str:
    if request.method == "POST":
        parsed = parse_patient_form(request.form)
        form_data = parsed["data"]
        errors = parsed["errors"]

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("register.html", form_data=form_data)

        timestamp = datetime.now().isoformat(timespec="seconds")
        db = get_db()
        db.execute(
            """
            INSERT INTO patients (
                name, age, diagnosis, treatment, medical_notes,
                consultation_date, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                form_data["name"],
                form_data["age"],
                form_data["diagnosis"],
                form_data["treatment"],
                form_data["medical_notes"],
                form_data["consultation_date"],
                timestamp,
                timestamp,
            ),
        )
        db.commit()

        flash("Paciente registrado correctamente.", "success")
        return redirect(url_for("list_patients"))

    return render_template("register.html", form_data={})


@app.route("/patients")
def list_patients() -> str:
    db = get_db()
    patients = db.execute(
        """
        SELECT id, name, age, diagnosis, consultation_date
        FROM patients
        ORDER BY consultation_date DESC, id DESC
        """
    ).fetchall()
    return render_template("patients.html", patients=patients)


@app.route("/patients/<int:patient_id>")
def patient_detail(patient_id: int) -> str:
    db = get_db()
    patient = db.execute(
        "SELECT * FROM patients WHERE id = ?",
        (patient_id,),
    ).fetchone()

    if patient is None:
        flash("Paciente no encontrado.", "error")
        return redirect(url_for("list_patients"))

    return render_template("patient_detail.html", patient=patient)


@app.route("/patients/<int:patient_id>/edit", methods=["GET", "POST"])
def edit_patient(patient_id: int) -> str:
    db = get_db()
    patient = db.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()

    if patient is None:
        flash("Paciente no encontrado.", "error")
        return redirect(url_for("list_patients"))

    if request.method == "POST":
        parsed = parse_patient_form(request.form)
        form_data = parsed["data"]
        errors = parsed["errors"]

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("edit_patient.html", patient=patient, form_data=form_data)

        db.execute(
            """
            UPDATE patients
            SET name = ?, age = ?, diagnosis = ?, treatment = ?, medical_notes = ?,
                consultation_date = ?,
                ai_summary_cache = NULL,
                ai_summary_fingerprint = NULL,
                ai_summary_model = NULL,
                ai_summary_cached_at = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (
                form_data["name"],
                form_data["age"],
                form_data["diagnosis"],
                form_data["treatment"],
                form_data["medical_notes"],
                form_data["consultation_date"],
                datetime.now().isoformat(timespec="seconds"),
                patient_id,
            ),
        )
        db.commit()

        flash("Paciente actualizado correctamente.", "success")
        return redirect(url_for("patient_detail", patient_id=patient_id))

    return render_template("edit_patient.html", patient=patient, form_data={})


@app.route("/patients/<int:patient_id>/delete", methods=["POST"])
def delete_patient(patient_id: int) -> str:
    db = get_db()
    db.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
    db.commit()

    flash("Registro eliminado correctamente.", "success")
    return redirect(url_for("list_patients"))


@app.route("/history")
def history() -> str:
    db = get_db()
    history_rows = db.execute(
        """
        SELECT id, name, diagnosis, treatment, consultation_date, updated_at
        FROM patients
        ORDER BY consultation_date DESC, updated_at DESC
        """
    ).fetchall()
    
    # Get health trends for each patient
    patient_trends = {}
    for patient in history_rows:
        trends = db.execute(
            """
            SELECT metric_type, value, unit, measurement_date
            FROM health_trends
            WHERE patient_id = ?
            ORDER BY measurement_date DESC
            LIMIT 10
            """,
            (patient["id"],)
        ).fetchall()
        
        if trends:
            patient_trends[patient["id"]] = {
                "count": len(trends),
                "last_date": trends[0]["measurement_date"] if trends else None,
                "metrics": {}
            }
            for trend in trends:
                metric = trend["metric_type"]
                if metric not in patient_trends[patient["id"]]["metrics"]:
                    patient_trends[patient["id"]]["metrics"][metric] = []
                patient_trends[patient["id"]]["metrics"][metric].append({
                    "value": trend["value"],
                    "unit": trend["unit"],
                    "date": trend["measurement_date"]
                })
    
    return render_template("history.html", history_rows=history_rows, patient_trends=patient_trends)


@app.route("/laboratories", methods=["GET", "POST"])
def laboratories() -> str:
    db = get_db()
    patients = db.execute("SELECT id, name FROM patients ORDER BY name").fetchall()
    lab_chat_history = session.get("lab_chat_history", [])
    lab_llm_status = session.get("lab_llm_status", "")
    selected_lab_patient_id = request.form.get("lab_patient_id", "") if request.method == "POST" else ""

    if request.method == "POST":
        action = request.form.get("action", "save_lab")

        if action == "save_lab":
            parsed = parse_laboratory_form(request.form)
            form_data = parsed["data"]
            errors = parsed["errors"]

            patient_exists = db.execute(
                "SELECT id FROM patients WHERE id = ?",
                (form_data["patient_id"],),
            ).fetchone()
            if patient_exists is None:
                errors.append("El paciente seleccionado no existe.")

            if errors:
                for error in errors:
                    flash(error, "error")
            else:
                created_at = datetime.now().isoformat(timespec="seconds")
                rows_to_insert = [
                    (
                        form_data["patient_id"],
                        entry["test_name"],
                        entry["result_value"],
                        entry["units"],
                        entry["reference_range"],
                        form_data["interpretation_notes"],
                        form_data["lab_date"],
                        created_at,
                    )
                    for entry in form_data["lab_entries"]
                ]
                db.executemany(
                    """
                    INSERT INTO laboratory_analyses (
                        patient_id, test_name, result_value, units, reference_range,
                        interpretation_notes, lab_date, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows_to_insert,
                )
                db.commit()
                flash(
                    f"Solicitud registrada con {len(rows_to_insert)} parametro(s) de laboratorio.",
                    "success",
                )

        elif action == "lab_chat":
            chat_question = request.form.get("lab_chat_message", "").strip()
            if not selected_lab_patient_id.isdigit():
                flash("Selecciona un paciente para analizar su panel de laboratorio.", "error")
            else:
                patient_row = db.execute(
                    """
                    SELECT id, name
                    FROM patients
                    WHERE id = ?
                    """,
                    (int(selected_lab_patient_id),),
                ).fetchone()
                if patient_row is None:
                    flash("No se encontro el paciente seleccionado.", "error")
                else:
                    latest_lab_date_row = db.execute(
                        """
                        SELECT MAX(lab_date) AS latest_lab_date
                        FROM laboratory_analyses
                        WHERE patient_id = ?
                        """,
                        (int(selected_lab_patient_id),),
                    ).fetchone()
                    latest_lab_date = str(latest_lab_date_row["latest_lab_date"] or "")

                    if not latest_lab_date:
                        flash("El paciente no tiene analisis de laboratorio registrados.", "error")
                    else:
                        patient_lab_rows = db.execute(
                            """
                            SELECT l.*, p.name AS patient_name
                            FROM laboratory_analyses l
                            JOIN patients p ON p.id = l.patient_id
                            WHERE l.patient_id = ? AND l.lab_date = ?
                            ORDER BY l.id ASC
                            """,
                            (int(selected_lab_patient_id), latest_lab_date),
                        ).fetchall()

                        if not chat_question:
                            chat_question = (
                                "Analiza en conjunto este panel y resume riesgo orientativo."
                            )

                        lab_chat_history.append({"role": "user", "content": chat_question[:700]})
                        summary_text, lab_llm_status = summarize_patient_labs_with_ai(
                            list(patient_lab_rows),
                            str(patient_row["name"]),
                            latest_lab_date,
                            chat_question,
                        )
                        combined_reply = (
                            f"Paciente: {patient_row['name']} (ID {patient_row['id']})\n"
                            f"Fecha de panel analizada: {latest_lab_date}\n"
                            f"Consulta: {chat_question[:220]}\n\n"
                            f"{summary_text}\n\n"
                            "Nota: salida de apoyo para personal medico, no sustituye juicio clinico."
                        )
                        lab_chat_history.append({"role": "assistant", "content": combined_reply})
                        lab_chat_history = lab_chat_history[-12:]
                        session["lab_chat_history"] = lab_chat_history
                        session["lab_llm_status"] = lab_llm_status
                        session.modified = True

        elif action == "clear_lab_chat":
            session.pop("lab_chat_history", None)
            session.pop("lab_llm_status", None)
            lab_chat_history = []
            lab_llm_status = ""

    lab_rows = db.execute(
        """
        SELECT l.*, p.name AS patient_name
        FROM laboratory_analyses l
        JOIN patients p ON p.id = l.patient_id
        ORDER BY l.lab_date DESC, l.id DESC
        """
    ).fetchall()

    return render_template(
        "laboratories.html",
        patients=patients,
        lab_panel_sections=LAB_PANEL_SECTIONS,
        lab_rows=lab_rows,
        lab_chat_history=lab_chat_history,
        lab_llm_status=lab_llm_status,
        selected_lab_patient_id=selected_lab_patient_id,
    )


@app.route("/prescriptions", methods=["GET", "POST"])
def prescriptions() -> str:
    db = get_db()
    patients = db.execute("SELECT id, name FROM patients ORDER BY name").fetchall()

    if request.method == "POST":
        parsed = parse_prescription_form(request.form)
        form_data = parsed["data"]
        errors = parsed["errors"]

        patient_exists = db.execute(
            "SELECT id FROM patients WHERE id = ?",
            (form_data["patient_id"],),
        ).fetchone()
        if patient_exists is None:
            errors.append("El paciente seleccionado no existe.")

        if errors:
            for error in errors:
                flash(error, "error")
        else:
            db.execute(
                """
                INSERT INTO prescriptions (
                    patient_id, medication, presentation, dosage,
                    frequency, duration, instructions, prescription_date, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    form_data["patient_id"],
                    form_data["medication"],
                    form_data["presentation"],
                    form_data["dosage"],
                    form_data["frequency"],
                    form_data["duration"],
                    form_data["instructions"],
                    form_data["prescription_date"],
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            db.commit()
            flash("Receta registrada correctamente.", "success")

    prescription_rows = db.execute(
        """
        SELECT r.*, p.name AS patient_name
        FROM prescriptions r
        JOIN patients p ON p.id = r.patient_id
        ORDER BY r.prescription_date DESC, r.id DESC
        """
    ).fetchall()

    return render_template(
        "prescriptions.html",
        patients=patients,
        prescription_rows=prescription_rows,
    )


@app.route("/ai-panel", methods=["GET", "POST"])
def ai_panel() -> str:
    db = get_db()
    patients = db.execute("SELECT * FROM patients ORDER BY consultation_date DESC").fetchall()
    disease_catalog_count = len(get_disease_catalog_entries())
    action = request.form.get("action", "") if request.method == "POST" else ""
    has_grok_api_key = bool(app.config["GROK_API_KEY"].strip())
    # Default behavior: use Grok whenever API key is configured.
    run_grok = has_grok_api_key
    force_reanalyze = action == "reanalyze"
    chat_history = session.get("ai_chat_history", [])
    last_chat_references = session.get("ai_chat_last_references", [])
    llm_runtime_status = session.get("ai_llm_status", "")
    selected_patient_id = request.form.get("chat_patient_id", "") if request.method == "POST" else ""
    selected_patient_context: dict[str, Any] | None = None

    if selected_patient_id.isdigit():
        selected_patient = db.execute(
            "SELECT * FROM patients WHERE id = ?",
            (int(selected_patient_id),),
        ).fetchone()
        if selected_patient is not None:
            selected_patient_context = build_patient_context(selected_patient)

    if run_grok and not has_grok_api_key:
        flash("No hay API key configurada para ejecutar Grok.", "error")
        run_grok = False

    if action == "chat":
        chat_message = request.form.get("chat_message", "").strip()
        if not chat_message:
            flash("Escribe una consulta para el chat IA.", "error")
        else:
            short_query = normalize_text(chat_message)
            if len(short_query) <= 12 or short_query in {"resume", "resumen", "analiza", "analisis"}:
                chat_message = (
                    "Genera un resumen clinico completo del paciente con: "
                    "1) estado actual, 2) riesgo y motivos, 3) plan de seguimiento, "
                    "4) alertas/red flags, 5) proximos pasos sugeridos. "
                    "Responde con secciones claras y lenguaje medico practico."
                )

            if len(chat_message) > 1500:
                chat_message = chat_message[:1500]

            references = retrieve_medical_knowledge(chat_message, selected_patient_context)
            chat_history.append({"role": "user", "content": chat_message})
            assistant_reply, llm_runtime_status = chat_with_grok_for_staff(
                chat_history,
                selected_patient_context,
                references,
            )
            if assistant_reply is None:
                assistant_reply = local_staff_chat_fallback(
                    chat_message,
                    selected_patient_context,
                    references,
                    chat_history,
                )
                llm_runtime_status = f"{llm_runtime_status} | Fallback local activado"
                flash(
                    "La IA entro en modo local para esta respuesta. Si persiste, usa 'Limpiar chat' para reiniciar contexto.",
                    "error",
                )

            chat_history.append({"role": "assistant", "content": assistant_reply})
            chat_history = chat_history[-14:]
            session["ai_chat_history"] = chat_history
            session["ai_chat_last_references"] = references
            session["ai_llm_status"] = llm_runtime_status
            last_chat_references = references
            session.modified = True

    if action == "clear_chat":
        session.pop("ai_chat_history", None)
        session.pop("ai_chat_last_references", None)
        session.pop("ai_llm_status", None)
        chat_history = []
        last_chat_references = []
        llm_runtime_status = ""

    insights = []
    cache_hits = 0
    generated_with_grok = 0
    local_fallbacks = 0

    for patient in patients:
        summary = summarize_notes(patient["medical_notes"])
        summary_source = "local"
        risk_details = assess_risk_details(patient)
        risk_reason_short = "; ".join(risk_details["reasons"][:2])

        if run_grok:
            fingerprint = build_summary_fingerprint(patient)
            cached_summary = patient["ai_summary_cache"]
            cached_fingerprint = patient["ai_summary_fingerprint"]
            cached_model = patient["ai_summary_model"]

            if (
                not force_reanalyze
                and cached_summary
                and cached_fingerprint == fingerprint
                and cached_model == app.config["GROK_MODEL"]
            ):
                summary = cached_summary
                summary_source = "cache"
                cache_hits += 1
            else:
                ai_summary = summarize_with_grok(patient["medical_notes"])
                if ai_summary:
                    cached_at = datetime.now().isoformat(timespec="seconds")
                    db.execute(
                        """
                        UPDATE patients
                        SET ai_summary_cache = ?,
                            ai_summary_fingerprint = ?,
                            ai_summary_model = ?,
                            ai_summary_cached_at = ?
                        WHERE id = ?
                        """,
                        (
                            ai_summary,
                            fingerprint,
                            app.config["GROK_MODEL"],
                            cached_at,
                            patient["id"],
                        ),
                    )
                    summary = ai_summary
                    summary_source = "grok"
                    generated_with_grok += 1
                else:
                    summary_source = "local-fallback"
                    local_fallbacks += 1

        insights.append(
            {
                "id": patient["id"],
                "name": patient["name"],
                "summary": summary,
                "summary_source": summary_source,
                "risk": risk_details["level"],
                "risk_reasons": risk_details["reasons"],
                "risk_reason_short": risk_reason_short,
                "reminder": follow_up_reminder(patient),
            }
        )

    if run_grok:
        db.commit()

    return render_template(
        "ai_panel.html",
        insights=insights,
        patients=patients,
        disease_catalog_count=disease_catalog_count,
        has_grok_api_key=has_grok_api_key,
        used_grok=run_grok,
        cache_hits=cache_hits,
        generated_with_grok=generated_with_grok,
        local_fallbacks=local_fallbacks,
        llm_runtime_status=llm_runtime_status,
        llm_provider=detect_llm_provider(),
        chat_history=chat_history,
        last_chat_references=last_chat_references,
        selected_patient_id=selected_patient_id,
    )


@app.route("/analytics")
def analytics():
    """Mostrar análisis de optimización con funciones lineales."""
    return render_template("analytics.html")


@app.route("/health-trends", methods=["GET", "POST"])
def health_trends():
    """Mostrar tendencias de salud con análisis de derivadas."""
    db = get_db()
    patients = db.execute("SELECT id, name FROM patients ORDER BY name").fetchall()
    
    selected_patient_id = ""
    patient_trends = {"glucosa": [], "presion_arterial": []}
    
    if request.method == "POST":
        action = request.form.get("action")
        selected_patient_id = request.form.get("patient_id", "")
        
        if action == "save_trend":
            patient_id = request.form.get("patient_id")
            metric_type = request.form.get("metric_type")
            value = request.form.get("value")
            unit = request.form.get("unit")
            measurement_date = request.form.get("measurement_date")
            
            if patient_id and metric_type and value and unit and measurement_date:
                try:
                    db.execute(
                        """
                        INSERT INTO health_trends 
                        (patient_id, metric_type, value, unit, measurement_date, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (int(patient_id), metric_type, float(value), unit, measurement_date, 
                         datetime.now().isoformat(timespec="seconds"))
                    )
                    db.commit()
                    flash(f"Registro de {metric_type} guardado correctamente.", "success")
                except Exception as e:
                    flash(f"Error al guardar: {str(e)}", "error")
        
        elif action == "load_patient" and selected_patient_id.isdigit():
            patient_trends_rows = db.execute(
                """
                SELECT metric_type, value, unit, measurement_date
                FROM health_trends
                WHERE patient_id = ?
                ORDER BY measurement_date DESC
                LIMIT 50
                """,
                (int(selected_patient_id),)
            ).fetchall()
            
            for row in patient_trends_rows:
                metric = row["metric_type"]
                if metric not in patient_trends:
                    patient_trends[metric] = []
                patient_trends[metric].append({
                    "value": row["value"],
                    "unit": row["unit"],
                    "fecha": row["measurement_date"]
                })
    
    return render_template(
        "health_trends.html", 
        patients=patients, 
        selected_patient_id=selected_patient_id,
        patient_trends=patient_trends
    )


@app.route("/api/health-trends/save", methods=["POST"])
def save_health_trend():
    """API para guardar tendencias de salud (AJAX)."""
    db = get_db()
    data = request.get_json()
    
    try:
        patient_id = data.get("patient_id")
        metric_type = data.get("metric_type")
        value = data.get("value")
        unit = data.get("unit")
        measurement_date = data.get("measurement_date")
        
        if not all([patient_id, metric_type, value, unit, measurement_date]):
            return {"success": False, "error": "Campos incompletos"}, 400
        
        # Verificar que el paciente existe
        patient = db.execute("SELECT id FROM patients WHERE id = ?", (int(patient_id),)).fetchone()
        if not patient:
            return {"success": False, "error": "Paciente no encontrado"}, 404
        
        db.execute(
            """
            INSERT INTO health_trends 
            (patient_id, metric_type, value, unit, measurement_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (int(patient_id), metric_type, float(value), unit, measurement_date,
             datetime.now().isoformat(timespec="seconds"))
        )
        db.commit()
        
        return {"success": True, "message": "Datos guardados correctamente"}
    except Exception as e:
        return {"success": False, "error": str(e)}, 500


@app.route("/api/health-trends/<int:patient_id>", methods=["GET"])
def get_health_trends(patient_id: int):
    """API para obtener tendencias de salud de un paciente."""
    db = get_db()
    
    try:
        trends = db.execute(
            """
            SELECT metric_type, value, unit, measurement_date
            FROM health_trends
            WHERE patient_id = ?
            ORDER BY measurement_date DESC
            LIMIT 50
            """,
            (patient_id,)
        ).fetchall()
        
        result = {}
        for row in trends:
            metric = row["metric_type"]
            if metric not in result:
                result[metric] = []
            result[metric].append({
                "value": row["value"],
                "unit": row["unit"],
                "fecha": row["measurement_date"]
            })
        
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}, 500


# Ensure tables exist in production (gunicorn/import execution) and local runs.
init_db()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
