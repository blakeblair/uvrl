from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path

from uvrl.app.services.database import open_database


LINUX_SCRIPT_EXTENSIONS = {
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".fish": "bash",
    ".py": "python",
}

WINDOWS_EXECUTABLE_EXTENSIONS = {
    ".exe": "native",
    ".bat": "batch",
    ".cmd": "batch",
    ".ps1": "powershell",
    ".py": "python",
}


NON_EXECUTABLE_APP_SUFFIXES = {
    ".json",
    ".dll",
    ".txt",
    ".md",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".svg",
    ".tga",
    ".dds",
    ".bmp",
    ".ico",
    ".log",
    ".ini",
    ".toml",
    ".yaml",
    ".yml",
    ".xml",
    ".cfg",
    ".conf",
    ".vdf",
    ".acf",
    ".vrsettings",
    ".vrpath",
    ".so",
    ".apk",
}


@dataclass(frozen=True)
class CatalogEntry:
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
    notes: str | None


@dataclass(frozen=True)
class ScanRoot:
    path: Path
    label: str
    depth: int | None


@dataclass(frozen=True)
class DirectoryStatus:
    path: Path
    ok: bool
    message: str
    files_seen: int = 0


@dataclass(frozen=True)
class FoundExecutable:
    display_name: str
    platform_name: str
    launch_kind: str
    source_root: Path
    catalog_id: int | None = None
    executable_path: Path | None = None
    steam_app_id: str | None = None
    flatpak_app_id: str | None = None
    default_arguments: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class FoundConfig:
    display_name: str
    platform_name: str
    file_kind: str
    file_path: Path
    source_root: Path
    catalog_id: int | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ScanResult:
    executables: list[FoundExecutable]
    configs: list[FoundConfig]
    statuses: list[DirectoryStatus]


def detect_uvrl_platform() -> str:
    system_name = platform.system().lower()

    if system_name == "linux":
        return "linux"

    if system_name == "windows":
        return "windows"

    return "any"


