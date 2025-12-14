from dataclasses import dataclass
from pathlib import Path
from typing import Literal
import os

from app.os import get_os, OSType
from app.steam_discovery import (
    find_installed_steam_apps,
    steam_apps_to_discovered,
    #filter_related_apps,
)

# -------------------------
# Data model
# -------------------------

@dataclass
class DiscoveredApp:
    name: str
    path: Path
    source: Literal["steam", "filesystem", "manual"]
    confidence: int


# -------------------------
# Filesystem discovery
# -------------------------

LAUNCHABLE_EXTENSIONS = {".exe", ".bat", ".cmd", ".ps1", ".py"}

EXCLUDED_DIR_NAMES = {
    "windows",
    ".venv",
    "node_modules",
    "__pycache__",
    ".git",
    ".idea",
    "temp",
    "tmp",
    "videos",
    "pictures",
    "music",
    "gallery",
}


def filesystem_search_roots() -> list[Path]:
    """
    Root directories to scan for launchable files.
    """
    roots: list[Path] = []

    # User home (recursive)
    roots.append(Path.home())

    # System install locations
    roots.extend([
        Path(os.environ.get("ProgramFiles", "")),
        Path(os.environ.get("ProgramFiles(x86)", "")),
        Path(os.environ.get("LOCALAPPDATA", "")),
        Path(os.environ.get("PROGRAMDATA", "")),
    ])

    return [r for r in roots if r.exists()]


def should_skip_dir(path: Path, include_documents: bool) -> bool:
    name = path.name.lower()

    if name in EXCLUDED_DIR_NAMES:
        return True

    if not include_documents and name == "documents":
        return True

    # Skip common junk anywhere in the tree
    for part in path.parts:
        if part.lower() in {".venv", "node_modules"}:
            return True

    return False


def discover_filesystem_apps(
    include_documents: bool = False,
    max_depth: int = 6,
) -> list[DiscoveredApp]:
    """
    Discover executable or script-based apps from the filesystem.
    """
    discovered: list[DiscoveredApp] = []

    for root in filesystem_search_roots():
        for path in root.rglob("*"):
            try:
                relative_depth = len(path.relative_to(root).parts)
            except ValueError:
                continue

            if relative_depth > max_depth:
                continue

            if path.is_dir():
                if should_skip_dir(path, include_documents):
                    continue
                continue

            if path.suffix.lower() not in LAUNCHABLE_EXTENSIONS:
                continue

            discovered.append(
                DiscoveredApp(
                    name=path.stem,
                    path=path,
                    source="filesystem",
                    confidence=40,
                )
            )

    return discovered


# -------------------------
# Steam discovery wrapper
# -------------------------

def discover_steam_apps(authoritative: bool = True) -> list[DiscoveredApp]:
    """
    Discover Steam apps via local Steam metadata.
    If authoritative is True, only return apps listed in STEAMAPPS.
    """
    steam_apps = find_installed_steam_apps()
    discovered = steam_apps_to_discovered(steam_apps)

    if authoritative:
        return filter_related_apps(discovered)

    return discovered


# -------------------------
# Unified discovery entrypoint
# -------------------------

def filter_related_apps(apps: list[DiscoveredApp]) -> list[DiscoveredApp]:
    """
    Authoritative Steam-only filter for initial launcher population.
    Keeps only Steam apps listed in STEAMAPPS.
    """
    related: list[DiscoveredApp] = []

    for app in apps:
        if app.source != "steam":
            continue

        # Extract AppID from steam://run/<appid>
        path_str = str(app.path)
        if not path_str.startswith("steam://run/"):
            continue

        try:
            appid = int(path_str.removeprefix("steam://run/"))
        except ValueError:
            continue

        if appid in :
            related.append(app)

    return related

def discover_apps(
    include_documents: bool = False,
    authoritative_steam: bool = True,
) -> list[DiscoveredApp]:
    """
    Perform full app discovery:
    - Steam apps (filtered authoritatively by default)
    - Filesystem apps (broad scan with exclusions)
    """
    results: list[DiscoveredApp] = []

    results.extend(discover_steam_apps(authoritative=authoritative_steam))
    results.extend(discover_filesystem_apps(include_documents=include_documents))

    return results
