"""Conexión y bootstrap de la base de datos SQLite de ChinoSRS.

La base de datos vive en outputs/chinosrs.db (fuera de git, como el resto
de lo generado). El esquema (src/db/schema.sql) sí vive en el repo.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "outputs" / "chinosrs.db"


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Crea la base de datos y aplica el esquema si no existen las tablas."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with sqlite3.connect(db_path) as conn:
        conn.executescript(schema_sql)


@contextmanager
def get_connection(db_path: Path = DEFAULT_DB_PATH):
    """Context manager que entrega una conexión con foreign_keys activado."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
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
