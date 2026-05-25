from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from uvrl.app.services.database import open_database


@dataclass(frozen=True)
class AppRegistryEntry:
    app_id: int
    display_name: str
    launch_kind: str
    platform: str
    executable_path: str | None
    steam_app_id: str | None
    flatpak_app_id: str | None
    default_arguments: str | None


def add_app(
    display_name: str,
    launch_kind: str = "native",
    platform: str = "any",
    executable_path: str | None = None,
    working_directory: str | None = None,
    default_arguments: str | None = None,
    steam_app_id: str | None = None,
    flatpak_app_id: str | None = None,
    notes: str | None = None,
) -> int:
    with open_database() as database:
        cursor = database.execute(
            """
            INSERT INTO app_registry (
                display_name,
                launch_kind,
                platform,
                executable_path,
                working_directory,
                default_arguments,
                steam_app_id,
                flatpak_app_id,
                source,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'manual', ?);
            """,
            (
                display_name,
                launch_kind,
                platform,
                executable_path,
                working_directory,
                default_arguments,
                steam_app_id,
                flatpak_app_id,
                notes,
            ),
        )

        return int(cursor.lastrowid)


def list_apps() -> list[AppRegistryEntry]:
    with open_database() as database:
        rows = database.execute(
            """
            SELECT
                app_id,
                display_name,
                launch_kind,
                platform,
                executable_path,
                steam_app_id,
                flatpak_app_id,
                default_arguments
            FROM app_registry
            WHERE is_hidden = 0
            ORDER BY display_name COLLATE NOCASE;
            """
        ).fetchall()

    return [
        AppRegistryEntry(
            app_id=row["app_id"],
            display_name=row["display_name"],
            launch_kind=row["launch_kind"],
            platform=row["platform"],
            executable_path=row["executable_path"],
            steam_app_id=row["steam_app_id"],
            flatpak_app_id=row["flatpak_app_id"],
            default_arguments=row["default_arguments"],
        )
        for row in rows
    ]


def print_apps() -> None:
    apps = list_apps()

    if not apps:
        print("No apps registered.")
        return

    for app in apps:
        target = app.executable_path or app.steam_app_id or app.flatpak_app_id or "(no target)"

        print(f"[{app.app_id}] {app.display_name}")
        print(f"  kind:     {app.launch_kind}")
        print(f"  platform: {app.platform}")
        print(f"  target:   {target}")

        if app.default_arguments:
            print(f"  args:     {app.default_arguments}")

        print()
