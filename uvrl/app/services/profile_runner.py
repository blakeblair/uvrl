from __future__ import annotations

import csv
import os
import shlex
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from uvrl.app.services.config_apply import apply_config_variant
from uvrl.app.services.config_backups import restore_config_from_backup
from uvrl.app.services.database import open_database
from uvrl.app.services.profile_validation import validate_profile
from uvrl.app.services.profiles import ProfileStep, list_profile_steps


def _split_args(argument_text: str | None) -> list[str]:
    if not argument_text:
        return []

    return shlex.split(argument_text, posix=not sys.platform.startswith("win"))


def _get_app_row(app_id: int):
    with open_database() as database:
        row = database.execute(
            """
            SELECT
                app_id,
                display_name,
                launch_kind,
                platform,
                executable_path,
                working_directory,
                default_arguments,
                steam_app_id,
                flatpak_app_id
            FROM app_registry
            WHERE app_id = ?
              AND is_hidden = 0;
            """,
            (app_id,),
        ).fetchone()

    if row is None:
        raise ValueError(f"No active app found with ID {app_id}")

    return row


def _launch_executable_step(step: ProfileStep, dry_run: bool) -> None:
    if step.app_id is None:
        raise ValueError("launch_executable step has no app_id.")

    app = _get_app_row(step.app_id)

    display_name = str(app["display_name"])
    launch_kind = str(app["launch_kind"])
    executable_path = app["executable_path"]
    working_directory = step.launch_working_directory or app["working_directory"]

    default_args = _split_args(app["default_arguments"])
    step_args = _split_args(step.launch_arguments)
    arguments = default_args + step_args

    if launch_kind == "steam_app":
        steam_app_id = app["steam_app_id"]

        if not steam_app_id:
            raise ValueError(f"Steam app [{step.app_id}] has no steam_app_id.")

        steam_url = f"steam://rungameid/{steam_app_id}"

        if dry_run:
            print(f"  would open Steam URL: {steam_url}")
            return

        opened = webbrowser.open(steam_url)

        if not opened:
            raise RuntimeError(f"Failed to open Steam URL: {steam_url}")

        print(f"  opened Steam URL: {steam_url}")
        return

    if launch_kind == "flatpak":
        flatpak_app_id = app["flatpak_app_id"]

        if not flatpak_app_id:
            raise ValueError(f"Flatpak app [{step.app_id}] has no flatpak_app_id.")

        if default_args:
            command = ["flatpak", *default_args, *step_args]
        else:
            command = ["flatpak", "run", str(flatpak_app_id), *step_args]

    elif launch_kind == "python":
        if not executable_path:
            raise ValueError(f"Python app [{step.app_id}] has no executable_path.")

        command = [sys.executable, str(Path(executable_path).expanduser()), *arguments]

    elif launch_kind == "bash":
        if not executable_path:
            raise ValueError(f"Bash app [{step.app_id}] has no executable_path.")

        command = ["bash", str(Path(executable_path).expanduser()), *arguments]

    elif launch_kind == "powershell":
        if not executable_path:
            raise ValueError(f"PowerShell app [{step.app_id}] has no executable_path.")

        shell_command = "powershell" if sys.platform.startswith("win") else "pwsh"
        command = [shell_command, str(Path(executable_path).expanduser()), *arguments]

    elif launch_kind == "batch":
        if not executable_path:
            raise ValueError(f"Batch app [{step.app_id}] has no executable_path.")

        if not sys.platform.startswith("win"):
            raise RuntimeError("Batch files are only supported on Windows.")

        command = [str(Path(executable_path).expanduser()), *arguments]

    elif launch_kind == "native":
        if not executable_path:
            raise ValueError(f"App [{step.app_id}] has no executable_path.")

        command = [str(Path(executable_path).expanduser()), *arguments]

    elif launch_kind == "custom":
        if not executable_path:
            raise ValueError(f"App [{step.app_id}] has no executable_path.")

        custom_path = Path(executable_path).expanduser()

        if sys.platform.startswith("linux") and custom_path.suffix.lower() == ".desktop":
            if shutil.which("gio"):
                command = ["gio", "launch", str(custom_path), *arguments]
            elif shutil.which("xdg-open"):
                command = ["xdg-open", str(custom_path)]
            else:
                raise RuntimeError("Cannot launch .desktop file. Missing gio and xdg-open.")
        else:
            command = [str(custom_path), *arguments]

    else:
        raise ValueError(f"Unsupported launch_kind for app [{step.app_id}]: {launch_kind}")

    if dry_run:
        print(f"  would launch {display_name}: {command}")

        if working_directory:
            print(f"  working directory: {working_directory}")

        return

    subprocess.Popen(
        command,
        cwd=working_directory if working_directory else None,
    )

    print(f"  launched {display_name}: {command}")