def load_enabled_catalog_entries() -> list[CatalogEntry]:
    uvrl_platform = detect_uvrl_platform()

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
                notes
            FROM discovery_catalog
            WHERE is_enabled = 1
              AND platform IN (?, 'any')
            ORDER BY target_kind, priority, display_name COLLATE NOCASE;
            """,
            (uvrl_platform,),
        ).fetchall()

    return [
        CatalogEntry(
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
            notes=row["notes"],
        )
        for row in rows
    ]


def recommended_scan_roots() -> list[ScanRoot]:
    uvrl_platform = detect_uvrl_platform()
    home = Path.home()

    if uvrl_platform == "linux":
        return [
            ScanRoot(Path("/usr/bin"), "System binaries", 0),
            ScanRoot(Path("/usr/local/bin"), "Local system binaries", 0),
            ScanRoot(home / ".local" / "bin", "User local binaries", 1),
            ScanRoot(home / ".local" / "share" / "applications", "Desktop app entries", 1),
            ScanRoot(home / ".local" / "share" / "Steam" / "steamapps", "Steam app manifests", 2),
            ScanRoot(home / ".local" / "share" / "Steam" / "steamapps" / "common", "Steam common apps", 2),
            ScanRoot(home / ".steam" / "steam" / "steamapps", "Alternate Steam app manifests", 2),
            ScanRoot(home / ".steam" / "steam" / "steamapps" / "common", "Alternate Steam common apps", 2),
            ScanRoot(home / ".config", "User config directory", 2),
            ScanRoot(home / ".local" / "share", "User local share", 2),
            ScanRoot(home / ".local" / "share" / "Steam" / "userdata", "Steam userdata configs", 4),
        ]

    if uvrl_platform == "windows":
        candidates: list[ScanRoot] = []

        program_files = os.environ.get("ProgramFiles")
        program_files_x86 = os.environ.get("ProgramFiles(x86)")
        local_app_data = os.environ.get("LOCALAPPDATA")
        app_data = os.environ.get("APPDATA")
        program_data = os.environ.get("ProgramData")

        if program_files:
            candidates.append(ScanRoot(Path(program_files), "Program Files", 3))

        if program_files_x86:
            candidates.append(ScanRoot(Path(program_files_x86), "Program Files x86", 3))

        if local_app_data:
            candidates.append(ScanRoot(Path(local_app_data), "Local AppData", 2))
            candidates.append(ScanRoot(Path(local_app_data) / "Programs", "User local programs", 3))

        if app_data:
            candidates.append(ScanRoot(Path(app_data), "Roaming AppData", 2))

        if program_data:
            candidates.append(ScanRoot(Path(program_data), "ProgramData", 2))

        candidates.extend(
            [
                ScanRoot(home / "Desktop", "Desktop", 1),
                ScanRoot(home / "Downloads", "Downloads", 1),
            ]
        )

        return candidates

    return [
        ScanRoot(home, "Home directory", 1),
    ]


def _prompt_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"

    while True:
        answer = input(f"{prompt} {suffix} ").strip().lower()

        if not answer:
            return default

        if answer in {"y", "yes"}:
            return True

        if answer in {"n", "no"}:
            return False

        print("Enter y or n.")


def _prompt_depth(default: int | None) -> int | None:
    default_text = _format_depth(default)

    while True:
        print("Recursion depth options:")
        print("  none     = no recursion. Only scan files directly inside this directory.")
        print("  number   = scan that many directory levels below this directory.")
        print("  full     = infinite recursion. Scan all subdirectories.")
        answer = input(f"Depth none, number, or full [{default_text}]: ").strip().lower()

        if not answer:
            return default

        if answer in {"none", "no", "n", "0"}:
            return 0

        if answer in {"full", "f", "all", "*", "infinite", "infinity"}:
            return None

        try:
            value = int(answer)
        except ValueError:
            print("Depth must be none, a non-negative integer, or full.")
            continue

        if value < 0:
            print("Depth must not be negative.")
            continue

        return value


def _format_depth(depth: int | None) -> str:
    if depth is None:
        return "full"

    if depth == 0:
        return "none"

    return str(depth)


def _read_path(prompt: str) -> Path | None:
    raw = input(prompt).strip()

    if not raw:
        return None

    return Path(raw).expanduser()


def _print_scan_roots(roots: list[ScanRoot]) -> None:
    if not roots:
        print("No scan directories selected.")
        return

    print("Selected scan directories:")

    for index, root in enumerate(roots, start=1):
        exists_text = "exists" if root.path.exists() else "missing"
        print(
            f"  [{index}] {root.label}: {root.path} "
            f"(depth {_format_depth(root.depth)}, {exists_text})"
        )


def choose_scan_roots_interactively() -> list[ScanRoot]:
    print(f"Detected platform: {detect_uvrl_platform()}")
    print()
    print("Recommended scan directories:")

    roots: list[ScanRoot] = []

    for candidate in recommended_scan_roots():
        exists_text = "exists" if candidate.path.exists() else "missing"
        include = _prompt_yes_no(
            f"Include {candidate.label}: {candidate.path} ({exists_text}, depth {_format_depth(candidate.depth)})?",
            default=candidate.path.exists(),
        )

        if include:
            roots.append(candidate)

    while _prompt_yes_no("Add another custom directory?", default=False):
        path = _read_path("Directory path: ")

        if path is None:
            continue

        label = input("Label: ").strip() or "Custom directory"
        depth = _prompt_depth(default=2)
        roots.append(ScanRoot(path=path, label=label, depth=depth))

    return review_scan_roots_interactively(roots)


def review_scan_roots_interactively(roots: list[ScanRoot]) -> list[ScanRoot]:
    while True:
        print()
        _print_scan_roots(roots)
        print()
        print("Options:")
        print("  c = confirm")
        print("  a = add directory")
        print("  r = remove directory")
        print("  d = change depth")
        print("  q = quit scan")

        choice = input("Choose: ").strip().lower()

        if choice == "c":
            if not roots:
                print("Select at least one directory before confirming.")
                continue

            return roots

        if choice == "q":
            return []

        if choice == "a":
            path = _read_path("Directory path: ")

            if path is None:
                continue

            label = input("Label: ").strip() or "Custom directory"
            depth = _prompt_depth(default=2)
            roots.append(ScanRoot(path=path, label=label, depth=depth))
            continue

        if choice == "r":
            index_text = input("Remove directory number: ").strip()

            try:
                index = int(index_text)
            except ValueError:
                print("Enter a number.")
                continue

            if index < 1 or index > len(roots):
                print("Invalid directory number.")
                continue

            removed = roots.pop(index - 1)
            print(f"Removed: {removed.path}")
            continue

        if choice == "d":
            index_text = input("Change depth for directory number: ").strip()

            try:
                index = int(index_text)
            except ValueError:
                print("Enter a number.")
                continue

            if index < 1 or index > len(roots):
                print("Invalid directory number.")
                continue

            root = roots[index - 1]
            depth = _prompt_depth(default=root.depth)
            roots[index - 1] = ScanRoot(path=root.path, label=root.label, depth=depth)
            continue

        print("Unknown option.")


def _iter_files_limited(root: Path, depth: int | None) -> tuple[list[Path], list[DirectoryStatus]]:
    files: list[Path] = []
    statuses: list[DirectoryStatus] = []

    root = root.expanduser()

    if not root.exists():
        return files, [DirectoryStatus(path=root, ok=False, message="Path does not exist.")]

    if not root.is_dir():
        return files, [DirectoryStatus(path=root, ok=False, message="Path is not a directory.")]

    def on_error(error: OSError) -> None:
        error_path = Path(error.filename) if error.filename else root
        statuses.append(
            DirectoryStatus(
                path=error_path,
                ok=False,
                message=f"Cannot access: {error.strerror or error}",
            )
        )

    try:
        for current_dir, dir_names, file_names in os.walk(
            root,
            topdown=True,
            followlinks=False,
            onerror=on_error,
        ):
            current_path = Path(current_dir)

            try:
                relative = current_path.relative_to(root)
                current_depth = 0 if str(relative) == "." else len(relative.parts)
            except ValueError:
                current_depth = 0

            if depth is not None and current_depth >= depth:
                dir_names[:] = []

            for file_name in file_names:
                files.append(current_path / file_name)

    except OSError as error:
        statuses.append(
            DirectoryStatus(
                path=root,
                ok=False,
                message=f"Search failed: {error}",
                files_seen=len(files),
            )
        )
        return files, statuses

    statuses.insert(
        0,
        DirectoryStatus(
            path=root,
            ok=True,
            message="Searched successfully.",
            files_seen=len(files),
        ),
    )

    return files, statuses


def _is_linux_executable(path: Path) -> bool:
    try:
        return path.is_file() and os.access(path, os.X_OK)
    except OSError:
        return False


def _is_windows_executable_candidate(path: Path) -> bool:
    return path.suffix.lower() in WINDOWS_EXECUTABLE_EXTENSIONS


def _is_linux_executable_candidate(path: Path, launch_kind: str | None) -> bool:
    if launch_kind == "python":
        return path.suffix.lower() == ".py"

    if launch_kind == "bash":
        return path.suffix.lower() in LINUX_SCRIPT_EXTENSIONS

    return _is_linux_executable(path)


def _is_executable_candidate(path: Path, entry: CatalogEntry, uvrl_platform: str) -> bool:
    if entry.match_type in {"steam_app_id", "flatpak_app_id"}:
        return True

    if any(suffix.lower() in NON_EXECUTABLE_APP_SUFFIXES for suffix in path.suffixes):
        return False

    if uvrl_platform == "windows":
        return _is_windows_executable_candidate(path)

    if uvrl_platform == "linux":
        return _is_linux_executable_candidate(path, entry.launch_kind)

    return path.is_file()


def _matches_steam_app_id(path: Path, steam_app_id: str) -> bool:
    expected = f"appmanifest_{steam_app_id}.acf"
    return path.name.lower() == expected.lower()


def _normalize_path_text(value: str) -> str:
    return value.lower().replace(chr(92), "/")


def _path_tail_matches(path_text: str, match_value: str) -> bool:
    clean_path = _normalize_path_text(path_text).rstrip("/")
    clean_match = _normalize_path_text(match_value).strip("/")

    return clean_path == clean_match or clean_path.endswith(f"/{clean_match}")


def _matches_catalog_entry(path: Path, entry: CatalogEntry) -> bool:
    match_value = _normalize_path_text(entry.match_value)
    filename = path.name.lower()
    path_text = _normalize_path_text(str(path))

    if entry.target_kind == "config":
        if entry.match_type == "filename_exact":
            return filename == match_value

        if entry.match_type == "filename_contains":
            return match_value in filename

        if entry.match_type == "path_contains":
            return _path_tail_matches(path_text, match_value)

        if entry.match_type == "steam_app_id":
            return _matches_steam_app_id(path, entry.match_value)

        if entry.match_type == "flatpak_app_id":
            return _path_tail_matches(path_text, match_value)

        return False

    if entry.match_type == "filename_exact":
        return filename == match_value

    if entry.match_type == "filename_contains":
        return match_value in filename

    if entry.match_type == "path_contains":
        return match_value in path_text

    if entry.match_type == "steam_app_id":
        return _matches_steam_app_id(path, entry.match_value)

    if entry.match_type == "flatpak_app_id":
        return match_value in path_text

    return False


def _found_executable_from_match(
    path: Path,
    entry: CatalogEntry,
    source_root: Path,
    uvrl_platform: str,
) -> FoundExecutable | None:
    if not _is_executable_candidate(path, entry, uvrl_platform):
        return None

    launch_kind = entry.launch_kind or "native"

    if uvrl_platform == "linux" and path.suffix.lower() == ".desktop":
        launch_kind = "custom"

    executable_path: Path | None = path
    steam_app_id = entry.steam_app_id
    flatpak_app_id = entry.flatpak_app_id

    if entry.match_type == "steam_app_id":
        launch_kind = "steam_app"
        steam_app_id = entry.steam_app_id or entry.match_value
        executable_path = None

    if entry.match_type == "flatpak_app_id":
        launch_kind = "flatpak"
        flatpak_app_id = entry.flatpak_app_id or entry.match_value
        executable_path = None

    return FoundExecutable(
        display_name=entry.display_name,
        platform_name=uvrl_platform if entry.platform == "any" else entry.platform,
        launch_kind=launch_kind,
        executable_path=executable_path,
        steam_app_id=steam_app_id,
        flatpak_app_id=flatpak_app_id,
        source_root=source_root,
        catalog_id=entry.discovery_catalog_id,
        notes=entry.notes,
    )


def _found_config_from_match(
    path: Path,
    entry: CatalogEntry,
    source_root: Path,
    uvrl_platform: str,
) -> FoundConfig:
    return FoundConfig(
        display_name=entry.display_name,
        platform_name=uvrl_platform if entry.platform == "any" else entry.platform,
        file_kind=entry.file_kind or "unknown",
        file_path=path,
        source_root=source_root,
        catalog_id=entry.discovery_catalog_id,
        notes=entry.notes,
    )



def _match_files_against_catalog(
    files: list[Path],
    root: ScanRoot,
    catalog_entries: list[CatalogEntry],
    uvrl_platform: str,
) -> tuple[list[FoundExecutable], list[FoundConfig]]:
    executables: list[FoundExecutable] = []
    configs: list[FoundConfig] = []

    for path in files:
        try:
            if not path.is_file():
                continue
        except OSError:
            continue

        for entry in catalog_entries:
            if not _matches_catalog_entry(path, entry):
                continue

            if entry.target_kind == "app":
                found = _found_executable_from_match(
                    path=path,
                    entry=entry,
                    source_root=root.path,
                    uvrl_platform=uvrl_platform,
                )

                if found is not None:
                    executables.append(found)

            elif entry.target_kind == "config":
                configs.append(
                    _found_config_from_match(
                        path=path,
                        entry=entry,
                        source_root=root.path,
                        uvrl_platform=uvrl_platform,
                    )
                )

    return executables, configs

def _flatpak_is_available() -> bool:
    return Path("/usr/bin/flatpak").exists()


def _list_installed_flatpak_app_ids() -> set[str]:
    if not _flatpak_is_available():
        return set()

    result = subprocess.run(
        ["flatpak", "list", "--app", "--columns=application"],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        return set()

    return {
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    }


def _flatpak_desktop_file_candidates(app_id: str) -> list[Path]:
    return [
        Path.home() / ".local" / "share" / "flatpak" / "exports" / "share" / "applications" / f"{app_id}.desktop",
        Path("/var/lib/flatpak/exports/share/applications") / f"{app_id}.desktop",
        Path.home() / ".local" / "share" / "applications" / f"{app_id}.desktop",
    ]


def _read_flatpak_exec_line(app_id: str) -> str | None:
    for desktop_file in _flatpak_desktop_file_candidates(app_id):
        if not desktop_file.exists():
            continue

        try:
            for line in desktop_file.read_text(errors="ignore").splitlines():
                if line.startswith("Exec="):
                    return line.removeprefix("Exec=").strip()
        except OSError:
            continue

    return None


def _flatpak_default_arguments(app_id: str) -> str:
    exec_line = _read_flatpak_exec_line(app_id)

    if exec_line:
        if exec_line.startswith("/usr/bin/flatpak "):
            return exec_line.removeprefix("/usr/bin/flatpak ").strip()

        if exec_line.startswith("flatpak "):
            return exec_line.removeprefix("flatpak ").strip()

    return f"run {app_id}"


def _discover_flatpak_apps_from_catalog(
    catalog_entries: list[CatalogEntry],
    uvrl_platform: str,
) -> list[FoundExecutable]:
    if uvrl_platform != "linux":
        return []

    installed_app_ids = _list_installed_flatpak_app_ids()

    if not installed_app_ids:
        return []

    found: list[FoundExecutable] = []

    for entry in catalog_entries:
        if entry.target_kind != "app":
            continue

        if entry.match_type != "flatpak_app_id":
            continue

        app_id = entry.flatpak_app_id or entry.match_value

        if app_id not in installed_app_ids:
            continue

        found.append(
            FoundExecutable(
                display_name=entry.display_name,
                platform_name="linux",
                launch_kind="flatpak",
                executable_path=None,
                flatpak_app_id=app_id,
                default_arguments=_flatpak_default_arguments(app_id),
                source_root=Path("/var/lib/flatpak/app"),
                catalog_id=entry.discovery_catalog_id,
                notes=entry.notes,
            )
        )

    return found


def scan_roots(roots: list[ScanRoot]) -> ScanResult:
    uvrl_platform = detect_uvrl_platform()
    catalog_entries = load_enabled_catalog_entries()

    all_executables: list[FoundExecutable] = _discover_flatpak_apps_from_catalog(
        catalog_entries=catalog_entries,
        uvrl_platform=uvrl_platform,
    )
    all_configs: list[FoundConfig] = []
    all_statuses: list[DirectoryStatus] = []

    seen_executables: set[tuple[str, str | None, str | None, str | None]] = set()

    for executable in all_executables:
        executable_path = str(executable.executable_path.resolve()) if executable.executable_path else None
        seen_executables.add(
            (
                executable.display_name,
                executable_path,
                executable.steam_app_id,
                executable.flatpak_app_id,
            )
        )

    seen_configs: set[str] = set()

    for root in roots:
        files, statuses = _iter_files_limited(root.path, root.depth)
        all_statuses.extend(statuses)

        if not any(status.ok for status in statuses):
            continue

        executables, configs = _match_files_against_catalog(
            files=files,
            root=root,
            catalog_entries=catalog_entries,
            uvrl_platform=uvrl_platform,
        )

        for executable in executables:
            executable_path = str(executable.executable_path.resolve()) if executable.executable_path else None
            key = (
                executable.display_name,
                executable_path,
                executable.steam_app_id,
                executable.flatpak_app_id,
            )

            if key in seen_executables:
                continue

            seen_executables.add(key)
            all_executables.append(executable)

        for config in configs:
            try:
                key = str(config.file_path.resolve())
            except OSError:
                key = str(config.file_path)

            if key in seen_configs:
                continue

            seen_configs.add(key)
            all_configs.append(config)

    all_executables.sort(key=lambda item: (item.display_name.lower(), str(item.executable_path or "")))
    all_configs.sort(key=lambda item: (item.display_name.lower(), str(item.file_path)))

    return ScanResult(
        executables=all_executables,
        configs=all_configs,
        statuses=all_statuses,
    )


def _print_statuses(statuses: list[DirectoryStatus]) -> None:
    print()
    print("Directory search status:")

    for status in statuses:
        prefix = "OK" if status.ok else "FAILED"
        print(f"  {prefix}: {status.path}")
        print(f"    {status.message}")
        print(f"    files seen: {status.files_seen}")


def _print_executables(executables: list[FoundExecutable]) -> None:
    print()
    print("Catalog-matched executables:")

    if not executables:
        print("  none")
        return

    for index, executable in enumerate(executables, start=1):
        print(
            f"  [{index}] {executable.display_name} "
            f"({executable.launch_kind}, {executable.platform_name})"
        )

        if executable.catalog_id is not None:
            print(f"      catalog: {executable.catalog_id}")

        if executable.executable_path is not None:
            print(f"      path:    {executable.executable_path}")

        if executable.steam_app_id:
            print(f"      steam:   {executable.steam_app_id}")

        if executable.flatpak_app_id:
            print(f"      flatpak: {executable.flatpak_app_id}")

        if executable.default_arguments:
            print(f"      args:    {executable.default_arguments}")


def _print_configs(configs: list[FoundConfig]) -> None:
    print()
    print("Catalog-matched configs:")

    if not configs:
        print("  none")
        return

    for index, config in enumerate(configs, start=1):
        print(f"  [{index}] {config.display_name} ({config.file_kind}, {config.platform_name})")

        if config.catalog_id is not None:
            print(f"      catalog: {config.catalog_id}")

        print(f"      path:    {config.file_path}")


def _parse_number_list(text: str, max_value: int) -> set[int]:
    values: set[int] = set()

    if not text.strip():
        return values

    for part in text.replace(",", " ").split():
        try:
            value = int(part)
        except ValueError:
            print(f"Ignoring invalid number: {part}")
            continue

        if value < 1 or value > max_value:
            print(f"Ignoring out of range number: {value}")
            continue

        values.add(value)

    return values


def _manual_executable_from_prompt() -> FoundExecutable | None:
    path = _read_path("Executable path, or blank to cancel: ")

    if path is None:
        return None

    display_name = input("Display name: ").strip() or path.stem or path.name
    uvrl_platform = detect_uvrl_platform()

    guessed_kind = "native"

    if uvrl_platform == "windows":
        guessed_kind = WINDOWS_EXECUTABLE_EXTENSIONS.get(path.suffix.lower(), "native")
    elif uvrl_platform == "linux":
        guessed_kind = LINUX_SCRIPT_EXTENSIONS.get(path.suffix.lower(), "native")

    launch_kind = input(f"Launch kind [{guessed_kind}]: ").strip() or guessed_kind

    return FoundExecutable(
        display_name=display_name,
        platform_name=uvrl_platform,
        launch_kind=launch_kind,
        executable_path=path,
        source_root=path.parent,
        notes="Manually added during scan review.",
    )


def _manual_config_from_prompt() -> FoundConfig | None:
    path = _read_path("Config path, or blank to cancel: ")

    if path is None:
        return None

    display_name = input("Display name: ").strip() or path.name
    file_kind = input("Config kind [unknown]: ").strip() or "unknown"

    return FoundConfig(
        display_name=display_name,
        platform_name=detect_uvrl_platform(),
        file_kind=file_kind,
        file_path=path,
        source_root=path.parent,
        notes="Manually added during scan review.",
    )


def review_found_results_interactively(
    result: ScanResult,
) -> tuple[list[FoundExecutable], list[FoundConfig]]:
    executables = list(result.executables)
    configs = list(result.configs)

    while True:
        _print_statuses(result.statuses)
        _print_executables(executables)
        _print_configs(configs)

        print()
        print("Result review options:")
        print("  c = confirm and save")
        print("  re = remove executables")
        print("  rc = remove configs")
        print("  ae = add executable manually")
        print("  ac = add config manually")
        print("  q = quit without saving")

        choice = input("Choose: ").strip().lower()

        if choice == "c":
            return executables, configs

        if choice == "q":
            return [], []

        if choice == "re":
            numbers = _parse_number_list(
                input("Executable numbers to remove: "),
                len(executables),
            )
            executables = [
                executable
                for index, executable in enumerate(executables, start=1)
                if index not in numbers
            ]
            continue

        if choice == "rc":
            numbers = _parse_number_list(
                input("Config numbers to remove: "),
                len(configs),
            )
            configs = [
                config
                for index, config in enumerate(configs, start=1)
                if index not in numbers
            ]
            continue

        if choice == "ae":
            executable = _manual_executable_from_prompt()

            if executable is not None:
                executables.append(executable)

            continue

        if choice == "ac":
            config = _manual_config_from_prompt()

            if config is not None:
                configs.append(config)

            continue

        print("Unknown option.")


def _save_executable(executable: FoundExecutable) -> bool:
    executable_path: str | None = None
    working_directory: str | None = None

    if executable.executable_path is not None:
        try:
            executable_path = str(executable.executable_path.expanduser().resolve())
        except OSError:
            executable_path = str(executable.executable_path.expanduser())

    if executable.executable_path is not None and executable_path is not None:
        working_directory = str(Path(executable_path).parent)

    with open_database() as database:
        cursor = database.execute(
            """
            INSERT OR IGNORE INTO app_registry (
                display_name,
                launch_kind,
                platform,
                executable_path,
                working_directory,
                steam_app_id,
                flatpak_app_id,
                default_arguments,
                source,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                executable.display_name,
                executable.launch_kind,
                executable.platform_name,
                executable_path,
                working_directory,
                executable.steam_app_id,
                executable.flatpak_app_id,
                executable.default_arguments,
                "discovered",
                executable.notes,
            ),
        )

        return cursor.rowcount > 0


