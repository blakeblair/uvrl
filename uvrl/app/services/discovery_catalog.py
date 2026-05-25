from __future__ import annotations

from dataclasses import dataclass

from uvrl.app.services.database import open_database


@dataclass(frozen=True)
class DiscoveryCatalogEntry:
    discovery_catalog_id: int
    target_kind: str
    display_name: str
    category: str
    platform: str
    match_type: str
    match_value: str
    launch_kind: str | None
    file_kind: str | None
    steam_app_id: str | None
    flatpak_app_id: str | None
    priority: int
    is_enabled: bool
    notes: str | None
    source_name: str | None
    source_url: str | None


def list_discovery_catalog() -> list[DiscoveryCatalogEntry]:
    with open_database() as database:
        rows = database.execute(
            """
            SELECT
                discovery_catalog_id,
                target_kind,
                display_name,
                category,
                platform,
                match_type,
                match_value,
                launch_kind,
                file_kind,
                steam_app_id,
                flatpak_app_id,
                priority,
                is_enabled,
                notes,
                source_name,
                source_url
            FROM discovery_catalog
            ORDER BY target_kind, category, priority, display_name COLLATE NOCASE;
            """
        ).fetchall()

    return [
        DiscoveryCatalogEntry(
            discovery_catalog_id=int(row["discovery_catalog_id"]),
            target_kind=str(row["target_kind"]),
            display_name=str(row["display_name"]),
            category=str(row["category"]),
            platform=str(row["platform"]),
            match_type=str(row["match_type"]),
            match_value=str(row["match_value"]),
            launch_kind=row["launch_kind"],
            file_kind=row["file_kind"],
            steam_app_id=row["steam_app_id"],
            flatpak_app_id=row["flatpak_app_id"],
            priority=int(row["priority"]),
            is_enabled=bool(row["is_enabled"]),
            notes=row["notes"],
            source_name=row["source_name"],
            source_url=row["source_url"],
        )
        for row in rows
    ]


def print_discovery_catalog() -> None:
    entries = list_discovery_catalog()

    if not entries:
        print("No discovery catalog entries registered.")
        return

    current_group: tuple[str, str] | None = None

    for entry in entries:
        group = (entry.target_kind, entry.category)

        if group != current_group:
            current_group = group
            print()
            print(f"{entry.target_kind.upper()} TARGETS / {entry.category}")

        enabled_text = "enabled" if entry.is_enabled else "disabled"

        print(f"[{entry.discovery_catalog_id}] {entry.display_name}")
        print(f"  platform: {entry.platform}")
        print(f"  match:    {entry.match_type} = {entry.match_value}")
        print(f"  priority: {entry.priority}")
        print(f"  status:   {enabled_text}")

        if entry.launch_kind:
            print(f"  launch:   {entry.launch_kind}")

        if entry.file_kind:
            print(f"  file:     {entry.file_kind}")

        if entry.steam_app_id:
            print(f"  steam:    {entry.steam_app_id}")

        if entry.flatpak_app_id:
            print(f"  flatpak:  {entry.flatpak_app_id}")

        if entry.source_name:
            print(f"  source:   {entry.source_name}")

        if entry.source_url:
            print(f"  url:      {entry.source_url}")

        if entry.notes:
            print(f"  notes:    {entry.notes}")

        print()