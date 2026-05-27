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
from dataclasses import dataclass

@dataclass
class LaunchArgumentContext:
    arguments: list[str]
    mode: str

def _split_args(argument_text: str | None) -> list[str]:
    if not argument_text:
        return []

    return shlex.split(argument_text, posix=not sys.platform.startswith("win"))

def _read_desktop_exec_line(desktop_file_path: str) -> str:
    desktop_path = Path(desktop_file_path).expanduser()

    if not desktop_path.exists():
        raise FileNotFoundError(f"Desktop file does not exist: {desktop_path}")

    for line in desktop_path.read_text(errors="ignore").splitlines():
        stripped = line.strip()

        if stripped.startswith("Exec="):
            return stripped.removeprefix("Exec=").strip()

    raise ValueError(f"Desktop file has no Exec line: {desktop_path}")


def _apply_desktop_arguments(
    exec_line: str,
    extra_arguments: list[str],
    mode: str,
) -> list[str]:
    command = shlex.split(exec_line, posix=True)

    if not command:
        raise ValueError("Desktop Exec line produced an empty command.")

    metadata_codes = {
        "%i",
        "%c",
        "%k",
        "%v",
        "%m",
        "%d",
        "%D",
        "%n",
        "%N",
    }

    argument_codes = {
        "%f",
        "%F",
        "%u",
        "%U",
    }

    cleaned: list[str] = []
    inserted_arguments = False

    for part in command:
        if part in metadata_codes:
            continue

        if part in argument_codes:
            if extra_arguments:
                cleaned.extend(extra_arguments)
                inserted_arguments = True
            continue

        cleaned.append(part.replace("%%", "%"))

    if not extra_arguments:
        return cleaned

    if mode == "replace":
        return [cleaned[0], *extra_arguments]

    if not inserted_arguments:
        cleaned.extend(extra_arguments)

    return cleaned

def _script_interpreter_from_shebang(script_path: Path) -> list[str] | None:
    try:
        first_line = script_path.read_text(errors="ignore").splitlines()[0]
    except (OSError, IndexError):
        return None

    if not first_line.startswith("#!"):
        return None

    shebang = first_line.removeprefix("#!").strip()

    if not shebang:
        return None

    parts = shlex.split(shebang, posix=True)

    if not parts:
        return None

    executable_name = Path(parts[0]).name

    if executable_name == "env":
        env_parts = parts[1:]

        if not env_parts:
            return None

        if env_parts[0] == "-S":
            return env_parts[1:] or None

        while env_parts and env_parts[0].startswith("-"):
            env_parts = env_parts[1:]

        return env_parts or None

    return parts


def _script_command(script_path_text: str, arguments: list[str]) -> list[str]:
    script_path = Path(script_path_text).expanduser()
    suffix = script_path.suffix.lower()

    if suffix == ".py":
        return [sys.executable, str(script_path), *arguments]

    if suffix in {".sh", ".bash"}:
        return ["bash", str(script_path), *arguments]

    if suffix == ".zsh":
        return ["zsh", str(script_path), *arguments]

    if suffix == ".fish":
        return ["fish", str(script_path), *arguments]

    if suffix == ".ps1":
        shell_command = "powershell" if sys.platform.startswith("win") else "pwsh"
        return [shell_command, str(script_path), *arguments]

    if suffix in {".bat", ".cmd"}:
        if not sys.platform.startswith("win"):
            raise RuntimeError("Batch files are only supported on Windows.")
        return [str(script_path), *arguments]

    shebang_command = _script_interpreter_from_shebang(script_path)

    if shebang_command:
        return [*shebang_command, str(script_path), *arguments]

    if sys.platform.startswith("linux") and os.access(script_path, os.X_OK):
        return [str(script_path), *arguments]

    raise ValueError(
        "Could not determine script type. Use a known suffix, add a shebang, " 
        "or mark the script executable."
    )


