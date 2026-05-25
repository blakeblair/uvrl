from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[3]

DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "uvrl.db"

SCHEMA_PATH = PROJECT_ROOT / "uvrl" / "db" / "schema.sql"

CONFIG_VARIANTS_DIR = DATA_DIR / "config_variants"
CONFIG_BACKUPS_DIR = DATA_DIR / "config_backups"


def ensure_runtime_directories() -> None:
    """
    Create runtime data folders used by UVRL during development.

    Later, these should move to a user data directory such as:
    Linux: ~/.local/share/uvrl/
    Windows: %APPDATA%/UVRL/
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_VARIANTS_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_BACKUPS_DIR.mkdir(parents=True, exist_ok=True)


def connect(database_path: Path = DATABASE_PATH) -> sqlite3.Connection:
    """
    Open a SQLite connection with UVRL defaults.

    foreign_keys must be enabled per connection in SQLite.
    row_factory makes rows behave more like dictionaries.
    """
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


@contextmanager
def open_database(database_path: Path = DATABASE_PATH) -> Iterator[sqlite3.Connection]:
    """
    Context manager for safe database use.

    Commits if the block succeeds.
    Rolls back if the block raises an exception.
    Always closes the connection.
    """
    connection = connect(database_path)

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(
    database_path: Path = DATABASE_PATH,
    schema_path: Path = SCHEMA_PATH,
) -> None:
    """
    Ensure folders exist and apply schema.sql.

    The schema uses CREATE TABLE IF NOT EXISTS, so this is safe to run
    repeatedly during development.
    """
    ensure_runtime_directories()

    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    schema_sql = schema_path.read_text(encoding="utf-8")

    with open_database(database_path) as database:
        database.executescript(schema_sql)


def get_table_names(database_path: Path = DATABASE_PATH) -> list[str]:
    """
    Return all user-created table names in the database.
    """
    with open_database(database_path) as database:
        rows = database.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name;
            """
        ).fetchall()

    return [row["name"] for row in rows]


def get_app_settings(database_path: Path = DATABASE_PATH) -> dict[str, str | None]:
    """
    Return app_settings as a simple dictionary.
    """
    with open_database(database_path) as database:
        rows = database.execute(
            """
            SELECT setting_key, setting_value
            FROM app_settings
            ORDER BY setting_key;
            """
        ).fetchall()

    return {row["setting_key"]: row["setting_value"] for row in rows}


def print_database_status() -> None:
    """
    Simple developer sanity check.
    """
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Database:     {DATABASE_PATH}")
    print(f"Schema:       {SCHEMA_PATH}")
    print()
    print("Tables:")

    for table_name in get_table_names():
        print(f"  - {table_name}")

    print()
    print("Settings:")

    for key, value in get_app_settings().items():
        print(f"  - {key}: {value}")


if __name__ == "__main__":
    initialize_database()
    print_database_status()
