#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from app.types import DiscoveredApp
from app.utils.os import get_os, OSType, executable_extensions
from app.discovery.steam_discovery import (
    find_steam_libraries,
    find_installed_steam_apps,
    steam_apps_to_discovered,
)

DEFAULT_EXCLUDED_DIR_NAMES = {
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

def config_path() -> Path:
    os_type = get_os()
    if os_type == OSType.WINDOWS:
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "uvrl" / "config.json"
    # Linux (and unknown): XDG fallback
    base = os.environ.get("XDG_CONFIG_HOME") or (str(Path.home() / ".config"))
    return Path(base) / "uvrl" / "config.json"


def default_roots() -> list[dict[str, Any]]:
    os_type = get_os()
    roots: list[dict[str, Any]] = []

    if os_type == OSType.WINDOWS:
        pf = os.environ.get("ProgramFiles")
        pf86 = os.environ.get("ProgramFiles(x86)")
        lad = os.environ.get("LOCALAPPDATA")
        pd = os.environ.get("ProgramData")

        if pf:
            roots.append({"path": pf, "enabled": True, "recursive": True, "max_depth": 5, "label": "Program Files"})
        if pf86:
            roots.append({"path": pf86, "enabled": True, "recursive": True, "max_depth": 5, "label": "Program Files (x86)"})
        if lad:
            roots.append({"path": lad, "enabled": False, "recursive": True, "max_depth": 4, "label": "LocalAppData"})
        if pd:
            roots.append({"path": pd, "enabled": False, "recursive": True, "max_depth": 4, "label": "ProgramData"})

        home = str(Path.home())
        roots.append({"path": str(Path(home) / "Desktop"), "enabled": False, "recursive": True, "max_depth": 3, "label": "Desktop"})
        roots.append({"path": str(Path(home) / "Downloads"), "enabled": False, "recursive": True, "max_depth": 3, "label": "Downloads"})
        roots.append({"path": str(Path(home) / "Documents"), "enabled": False, "recursive": True, "max_depth": 3, "label": "Documents"})

    else:  # Linux/Unknown
        home = Path.home()
        roots.append({"path": str(home / "Games"), "enabled": False, "recursive": True, "max_depth": 6, "label": "Games"})
        roots.append({"path": str(home / ".local" / "bin"), "enabled": False, "recursive": True, "max_depth": 2, "label": "~/.local/bin"})
        roots.append({"path": str(home / "Downloads"), "enabled": False, "recursive": True, "max_depth": 3, "label": "Downloads"})

    existing: list[dict[str, Any]] = []
    for r in roots:
        if Path(r["path"]).exists():
            existing.append(r)
    return existing


def load_config() -> dict[str, Any]:
    p = config_path()
    if not p.exists():
        return {
            "roots": default_roots(),
            "exclude_dir_names": sorted(DEFAULT_EXCLUDED_DIR_NAMES),
            "steam_enabled": True,
        }
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {
            "roots": default_roots(),
            "exclude_dir_names": sorted(DEFAULT_EXCLUDED_DIR_NAMES),
            "steam_enabled": True,
        }


def save_config(cfg: dict[str, Any]) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

def _is_linux_executable(path: Path) -> bool:
    try:
        return path.is_file() and os.access(str(path), os.X_OK)
    except Exception:
        return False


def discover_filesystem_apps_optin(
    roots: list[dict[str, Any]],
    excluded_dir_names: set[str],
) -> list[DiscoveredApp]:
    os_type = get_os()
    exts = set(executable_extensions())  # windows uses extensions; linux includes scripts (.sh/.py)
    discovered: list[DiscoveredApp] = []

    for r in roots:
        if not r.get("enabled", False):
            continue

        root = Path(r["path"]).expanduser()
        if not root.exists():
            continue

        max_depth = int(r.get("max_depth", 3))
        recursive = bool(r.get("recursive", True))

        if not recursive:
            max_depth = 1

        for dirpath, dirnames, filenames in os.walk(root):
            dp = Path(dirpath)

            try:
                depth = len(dp.relative_to(root).parts)
            except ValueError:
                continue

            dirnames[:] = [d for d in dirnames if d.lower() not in excluded_dir_names]

            if depth >= max_depth:
                dirnames[:] = []

            for fn in filenames:
                p = dp / fn

                # Windows: extension-based
                if os_type == OSType.WINDOWS:
                    if p.suffix.lower() not in exts:
                        continue

                # Linux: allow scripts by extension OR executable-bit files (ELF, AppImage, etc.)
                elif os_type == OSType.LINUX:
                    if p.suffix.lower() not in exts and not _is_linux_executable(p):
                        continue

                else:
                    if p.suffix.lower() not in exts:
                        continue

                discovered.append(DiscoveredApp(name=p.stem, path=p))

    return discovered

def apps_to_json(apps: list[DiscoveredApp]) -> str:
    def encode(a: DiscoveredApp) -> dict[str, Any]:
        return {"name": a.name, "path": str(a.path)}
    return json.dumps([encode(a) for a in apps], indent=2)


def print_apps(apps: list[DiscoveredApp]) -> None:
    for a in apps:
        print(f"- {a.name} @ {a.path}")


# -----------------------------
# CLI commands
#------------------------------
def cmd_roots_list(args: argparse.Namespace) -> int:
    cfg = load_config()
    roots = cfg.get("roots", [])
    if not roots:
        print("(no roots configured)")
        return 0

    for r in roots:
        status = "ON " if r.get("enabled") else "OFF"
        label = r.get("label") or ""
        md = r.get("max_depth", "")
        print(f"[{status}] {r.get('path')}  max_depth={md}  {label}".rstrip())
    return 0


def _normalize_path(s: str) -> str:
    return str(Path(s).expanduser().resolve())


def cmd_roots_add(args: argparse.Namespace) -> int:
    cfg = load_config()
    roots: list[dict[str, Any]] = cfg.get("roots", [])

    p = _normalize_path(args.path)
    if any(_normalize_path(r["path"]) == p for r in roots):
        print("Already present:", p)
        return 0

    roots.append({
        "path": p,
        "enabled": True if args.enable else False if args.disable else True,
        "recursive": True,
        "max_depth": args.max_depth,
        "label": args.label or "Custom",
    })
    cfg["roots"] = roots
    save_config(cfg)
    print("Added root:", p)
    return 0


def cmd_roots_enable_disable(args: argparse.Namespace, enabled: bool) -> int:
    cfg = load_config()
    roots: list[dict[str, Any]] = cfg.get("roots", [])

    target = _normalize_path(args.path)
    hit = False
    for r in roots:
        if _normalize_path(r["path"]) == target:
            r["enabled"] = enabled
            hit = True

    if not hit:
        print("No such root:", target)
        return 1

    cfg["roots"] = roots
    save_config(cfg)
    print(("Enabled" if enabled else "Disabled") + ":", target)
    return 0


def cmd_roots_remove(args: argparse.Namespace) -> int:
    cfg = load_config()
    roots: list[dict[str, Any]] = cfg.get("roots", [])

    target = _normalize_path(args.path)
    new_roots = [r for r in roots if _normalize_path(r["path"]) != target]

    if len(new_roots) == len(roots):
        print("No such root:", target)
        return 1

    cfg["roots"] = new_roots
    save_config(cfg)
    print("Removed:", target)
    return 0


def cmd_roots_reset(args: argparse.Namespace) -> int:
    cfg = load_config()
    cfg["roots"] = default_roots()
    cfg["exclude_dir_names"] = sorted(DEFAULT_EXCLUDED_DIR_NAMES)
    cfg["steam_enabled"] = True
    save_config(cfg)
    print("Reset roots to defaults for", get_os().value)
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    cfg = load_config()

    excluded = set(cfg.get("exclude_dir_names", []))
    roots = cfg.get("roots", [])

    apps: list[DiscoveredApp] = []

    steam_enabled = bool(cfg.get("steam_enabled", True))
    if args.no_steam:
        steam_enabled = False
    if args.steam:
        steam_enabled = True

    fs_enabled = not args.no_filesystem

    if steam_enabled:
        steam_apps = find_installed_steam_apps()
        apps.extend(steam_apps_to_discovered(steam_apps))

    if fs_enabled:
        apps.extend(discover_filesystem_apps_optin(roots=roots, excluded_dir_names=excluded))


def cmd_steam_libs(args: argparse.Namespace) -> int:
    libs = find_steam_libraries()
    if not libs:
        print("(no steam libraries found)")
        return 0
    for lib in libs:
        print("-", lib)
    return 0


def cmd_sensor_test(args: argparse.Namespace) -> int:
    from app.sensors import SensorStub
    from app.utils.state import StateMachine

    sensor = SensorStub()
    sm = StateMachine()

    print("Press ENTER to toggle sensor state. Ctrl+C to exit.")
    try:
        while True:
            input()
            sensor.toggle()
            sm.update(sensor.read())
    except KeyboardInterrupt:
        print("\nExiting.")
        return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="uvrl-hi", description="UVRL human interface (CLI-first).")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("roots", help="Manage opt-in filesystem discovery roots.")
    rsub = pr.add_subparsers(dest="roots_cmd", required=True)

    rsub.add_parser("list", help="List configured roots.").set_defaults(func=cmd_roots_list)

    pa = rsub.add_parser("add", help="Add a custom root path.")
    pa.add_argument("path")
    pa.add_argument("--label", default="")
    pa.add_argument("--max-depth", type=int, default=4)
    g = pa.add_mutually_exclusive_group()
    g.add_argument("--enable", action="store_true")
    g.add_argument("--disable", action="store_true")
    pa.set_defaults(func=cmd_roots_add)

    pe = rsub.add_parser("enable", help="Enable an existing root.")
    pe.add_argument("path")
    pe.set_defaults(func=lambda a: cmd_roots_enable_disable(a, True))

    pd = rsub.add_parser("disable", help="Disable an existing root.")
    pd.add_argument("path")
    pd.set_defaults(func=lambda a: cmd_roots_enable_disable(a, False))

    prm = rsub.add_parser("remove", help="Remove a root.")
    prm.add_argument("path")
    prm.set_defaults(func=cmd_roots_remove)

    rsub.add_parser("reset", help="Reset roots to OS defaults.").set_defaults(func=cmd_roots_reset)

    pdv = sub.add_parser("discover", help="Discover apps (Steam + filesystem).")
    pdv.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable output.")
    pdv.add_argument("--steam", action="store_true", help="Force-enable Steam discovery.")
    pdv.add_argument("--no-steam", action="store_true", help="Disable Steam discovery.")
    pdv.add_argument("--no-filesystem", action="store_true", help="Disable filesystem discovery.")
    pdv.set_defaults(func=cmd_discover)

    ps = sub.add_parser("steam", help="Steam-related info.")
    ssub = ps.add_subparsers(dest="steam_cmd", required=True)
    ssub.add_parser("libs", help="List Steam libraries.").set_defaults(func=cmd_steam_libs)

    psen = sub.add_parser("sensor", help="Sensor test utilities.")
    sensub = psen.add_subparsers(dest="sensor_cmd", required=True)
    sensub.add_parser("test", help="Interactive sensor toggle test.").set_defaults(func=cmd_sensor_test)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())