def _app_output_log_path(display_name: str) -> Path:
    safe_name = "".join(
        character.lower() if character.isalnum() else "-"
        for character in display_name
    ).strip("-")

    if not safe_name:
        safe_name = "app"

    log_dir = Path.home() / "Documents" / "UVRL Logs" / "app-output"
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%dT%H%M%S")
    return log_dir / f"{safe_name}-{timestamp}.log"


def _terminal_launcher_command(command: list[str], display_name: str) -> list[str] | None:
    title = f"UVRL - {display_name}"

    if sys.platform.startswith("linux"):
        if shutil.which("ptyxis"):
            return ["ptyxis", "--new-window", "--title", title, "--", *command]

        if shutil.which("gnome-terminal"):
            return ["gnome-terminal", f"--title={title}", "--", *command]

        if shutil.which("konsole"):
            return ["konsole", "--new-tab", "-p", f"tabtitle={title}", "-e", *command]

        if shutil.which("xterm"):
            return ["xterm", "-T", title, "-e", *command]

    return None


def _launch_mode_for_app(
    launch_kind: str,
    executable_path: str | None,
) -> str:
    if launch_kind in {"script", "python", "bash", "powershell", "batch"}:
        return "terminal"

    return "detached"


def _launch_command(
    command: list[str],
    working_directory: str | None,
    display_name: str,
    launch_mode: str,
) -> None:
    cwd = working_directory if working_directory else None

    if launch_mode == "terminal":
        terminal_command = _terminal_launcher_command(command, display_name)

        if terminal_command:
            subprocess.Popen(
                terminal_command,
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=not sys.platform.startswith("win"),
            )

            print(f"  launched {display_name} in separate terminal: {command}")
            return

        print("  no supported terminal emulator found. Falling back to detached app log.")

    log_path = _app_output_log_path(display_name)

    with log_path.open("ab") as log_file:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_file.write(bytes([10]))
        header_text = "===== Starting {} at {} =====".format(display_name, timestamp)
        log_file.write((header_text + chr(10)).encode("utf-8"))

        subprocess.Popen(
            command,
            cwd=cwd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=not sys.platform.startswith("win"),
        )

    print(f"  launched {display_name}: {command}")
    print(f"  app output log: {log_path}")

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


