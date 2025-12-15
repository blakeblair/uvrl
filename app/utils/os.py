import os
import platform
from enum import Enum
from pathlib import Path

class OSType(Enum):
    WINDOWS = "windows"
    LINUX = "linux"
    UNKNOWN = "unknown"


def get_os() -> OSType:
    system = platform.system().lower()

    if system == "windows":
        return OSType.WINDOWS
    elif system == "linux":
        return OSType.LINUX
    else:
        return OSType.UNKNOWN


def is_windows() -> bool:
    return get_os() == OSType.WINDOWS


def is_linux() -> bool:
    return get_os() == OSType.LINUX


def user_dirs() -> list[Path]:
    """
    User-facing directories worth scanning by default.
    """
    home = Path.home()

    dirs = [
        home / "Desktop",
        home / "Downloads",
        home / "Documents",
    ]

    # Filter to ones that actually exist
    return [d for d in dirs if d.exists()]


def executable_extensions() -> list[str]:
    """
    Extensions considered launchable on this OS.
    Steam-discovered apps bypass this entirely.
    """
    if is_windows():
        return [".exe", ".bat", ".cmd", ".ps1", ".py"]

    if is_linux():
        return [".sh", ".py"]  # ELF handled via executable bit

    return []

def get_env (env: str) -> str:
    return os.environ.get(env)


