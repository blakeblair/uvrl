from dataclasses import dataclass
from pathlib import Path

from app.os import get_os, OSType
from app.discovery import DiscoveredApp

# -------------------------
# Data structures
# -------------------------

@dataclass
class SteamApp:
    appid: int
    name: str
    install_dir: Path


# -------------------------
# Steam path discovery
# -------------------------

def find_steam_root() -> Path | None:
    """
    Locate the Steam root directory for the current OS.
    """
    os_type = get_os()

    if os_type == OSType.WINDOWS:
        path = Path("C:/Program Files (x86)/Steam")
    elif os_type == OSType.LINUX:
        path = Path.home() / ".steam" / "steam"
    else:
        return None

    return path if path.exists() else None


def parse_libraryfolders_vdf(path: Path) -> list[Path]:
    """
    Parse Steam's libraryfolders.vdf and return steamapps paths.
    Minimal, tolerant parser.
    """
    libraries: list[Path] = []

    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()

                # Lines look like: "1"    "D:\\SteamLibrary"
                if line.count('"') >= 4:
                    parts = line.split('"')
                    value = parts[3]

                    lib_path = Path(value)
                    steamapps = lib_path / "steamapps"

                    if steamapps.exists():
                        libraries.append(steamapps)
    except OSError:
        pass

    return libraries


def find_steam_libraries() -> list[Path]:
    """
    Find all Steam library directories, including non-default drives.
    """
    steam_root = find_steam_root()
    if not steam_root:
        return []

    libraries: list[Path] = []

    # Default library
    default = steam_root / "steamapps"
    if default.exists():
        libraries.append(default)

    # Additional libraries
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        libraries.extend(parse_libraryfolders_vdf(vdf))

    # De-duplicate
    return list({lib.resolve() for lib in libraries})


# -------------------------
# Manifest parsing
# -------------------------

def parse_acf(path: Path) -> dict[str, str]:
    """
    Minimal ACF parser for Steam manifests.
    Reads flat key/value pairs at the top level.
    """
    data: dict[str, str] = {}

    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("//"):
                    continue

                # Expect lines like: "key"    "value"
                if line.count('"') >= 4:
                    parts = line.split('"')
                    key = parts[1]
                    value = parts[3]
                    data[key] = value
    except OSError:
        pass

    return data


def find_installed_steam_apps() -> list[SteamApp]:
    """
    Locate all installed Steam apps by parsing appmanifest_*.acf
    from all detected Steam libraries.
    """
    libraries = find_steam_libraries()
    if not libraries:
        return []

    apps: list[SteamApp] = []

    for steamapps in libraries:
        for manifest in steamapps.glob("appmanifest_*.acf"):
            try:
                appid = int(manifest.stem.split("_")[1])
            except (IndexError, ValueError):
                continue

            acf = parse_acf(manifest)

            name = acf.get("name", f"Steam App {appid}")
            installdir = acf.get("installdir")

            install_path = (
                steamapps / "common" / installdir
                if installdir
                else steamapps
            )

            apps.append(
                SteamApp(
                    appid=appid,
                    name=name,
                    install_dir=install_path,
                )
            )

    return apps


# -------------------------
# Steam → DiscoveredApp conversion
# -------------------------

def steam_apps_to_discovered(apps: list[SteamApp]) -> list[DiscoveredApp]:
    """
    Convert parsed Steam apps into DiscoveredApp entries
    using steam://run/<appid> URIs.

    Note: Filtering against a curated list happens in discovery.filter_steam_apps.
    """
    discovered: list[DiscoveredApp] = []

    for app in apps:
        discovered.append(
            DiscoveredApp(
                name=app.name,
                path=Path(f"steam://run/{app.appid}"),
                source="steam",
                confidence=60,
            )
        )

    return discovered