def _launch_executable_step(
    step: ProfileStep,
    dry_run: bool,
    launch_argument_context: dict[int, LaunchArgumentContext],
) -> None:
    if step.app_id is None:
        raise ValueError("launch_executable step has no app_id.")

    app = _get_app_row(step.app_id)

    display_name = str(app["display_name"])
    launch_kind = str(app["launch_kind"])
    executable_path = app["executable_path"]
    working_directory = step.launch_working_directory or app["working_directory"]

    if step.wait_process_name or step.wait_process_path:
        if dry_run:
            print(
                "  would skip launch if process is already detected: "
                f"name={step.wait_process_name!r}, path={step.wait_process_path!r}"
            )
        elif _process_detected(step.wait_process_name, step.wait_process_path):
            print(
                "  process already detected. Skipping launch: "
                f"name={step.wait_process_name!r}, path={step.wait_process_path!r}"
            )
            return


    default_args = _split_args(app["default_arguments"])
    step_args = _split_args(step.launch_arguments)

    context = launch_argument_context.get(step.app_id)

    if step_args:
        context_args = step_args
        context_mode = "supplement"
    elif context is not None:
        context_args = context.arguments
        context_mode = context.mode
    else:
        context_args = []
        context_mode = "supplement"

    if context_mode == "replace":
        arguments = context_args
    else:
        arguments = default_args + context_args

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
            command = ["flatpak", *default_args, *context_args]
        else:
            command = ["flatpak", "run", str(flatpak_app_id), *context_args]

    elif launch_kind == "script":
        if not executable_path:
            raise ValueError(f"Script app [{step.app_id}] has no executable_path.")

        command = _script_command(str(executable_path), arguments)

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

    elif launch_kind in {"native", "script"}:
        if not executable_path:
            raise ValueError(f"App [{step.app_id}] has no executable_path.")

        native_path = Path(executable_path).expanduser()

        if sys.platform.startswith("linux") and native_path.suffix.lower() == ".desktop":
            exec_line = _read_desktop_exec_line(str(native_path))
            command = _apply_desktop_arguments(
                exec_line=exec_line,
                extra_arguments=context_args,
                mode=context_mode,
            )
        else:
            command = [str(native_path), *arguments]

    elif launch_kind == "custom":
        if not executable_path:
            raise ValueError(f"App [{step.app_id}] has no executable_path.")

        custom_path = Path(executable_path).expanduser()

        if sys.platform.startswith("linux") and custom_path.suffix.lower() == ".desktop":
            exec_line = _read_desktop_exec_line(str(custom_path))
            command = _apply_desktop_arguments(
                exec_line=exec_line,
                extra_arguments=context_args,
                mode=context_mode,
            )
        else:
            command = [str(custom_path), *arguments]

    else:
        raise ValueError(f"Unsupported launch_kind for app [{step.app_id}]: {launch_kind}")

    launch_mode = _launch_mode_for_app(
        launch_kind=launch_kind,
        executable_path=executable_path,
    )

    if dry_run:
        print(f"  would launch {display_name}: {command}")
        print(f"  launch mode: {launch_mode}")

        if launch_mode == "detached":
            print("  app output: separate app-output log")

        if working_directory:
            print(f"  working directory: {working_directory}")

        return

    _launch_command(
        command=command,
        working_directory=working_directory,
        display_name=display_name,
        launch_mode=launch_mode,
    )


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

    process_name = step.wait_process_name
    process_path = step.wait_process_path

    if dry_run:
        if process_name or process_path:
            print(
                "  would delay for "
                f"{step.delay_seconds} seconds unless process is detected: "
                f"name={process_name!r}, path={process_path!r}"
            )
        else:
            print(f"  would delay for {step.delay_seconds} seconds")
        return

    if not process_name and not process_path:
        print(f"  delaying for {step.delay_seconds} seconds")
        time.sleep(step.delay_seconds)
        return

    print(
        "  delaying for "
        f"{step.delay_seconds} seconds unless process is detected: "
        f"name={process_name!r}, path={process_path!r}"
    )

    deadline = time.monotonic() + step.delay_seconds

    while True:
        if _process_detected(process_name, process_path):
            print("  process detected. Skipping remaining delay.")
            return

        if step.delay_seconds == 0 or time.monotonic() >= deadline:
            print("  delay completed.")
            return

        time.sleep(1)


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

    launch_argument_context: dict[int, LaunchArgumentContext] = {}

    for step in steps:
        if not step.is_enabled:
            print(f"Skipping disabled step [{step.profile_step_id}] #{step.step_order}: {step.action_type}")
            continue

        label = step.step_name or step.action_type
        print(f"Step [{step.profile_step_id}] #{step.step_order}: {label}")

        try:
            if step.action_type == "set_config":
                _set_config_step(step, dry_run=dry_run, backup_export_dir=backup_export_dir)

            elif step.action_type == "app_args":
                if step.app_id is None:
                    raise ValueError("app_args step has no app_id.")

                launch_argument_context[step.app_id] = LaunchArgumentContext(
                    arguments=_split_args(step.launch_arguments),
                    mode=step.launch_argument_mode,
                )

                if dry_run:
                    print(
                        "  would set launch arguments for "
                        f"app [{step.app_id}] mode={step.launch_argument_mode}: "
                        f"{launch_argument_context[step.app_id].arguments}"
                    )
                else:
                    print(
                        "  set launch arguments for "
                        f"app [{step.app_id}] mode={step.launch_argument_mode}"
                    )

            elif step.action_type == "launch_executable":
                _launch_executable_step(
                    step,
                    dry_run=dry_run,
                    launch_argument_context=launch_argument_context,
                )

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

