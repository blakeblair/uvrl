import os
from pathlib import Path
from app.utils import get_os, OSType, get_env, json_to_dict, read_file_as_text
from app.utils.config import get_default_config
from app.types import DiscoveredApp


from app.discovery.steam_discovery import (
   find_installed_steam_apps,
   steam_apps_to_discovered,
)


# -------------------------
# Filesystem discovery
# -------------------------

LAUNCHABLE_EXTENSIONS = {".exe", ".bat", ".cmd", ".ps1", ".py", ".sh"}

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


    current_platform = get_os()

    if current_platform == OSType.LINUX:

        platform_env_var = ["UVRL_APPS"]

    elif current_platform == OSType.WINDOWS:
        platform_env_var = ["HOME", "UVRL_APPS", "ProgramFiles", "ProgamFiles(x86)", "LOCALAPPDATA", "PROGAMDATA"]


    roots.extend([Path(get_env(env)) for env in platform_env_var if get_env(env) is not None])
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
    max_depth: int = 3,
) -> list[DiscoveredApp]:
    """
    Discover executable or script-based apps from the filesystem.
    """
    discovered: list[DiscoveredApp] = []

    print (filesystem_search_roots())
    for root in filesystem_search_roots():
        for path in root.rglob("*"):
            try:
                relative_depth = len(path.relative_to(root).parts)
            except ValueError:
                continue

            if relative_depth > max_depth:
                continue

            if path.is_dir():
                continue

            if path.suffix.lower() not in LAUNCHABLE_EXTENSIONS:
                continue

            discovered.append(
                DiscoveredApp(
                    name=path.stem,
                    path=path
                )
            )

    return discovered


# -------------------------
# Steam discovery wrapper
# -------------------------

def discover_steam_apps() -> list[DiscoveredApp]:
    """
    Discover Steam apps via local Steam metadata.
    """
    steam_apps = find_installed_steam_apps()
    discovered = steam_apps_to_discovered(steam_apps)

    return discovered


# -------------------------
# Unified discovery entrypoint
# -------------------------

def filter_steam_apps(apps: list[DiscoveredApp]) -> list[DiscoveredApp]:
    # Load the applist.json
    applist_path = get_default_config().app_list_config_path
    applist_data = json_to_dict(read_file_as_text(str(applist_path)))
    steam_apps = applist_data.get("steam_apps", {})

    related: list[DiscoveredApp] = []

    for app in apps:
        # Extract AppID from steam://run/<appid>
        path_str = str(app.path)
        if not path_str.startswith("steam://run/"):
            continue

        try:
            appid = int(path_str.removeprefix("steam://run/"))
        except ValueError:
            continue

        if str(appid) in steam_apps:
            related.append(app)

    return related

def discover_apps(
) -> list[DiscoveredApp]:
    """
    Perform full app discovery:
    - Steam apps (filtered authoritatively by default)
    - Filesystem apps (broad scan with exclusions)
    """
    results: list[DiscoveredApp] = []

    results.extend(discover_steam_apps())
    results.extend(discover_filesystem_apps())

    return results
