from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from uvrl.app.services.database import PROJECT_ROOT, open_database


@dataclass(frozen=True)
class ResetUvrlResult:
    database_path: Path
    backup_path: Path | None
    deleted_directories: list[Path]
    recreated_directories: list[Path]


USER_DATA_TABLES = [
    "profile_steps",
    "profiles",
    "config_variants",
    "config_backups",
    "config_locations",
    "user_scripts",
    "app_registry",
]


GENERATED_DATA_DIRECTORIES = [
    PROJECT_ROOT / "data" / "config_variants",
    PROJECT_ROOT / "data" / "config_backups",
    PROJECT_ROOT / "data" / "config_variant_working",
    PROJECT_ROOT / "data" / "test_configs",
    PROJECT_ROOT / "data" / "alternate_variant_exports",
    PROJECT_ROOT / "data" / "alternate_backup_exports",
]


RECREATE_DIRECTORIES = [
    PROJECT_ROOT / "data" / "config_variants",
    PROJECT_ROOT / "data" / "config_backups",
    PROJECT_ROOT / "data" / "config_variant_working",
]


def _database_path() -> Path:
    return PROJECT_ROOT / "data" / "uvrl.db"


def _backup_database(database_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup_path = PROJECT_ROOT / "data" / f"uvrl_before_reset_{timestamp}.db"

    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(database_path, backup_path)

    return backup_path


def _clear_user_data_tables(database_path: Path) -> None:
    table_delete_sql = "\n".join(
        f"DELETE FROM {table_name};"
        for table_name in USER_DATA_TABLES
    )

    sequence_names = ", ".join(
        f"'{table_name}'"
        for table_name in USER_DATA_TABLES
    )

    reset_sql = f"""
    PRAGMA foreign_keys = ON;

    BEGIN;

    {table_delete_sql}

    DELETE FROM sqlite_sequence
    WHERE name IN ({sequence_names});

    COMMIT;
    """

    with open_database(database_path) as database:
        database.executescript(reset_sql)
        database.execute("VACUUM;")


def _clear_generated_directories() -> tuple[list[Path], list[Path]]:
    deleted_directories: list[Path] = []
    recreated_directories: list[Path] = []

    for directory in GENERATED_DATA_DIRECTORIES:
        if directory.exists():
            shutil.rmtree(directory)
            deleted_directories.append(directory)

    for directory in RECREATE_DIRECTORIES:
        directory.mkdir(parents=True, exist_ok=True)
        recreated_directories.append(directory)

    return deleted_directories, recreated_directories


def reset_uvrl_runtime_state(create_backup: bool = True) -> ResetUvrlResult:
    database_path = _database_path()

    if not database_path.exists():
        raise FileNotFoundError(f"UVRL database does not exist: {database_path}")

    backup_path = _backup_database(database_path) if create_backup else None

    _clear_user_data_tables(database_path)
    deleted_directories, recreated_directories = _clear_generated_directories()

    return ResetUvrlResult(
        database_path=database_path,
        backup_path=backup_path,
        deleted_directories=deleted_directories,
        recreated_directories=recreated_directories,
    )


def print_reset_proof() -> None:
    database_path = _database_path()

    with open_database(database_path) as database:
        table_counts = []

        for table_name in USER_DATA_TABLES:
            row = database.execute(
                f"SELECT COUNT(*) AS row_count FROM {table_name};"
            ).fetchone()

            table_counts.append((table_name, int(row["row_count"])))

        sequence_rows = database.execute(
            """
            SELECT name, seq
            FROM sqlite_sequence
            ORDER BY name;
            """
        ).fetchall()

        catalog_rows = database.execute(
            """
            SELECT target_kind, COUNT(*) AS row_count
            FROM discovery_catalog
            GROUP BY target_kind
            ORDER BY target_kind;
            """
        ).fetchall()

    print()
    print("Reset proof:")

    print("  user data tables:")
    for table_name, row_count in table_counts:
        print(f"    {table_name}: {row_count}")

    print("  user data ID sequences:")
    relevant_sequence_rows = [
        row
        for row in sequence_rows
        if row["name"] in USER_DATA_TABLES
    ]

    if relevant_sequence_rows:
        for row in relevant_sequence_rows:
            print(f"    {row['name']}: {row['seq']}")
    else:
        print("    none")

    print("  discovery catalog:")
    if catalog_rows:
        for row in catalog_rows:
            print(f"    {row['target_kind']}: {row['row_count']}")
    else:
        print("    none")