def _save_config(config: FoundConfig) -> bool:
    try:
        file_path = str(config.file_path.expanduser().resolve())
    except OSError:
        file_path = str(config.file_path.expanduser())

    with open_database() as database:
        cursor = database.execute(
            """
            INSERT OR IGNORE INTO config_locations (
                display_name,
                file_path,
                platform,
                file_kind,
                notes
            )
            VALUES (?, ?, ?, ?, ?);
            """,
            (
                config.display_name,
                file_path,
                config.platform_name,
                config.file_kind,
                config.notes,
            ),
        )

        return cursor.rowcount > 0


def save_confirmed_scan_results(
    executables: list[FoundExecutable],
    configs: list[FoundConfig],
) -> None:
    saved_executables = 0
    skipped_executables = 0
    saved_configs = 0
    skipped_configs = 0

    for executable in executables:
        if _save_executable(executable):
            saved_executables += 1
        else:
            skipped_executables += 1

    for config in configs:
        if _save_config(config):
            saved_configs += 1
        else:
            skipped_configs += 1

    print()
    print("Saved scan results:")
    print(f"  executables saved: {saved_executables}")
    print(f"  executables skipped as duplicates: {skipped_executables}")
    print(f"  configs saved: {saved_configs}")
    print(f"  configs skipped as duplicates: {skipped_configs}")


def run_scan_wizard() -> None:
    catalog_entries = load_enabled_catalog_entries()

    if not catalog_entries:
        print("No enabled discovery catalog entries found.")
        return

    print(f"Loaded {len(catalog_entries)} enabled discovery catalog entries.")
    print("Scanner will only show files matching the catalog.")
    print()

    roots = choose_scan_roots_interactively()

    if not roots:
        print("Scan cancelled. No directories selected.")
        return

    print()
    print("Scanning. This may take a moment.")
    result = scan_roots(roots)

    executables, configs = review_found_results_interactively(result)

    if not executables and not configs:
        print("No confirmed results to save.")
        return

    if not _prompt_yes_no("Save confirmed executables and configs to UVRL?", default=False):
        print("Scan results not saved.")
        return

    save_confirmed_scan_results(executables, configs)