def _linux_process_detected(
    process_name: str | None,
    process_path: str | None,
) -> bool:
    proc_root = Path("/proc")

    if not proc_root.exists():
        return False

    wanted_name = process_name.lower() if process_name else None
    wanted_path = str(Path(process_path).expanduser().resolve()) if process_path else None

    for child in proc_root.iterdir():
        if not child.name.isdigit():
            continue

        comm_text = ""
        exe_path = ""
        cmdline_text = ""

        try:
            comm_text = (child / "comm").read_text(errors="ignore").strip()
        except OSError:
            pass

        try:
            exe_path = str((child / "exe").resolve())
        except OSError:
            pass

        try:
            raw_cmdline = (child / "cmdline").read_bytes()
            cmdline_text = raw_cmdline.replace(b"\x00", b" ").decode(errors="ignore")
        except OSError:
            pass

        if wanted_name:
            lower_comm = comm_text.lower()
            lower_exe_name = Path(exe_path).name.lower() if exe_path else ""
            lower_cmdline = cmdline_text.lower()

            if wanted_name in {lower_comm, lower_exe_name}:
                return True

            if wanted_name in lower_cmdline:
                return True

        if wanted_path:
            if exe_path == wanted_path:
                return True

            if wanted_path in cmdline_text:
                return True

    return False


def _windows_process_detected_by_name(process_name: str) -> bool:
    result = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        return False

    reader = csv.reader(result.stdout.splitlines())

    wanted = process_name.lower()

    for row in reader:
        if not row:
            continue

        image_name = row[0].strip().lower()

        if image_name == wanted:
            return True

    return False


def _windows_process_detected_by_path(process_path: str) -> bool:
    wanted = str(Path(process_path).expanduser()).lower()

    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        "Get-CimInstance Win32_Process | Select-Object -ExpandProperty ExecutablePath",
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        return False

    for line in result.stdout.splitlines():
        if line.strip().lower() == wanted:
            return True

    return False


