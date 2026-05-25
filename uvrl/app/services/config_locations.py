from __future__ import annotations

from dataclasses import dataclass

from uvrl.app.services.database import open_database


@dataclass(frozen=True)
class ConfigLocation:
    config_location_id: int
    display_name: str
    file_path: str
    platform: str
    file_kind: str
    app_id: int | None
    notes: str | None


def add_config_location(
    display_name: str,
    file_path: str,
    platform: str = "any",
    file_kind: str = "unknown",
    app_id: int | None = None,
    notes: str | None = None,
) -> int:
    with open_database() as database:
        cursor = database.execute(
            """
            INSERT INTO config_locations (
                display_name,
                file_path,
                platform,
                file_kind,
                app_id,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                display_name,
                file_path,
                platform,
                file_kind,
                app_id,
                notes,
            ),
        )

        return int(cursor.lastrowid)


def list_config_locations() -> list[ConfigLocation]:
    with open_database() as database:
        rows = database.execute(
            """
            SELECT
                config_location_id,
                display_name,
                file_path,
                platform,
                file_kind,
                app_id,
                notes
            FROM config_locations
            WHERE is_hidden = 0
            ORDER BY display_name COLLATE NOCASE;
            """
        ).fetchall()

    return [
        ConfigLocation(
            config_location_id=row["config_location_id"],
            display_name=row["display_name"],
            file_path=row["file_path"],
            platform=row["platform"],
            file_kind=row["file_kind"],
            app_id=row["app_id"],
            notes=row["notes"],
        )
        for row in rows
    ]


def print_config_locations() -> None:
    locations = list_config_locations()

    if not locations:
        print("No config locations registered.")
        return

    for location in locations:
        print(f"[{location.config_location_id}] {location.display_name}")
        print(f"  path:     {location.file_path}")
        print(f"  kind:     {location.file_kind}")
        print(f"  platform: {location.platform}")

        if location.app_id is not None:
            print(f"  app_id:   {location.app_id}")

        if location.notes:
            print(f"  notes:    {location.notes}")

        print()
