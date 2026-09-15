"""Conexión y bootstrap de la base de datos SQLite de ChinoSRS.

La base de datos vive en outputs/chinosrs.db (fuera de git, como el resto
de lo generado). El esquema (src/db/schema.sql) sí vive en el repo.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "outputs" / "chinosrs.db"


def _migrate(conn: sqlite3.Connection) -> None:
    """Ajustes de esquema sobre una DB que ya existía antes de que se agregara
    la columna (CREATE TABLE IF NOT EXISTS no la agrega a una tabla existente)."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(cards)").fetchall()}
    if "anki_note_id" not in cols:
        conn.execute("ALTER TABLE cards ADD COLUMN anki_note_id INTEGER")
    if "regen_attempts" not in cols:
        conn.execute("ALTER TABLE cards ADD COLUMN regen_attempts INTEGER NOT NULL DEFAULT 0")

    word_cols = {row[1] for row in conn.execute("PRAGMA table_info(words)").fetchall()}
    if "export_level" not in word_cols:
        conn.execute("ALTER TABLE words ADD COLUMN export_level INTEGER")
    if "word_prep_status" not in word_cols:
        conn.execute("ALTER TABLE words ADD COLUMN word_prep_status TEXT NOT NULL DEFAULT 'pending'")
    if "word_prep_attempts" not in word_cols:
        conn.execute("ALTER TABLE words ADD COLUMN word_prep_attempts INTEGER NOT NULL DEFAULT 0")


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Crea la base de datos y aplica el esquema si no existen las tablas."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with sqlite3.connect(db_path) as conn:
        # WAL: permite lectores/escritores concurrentes sin "database is locked" —
        # necesario porque el grafo de generación corre nodos en paralelo, cada
        # uno con su propia conexión a este mismo archivo.
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(schema_sql)
        _migrate(conn)


@contextmanager
def get_connection(db_path: Path = DEFAULT_DB_PATH):
    """Context manager que entrega una conexión con foreign_keys activado."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Base de datos inicializada en: {DEFAULT_DB_PATH}")