def _process_detected(
    process_name: str | None,
    process_path: str | None,
) -> bool:
    if sys.platform.startswith("linux"):
        return _linux_process_detected(process_name, process_path)

    if sys.platform.startswith("win"):
        if process_name and _windows_process_detected_by_name(process_name):
            return True

        if process_path and _windows_process_detected_by_path(process_path):
            return True

        return False

    if process_name:
        result = subprocess.run(
            ["pgrep", "-f", process_name],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    return False


def _wait_for_process_step(step: ProfileStep, dry_run: bool) -> None:
    process_name = step.wait_process_name
    process_path = step.wait_process_path
    timeout_seconds = step.wait_timeout_seconds

    if not process_name and not process_path:
        raise ValueError("wait_for_process step has no process name or process path.")

    if dry_run:
        print(
            "  would wait for process: "
            f"name={process_name!r}, path={process_path!r}, timeout={timeout_seconds}s"
        )
        return

    deadline = time.monotonic() + timeout_seconds

    while True:
        if _process_detected(process_name, process_path):
            print("  process detected.")
            return

        if timeout_seconds == 0 or time.monotonic() >= deadline:
            break

        time.sleep(1)

    raise TimeoutError(
        "Timed out waiting for process: "
        f"name={process_name!r}, path={process_path!r}"
    )


def _set_config_step(
    step: ProfileStep,
    dry_run: bool,
    backup_export_dir: str | None,
) -> None:
    if step.config_source_type == "variant":
        if step.config_variant_id is None:
            raise ValueError("set_config variant step has no config_variant_id.")

        if dry_run:
            print(f"  would apply config variant [{step.config_variant_id}]")
            return

        result = apply_config_variant(
            config_variant_id=step.config_variant_id,
            backup_export_dir=backup_export_dir,
        )

        if result.already_applied:
            print(f"  variant [{result.config_variant_id}] already applied.")
        else:
            print(f"  applied variant [{result.config_variant_id}] to {result.target_path}")

        if result.backup_created:
            print(f"  created pre-apply backup [{result.backup_id}]")

        elif result.matched_existing_backup_id is not None:
            print(f"  matching backup already exists [{result.matched_existing_backup_id}]")

        return

    if step.config_source_type == "backup":
        if step.config_backup_id is None:
            raise ValueError("set_config backup step has no config_backup_id.")

        if dry_run:
            print(f"  would restore/set config from backup [{step.config_backup_id}]")
            return

        result = restore_config_from_backup(
            config_backup_id=step.config_backup_id,
            create_pre_restore_backup=True,
            backup_export_dir=backup_export_dir,
        )

        print(f"  restored backup [{result.restored_backup_id}] to {result.restored_to_path}")

        if result.pre_restore_backup_created:
            print(f"  created pre-restore backup [{result.pre_restore_backup_id}]")

        elif result.matched_existing_backup_id is not None:
            print(f"  matching backup already exists [{result.matched_existing_backup_id}]")

        return

    raise ValueError(f"Unsupported set_config source: {step.config_source_type}")


def _delay_step(step: ProfileStep, dry_run: bool) -> None:
    if step.delay_seconds is None:
        raise ValueError("delay step has no delay_seconds.")

    if dry_run:
        print(f"  would delay for {step.delay_seconds} seconds")
        return

    print(f"  delaying for {step.delay_seconds} seconds")
    time.sleep(step.delay_seconds)


def _open_url_step(step: ProfileStep, dry_run: bool) -> None:
    if not step.url:
        raise ValueError("open_url step has no URL.")

    if dry_run:
        print(f"  would open URL: {step.url}")
        return

    opened = webbrowser.open(step.url)

    if not opened:
        raise RuntimeError(f"Failed to open URL: {step.url}")

    print(f"  opened URL: {step.url}")


def _print_validation_issues(profile_id: int) -> bool:
    validation = validate_profile(profile_id)

    if not validation.issues:
        return validation.is_valid

    print(f"Validation for profile [{validation.profile_id}] {validation.profile_name}:")

    for issue in validation.issues:
        location = ""

        if issue.step_id is not None:
            location = f" step [{issue.step_id}]"

            if issue.step_order is not None:
                location += f" order #{issue.step_order}"

        print(f"  {issue.severity.upper()}:{location} {issue.message}")

    return validation.is_valid


def run_profile(
    profile_id: int,
    dry_run: bool = False,
    backup_export_dir: str | None = None,
) -> None:
    """
    Run a profile step by step.

    This can overwrite config files, launch executables, wait for processes,
    delay, and open URLs.

    Elevation is left to the OS and user.
    """
    validation_ok = _print_validation_issues(profile_id)

    if not validation_ok:
        print("Profile run cancelled because validation failed.")
        return

    steps = list_profile_steps(profile_id)

    if not steps:
        print(f"Profile [{profile_id}] has no steps. Nothing to run.")
        return

    if dry_run:
        print("DRY RUN: no configs will be written, no apps launched, no URLs opened, no waits performed.")

    print(f"Running profile [{profile_id}]")

    for step in steps:
        if not step.is_enabled:
            print(f"Skipping disabled step [{step.profile_step_id}] #{step.step_order}: {step.action_type}")
            continue

        label = step.step_name or step.action_type
        print(f"Step [{step.profile_step_id}] #{step.step_order}: {label}")

        try:
            if step.action_type == "set_config":
                _set_config_step(step, dry_run=dry_run, backup_export_dir=backup_export_dir)

            elif step.action_type == "launch_executable":
                _launch_executable_step(step, dry_run=dry_run)

            elif step.action_type == "wait_for_process":
                _wait_for_process_step(step, dry_run=dry_run)

            elif step.action_type == "delay":
                _delay_step(step, dry_run=dry_run)

            elif step.action_type == "open_url":
                _open_url_step(step, dry_run=dry_run)

            else:
                raise ValueError(f"Unsupported action type: {step.action_type}")

        except Exception as error:
            print(f"  ERROR: {error}")

            if step.failure_behavior == "continue":
                print("  continuing because failure_behavior is continue.")
                continue

            print("Profile stopped.")
            return

    print("Profile run complete.")