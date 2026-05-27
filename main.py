from __future__ import annotations

import argparse
import shutil

from pathlib import Path
from uvrl.app.services.app_registry import add_app, print_apps
from uvrl.app.services.config_apply import apply_config_variant
from uvrl.app.services.config_backups import print_config_backups, restore_config_from_backup
from uvrl.app.services.config_locations import add_config_location, print_config_locations
from uvrl.app.services.profile_validation import print_profile_validation
from uvrl.app.services.profile_runner import run_profile
from uvrl.app.services.config_variants import (
    create_working_variant_from_original,
    delete_config_variant,
    import_variant_from_file,
    print_config_variants,
)
from uvrl.app.services.database import initialize_database, print_database_status
from uvrl.app.services.discovery_catalog import print_discovery_catalog
from uvrl.app.services.scanner import run_scan_wizard
from uvrl.app.services.reset import print_reset_proof, reset_uvrl_runtime_state
from uvrl.app.services.profiles import (
    add_delay_step,
    add_app_args_step,
    add_launch_executable_step,
    add_open_url_step,
    add_profile,
    add_set_config_step,
    add_wait_for_process_step,
    delete_profile,
    delete_profile_step,
    move_profile_step,
    print_profile_steps,
    print_profiles,
)



class UVRLHelpFormatter(argparse.HelpFormatter):
    def __init__(self, prog: str) -> None:
        terminal_width = shutil.get_terminal_size(fallback=(100, 24)).columns
        safe_width = max(72, min(terminal_width, 120))

        super().__init__(
            prog,
            width=safe_width,
            max_help_position=34,
        )


class UVRLArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("formatter_class", UVRLHelpFormatter)
        super().__init__(*args, **kwargs)


def add_config_selector_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--config-location-id", type=int)
    group.add_argument("--config-path")


def add_common_step_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile-id", required=True, type=int)
    parser.add_argument("--step-order", type=int)
    parser.add_argument("--name")
    parser.add_argument(
        "--failure-behavior",
        default="stop_profile",
        choices=["stop_profile", "continue"],
    )
    parser.add_argument("--notes")


def build_parser() -> argparse.ArgumentParser:
    parser = UVRLArgumentParser(
        prog="uvrl",
        description="Universal VR Launcher",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="command")

    subparsers.add_parser("init-db", help="Create or update the UVRL SQLite database.")
    subparsers.add_parser("db-status", help="Show UVRL database path, tables, and settings.")

    subparsers.add_parser(
        "catalog-list",
        help="List known app/config discovery targets.",
    )

    subparsers.add_parser(
        "scan-wizard",
        help="Interactively scan for catalog-matched executables and config files.",
    )

    reset_parser = subparsers.add_parser(
        "reset-uvrl",
        aliases=["reset"],
        help="Reset UVRL to first-run user state while keeping schema and discovery catalog.",
    )
    reset_parser.set_defaults(command="reset-uvrl")
    reset_parser.add_argument("--yes", action="store_true", help="Confirm destructive reset.")
    reset_parser.add_argument("--no-backup", action="store_true", help="Do not create a database backup first.")
    reset_parser.add_argument("--proof", action="store_true", help="Print verification counts after reset.")

    subparsers.add_parser("app-list", help="List registered apps.")

    app_add_parser = subparsers.add_parser(
        "app-add",
        help="Add a manually managed app to the registry.",
    )
    app_add_parser.add_argument("--name", required=True)
    app_add_parser.add_argument(
        "--kind",
        default="native",
        choices=[
            "native",
            "script",
            "steam_app",
            "flatpak",
            "python",
            "bash",
            "powershell",
            "batch",
            "custom",
        ],
    )
    app_add_parser.add_argument(
        "--platform",
        default="any",
        choices=["linux", "windows", "any"],
    )
    app_add_parser.add_argument("--path")
    app_add_parser.add_argument("--working-directory")
    app_add_parser.add_argument("--args")
    app_add_parser.add_argument("--steam-app-id")
    app_add_parser.add_argument("--flatpak-app-id")
    app_add_parser.add_argument("--notes")

    subparsers.add_parser("config-list", help="List managed config file locations.")

    config_add_parser = subparsers.add_parser(
        "config-add",
        help="Add a managed config file location.",
    )
    config_add_parser.add_argument("--name", required=True)
    config_add_parser.add_argument("--path", required=True)
    config_add_parser.add_argument(
        "--platform",
        default="any",
        choices=["linux", "windows", "any"],
    )
    config_add_parser.add_argument(
        "--kind",
        default="unknown",
        choices=["json", "vdf", "ini", "toml", "yaml", "text", "binary", "unknown"],
    )
    config_add_parser.add_argument("--app-id", type=int)
    config_add_parser.add_argument("--notes")

    subparsers.add_parser("variant-list", help="List stored config variants.")

    variant_import_parser = subparsers.add_parser(
        "variant-import",
        help="Import an explicitly selected modified config file as a variant.",
    )
    add_config_selector_arguments(variant_import_parser)
    variant_import_parser.add_argument("--variant-file", required=True)
    variant_import_parser.add_argument("--name", required=True)
    variant_import_parser.add_argument("--description")
    variant_import_parser.add_argument("--variant-export-dir")

    variant_new_parser = subparsers.add_parser(
        "variant-new-from-original",
        help="Copy an original managed config to a working file and open it for editing.",
    )
    add_config_selector_arguments(variant_new_parser)
    variant_new_parser.add_argument("--name", required=True)
    variant_new_parser.add_argument("--working-dir")
    variant_new_parser.add_argument(
        "--no-open-editor",
        action="store_true",
        help="Create the working copy but do not open the OS default editor.",
    )

    variant_apply_parser = subparsers.add_parser(
        "variant-apply",
        help="Overwrite a managed config file with a stored config variant.",
    )
    variant_apply_parser.add_argument("--variant-id", required=True, type=int)
    variant_apply_parser.add_argument("--backup-export-dir")

    variant_delete_parser = subparsers.add_parser(
        "variant-delete",
        help="Delete a stored config variant.",
    )
    variant_delete_parser.add_argument("--variant-id", required=True, type=int)
    variant_delete_parser.add_argument("--keep-exported-file", action="store_true")
    variant_delete_parser.add_argument("--yes", action="store_true", help="Confirm deletion.")

    subparsers.add_parser("backup-list", help="List stored config backups.")

    backup_restore_parser = subparsers.add_parser(
        "backup-restore",
        help="Restore a real config file from a stored backup.",
    )
    backup_restore_parser.add_argument("--backup-id", required=True, type=int)
    backup_restore_parser.add_argument("--no-pre-restore-backup", action="store_true")
    backup_restore_parser.add_argument("--backup-export-dir")

    subparsers.add_parser("profile-list", help="List profiles.")

    profile_add_parser = subparsers.add_parser("profile-add", help="Add a profile.")
    profile_add_parser.add_argument("--name", required=True)
    profile_add_parser.add_argument("--description")
    profile_add_parser.add_argument(
        "--platform",
        default="any",
        choices=["linux", "windows", "any"],
    )
    profile_add_parser.add_argument("--restore-configs-on-exit", action="store_true")

    profile_delete_parser = subparsers.add_parser("profile-delete", help="Delete a profile.")
    profile_delete_parser.add_argument("--profile-id", required=True, type=int)
    profile_delete_parser.add_argument("--yes", action="store_true")

    profile_step_list_parser = subparsers.add_parser(
        "profile-step-list",
        help="List steps for a profile.",
    )
    profile_step_list_parser.add_argument("--profile-id", required=True, type=int)

    step_delete_parser = subparsers.add_parser(
        "profile-step-delete",
        help="Delete a profile step.",
    )
    step_delete_parser.add_argument("--step-id", required=True, type=int)
    step_delete_parser.add_argument("--yes", action="store_true")

    set_config_parser = subparsers.add_parser(
        "profile-step-add-set-config",
        help="Add a set_config step to a profile.",
    )
    add_common_step_arguments(set_config_parser)
    source_group = set_config_parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--config-variant-id", type=int)
    source_group.add_argument("--config-backup-id", type=int)

    launch_parser = subparsers.add_parser(
        "profile-step-add-launch-executable",
        aliases=["add-launch"],
        help="Add a launch_executable step to a profile.",
    )
    launch_parser.set_defaults(command="profile-step-add-launch-executable")
    add_common_step_arguments(launch_parser)
    launch_parser.add_argument("--app-id", required=True, type=int)
    launch_parser.add_argument("--args")
    launch_parser.add_argument("--working-directory")

    app_args_parser = subparsers.add_parser(
        "profile-step-add-app-args",
        aliases=["app-args"],
        help="Set temporary launch arguments for a later app launch step.",
    )
    app_args_parser.set_defaults(command="profile-step-add-app-args")
    add_common_step_arguments(app_args_parser)
    app_args_parser.add_argument("--app-id", required=True, type=int)
    app_args_parser.add_argument("--args", required=True)
    app_args_parser.add_argument(
        "--mode",
        default="supplement",
        choices=["supplement", "replace"],
    )

    wait_parser = subparsers.add_parser(
        "profile-step-add-wait-for-process",
        help="Add a wait_for_process step to a profile.",
    )
    add_common_step_arguments(wait_parser)
    wait_group = wait_parser.add_mutually_exclusive_group(required=True)
    wait_group.add_argument("--process-name")
    wait_group.add_argument("--process-path")
    wait_parser.add_argument("--timeout-seconds", type=int, default=120)

    delay_parser = subparsers.add_parser(
        "profile-step-add-delay",
        help="Add a delay step to a profile.",
    )
    add_common_step_arguments(delay_parser)
    delay_parser.add_argument("--seconds", required=True, type=int)

    url_parser = subparsers.add_parser(
        "profile-step-add-open-url",
        help="Add an open_url step to a profile.",
    )
    add_common_step_arguments(url_parser)
    url_parser.add_argument("--url", required=True)

    move_step_parser = subparsers.add_parser(
        "move-step",
        aliases=["step-move"],
        help="Move a profile step between two other steps.",
    )
    move_step_parser.set_defaults(command="move-step")
    move_step_parser.add_argument("--step-id", required=True, type=int)
    move_step_parser.add_argument(
        "--step-pos",
        required=True,
        nargs=2,
        metavar=("AFTER_STEP_ID", "BEFORE_STEP_ID_OR_END"),
    )

    profile_validate_parser = subparsers.add_parser(
        "profile-validate",
        help="Validate a profile without running it.",
    )
    profile_validate_parser.add_argument("--profile-id", required=True, type=int)

    profile_run_parser = subparsers.add_parser(
        "profile-run",
        help="Run a profile. Use --dry-run first.",
    )
    profile_run_parser.add_argument("--profile-id", required=True, type=int)
    profile_run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without writing configs, launching apps, opening URLs, or waiting.",
    )
    profile_run_parser.add_argument("--backup-export-dir")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    initialize_database()

    if args.command == "init-db":
        print("UVRL database initialized.")

    elif args.command == "db-status":
        print_database_status()

    elif args.command == "catalog-list":
        print_discovery_catalog()

    elif args.command == "scan-wizard":
        run_scan_wizard()

    elif args.command == "reset-uvrl":
        if not args.yes:
            print("Reset requires --yes.")
            print("This clears saved profiles, profile steps, apps, config locations, variants, backups, scripts, generated files, and ID sequences.")
            print("It keeps the schema, app settings, and discovery catalog.")
            return

        result = reset_uvrl_runtime_state(create_backup=not args.no_backup)

        print("UVRL reset complete.")
        print(f"  database: {result.database_path}")

        if result.backup_path is not None:
            print(f"  backup:   {result.backup_path}")
        else:
            print("  backup:   not created")

        if result.deleted_directories:
            print("  deleted generated directories:")

            for directory in result.deleted_directories:
                print(f"    - {directory}")

        if result.recreated_directories:
            print("  recreated runtime directories:")

            for directory in result.recreated_directories:
                print(f"    - {directory}")
        if args.proof:
            print_reset_proof()

    elif args.command == "app-list":
        print_apps()

    elif args.command == "app-add":
        app_id = add_app(
            display_name=args.name,
            launch_kind=args.kind,
            platform=args.platform,
            executable_path=args.path,
            working_directory=(
                args.working_directory
                or (str(Path(args.path).expanduser().parent) if args.path else None)
            ),
            default_arguments=args.args,
            steam_app_id=args.steam_app_id,
            flatpak_app_id=args.flatpak_app_id,
            notes=args.notes,
        )
        print(f"Added app [{app_id}] {args.name}")

    elif args.command == "config-list":
        print_config_locations()

    elif args.command == "config-add":
        config_location_id = add_config_location(
            display_name=args.name,
            file_path=args.path,
            platform=args.platform,
            file_kind=args.kind,
            app_id=args.app_id,
            notes=args.notes,
        )
        print(f"Added config location [{config_location_id}] {args.name}")

    elif args.command == "variant-list":
        print_config_variants()

    elif args.command == "variant-import":
        result = import_variant_from_file(
            config_location_id=args.config_location_id,
            config_path=args.config_path,
            variant_file_path=args.variant_file,
            variant_name=args.name,
            description=args.description,
            variant_export_dir=args.variant_export_dir,
        )

        if result.variant_created:
            print(f"Imported config variant [{result.config_variant_id}] {result.variant_name}")
            print(f"  exported: {result.variant_export_path}")
        else:
            print("No config variant imported.")
            print(
                "Selected file content already matched existing variant "
                f"[{result.matched_existing_variant_id}] "
                f"{result.matched_existing_variant_name}"
            )

    elif args.command == "variant-new-from-original":
        result = create_working_variant_from_original(
            config_location_id=args.config_location_id,
            config_path=args.config_path,
            variant_name=args.name,
            working_dir=args.working_dir,
            open_editor=not args.no_open_editor,
        )

        print("Created working variant file from original config.")
        print(f"  config:   [{result.config_location_id}] {result.config_display_name}")
        print(f"  original: {result.original_config_path}")
        print(f"  working:  {result.working_file_path}")

        if result.opened_with_default_app:
            print("Opened working file with OS default app.")
        else:
            print("Did not open working file with OS default app.")

    elif args.command == "variant-apply":
        result = apply_config_variant(
            config_variant_id=args.variant_id,
            backup_export_dir=args.backup_export_dir,
        )

        if result.already_applied:
            print(f"Variant [{result.config_variant_id}] {result.variant_name} is already applied.")
            print(f"  target: {result.target_path}")
        else:
            print(f"Applied variant [{result.config_variant_id}] {result.variant_name}")
            print(f"  target: {result.target_path}")

        if result.backup_created:
            print(f"Created pre-apply backup [{result.backup_id}]")
            print(f"  exported: {result.backup_export_path}")
        elif result.matched_existing_backup_id is not None:
            print(
                "No pre-apply backup created. "
                f"Matching backup already exists [{result.matched_existing_backup_id}]."
            )
        else:
            print("No pre-apply backup created.")

    elif args.command == "variant-delete":
        if not args.yes:
            print("Deletion requires --yes.")
            return

        result = delete_config_variant(
            config_variant_id=args.variant_id,
            delete_exported_file=not args.keep_exported_file,
        )

        print(f"Deleted config variant [{result.config_variant_id}] {result.variant_name}")

        if result.exported_file_deleted:
            print(f"Deleted exported file: {result.exported_file_path}")
        elif result.exported_file_missing:
            print(f"Exported file was already missing: {result.exported_file_path}")
        elif result.exported_file_path and args.keep_exported_file:
            print(f"Kept exported file: {result.exported_file_path}")
        else:
            print("No exported file path was stored.")

    elif args.command == "backup-list":
        print_config_backups()

    elif args.command == "backup-restore":
        result = restore_config_from_backup(
            config_backup_id=args.backup_id,
            create_pre_restore_backup=not args.no_pre_restore_backup,
            backup_export_dir=args.backup_export_dir,
        )

        print(f"Restored backup [{result.restored_backup_id}]")
        print(f"  restored to: {result.restored_to_path}")

        if result.pre_restore_backup_created:
            print(f"Created pre-restore backup [{result.pre_restore_backup_id}]")
            print(f"  exported: {result.pre_restore_backup_export_path}")
        elif result.matched_existing_backup_id is not None:
            print(
                "No pre-restore backup created. "
                f"Matching backup already exists [{result.matched_existing_backup_id}]."
            )
        else:
            print("No pre-restore backup created.")

    elif args.command == "profile-list":
        print_profiles()

    elif args.command == "profile-add":
        profile_id = add_profile(
            profile_name=args.name,
            description=args.description,
            platform=args.platform,
            restore_configs_on_exit=args.restore_configs_on_exit,
        )
        print(f"Added profile [{profile_id}] {args.name}")

    elif args.command == "profile-delete":
        if not args.yes:
            print("Deletion requires --yes.")
            return

        delete_profile(args.profile_id)
        print(f"Deleted profile [{args.profile_id}]")

    elif args.command == "profile-step-list":
        print_profile_steps(args.profile_id)

    elif args.command == "profile-validate":
        print_profile_validation(args.profile_id)

    elif args.command == "profile-run":
        run_profile(
            profile_id=args.profile_id,
            dry_run=args.dry_run,
            backup_export_dir=args.backup_export_dir,
        )

    elif args.command == "profile-step-delete":
        if not args.yes:
            print("Deletion requires --yes.")
            return

        delete_profile_step(args.step_id)
        print(f"Deleted profile step [{args.step_id}]")

    elif args.command == "profile-step-add-set-config":
        step_id = add_set_config_step(
            profile_id=args.profile_id,
            config_variant_id=args.config_variant_id,
            config_backup_id=args.config_backup_id,
            step_order=args.step_order,
            step_name=args.name,
            failure_behavior=args.failure_behavior,
            notes=args.notes,
        )
        print(f"Added set_config profile step [{step_id}]")

    elif args.command == "profile-step-add-app-args":
        step_id = add_app_args_step(
            profile_id=args.profile_id,
            app_id=args.app_id,
            step_order=args.step_order,
            step_name=args.name,
            launch_arguments=args.args,
            launch_argument_mode=args.mode,
            failure_behavior=args.failure_behavior,
            notes=args.notes,
        )
        print(f"Added app_args profile step [{step_id}]")

    elif args.command == "profile-step-add-launch-executable":
        step_id = add_launch_executable_step(
            profile_id=args.profile_id,
            app_id=args.app_id,
            step_order=args.step_order,
            step_name=args.name,
            launch_arguments=args.args,
            launch_working_directory=args.working_directory,
            failure_behavior=args.failure_behavior,
            notes=args.notes,
        )
        print(f"Added launch_executable profile step [{step_id}]")

    elif args.command == "profile-step-add-wait-for-process":
        step_id = add_wait_for_process_step(
            profile_id=args.profile_id,
            process_name=args.process_name,
            process_path=args.process_path,
            timeout_seconds=args.timeout_seconds,
            step_order=args.step_order,
            step_name=args.name,
            failure_behavior=args.failure_behavior,
            notes=args.notes,
        )
        print(f"Added wait_for_process profile step [{step_id}]")

    elif args.command == "profile-step-add-delay":
        step_id = add_delay_step(
            profile_id=args.profile_id,
            delay_seconds=args.seconds,
            step_order=args.step_order,
            step_name=args.name,
            failure_behavior=args.failure_behavior,
            notes=args.notes,
        )
        print(f"Added delay profile step [{step_id}]")

    elif args.command == "profile-step-add-open-url":
        step_id = add_open_url_step(
            profile_id=args.profile_id,
            url=args.url,
            step_order=args.step_order,
            step_name=args.name,
            failure_behavior=args.failure_behavior,
            notes=args.notes,
        )
        print(f"Added open_url profile step [{step_id}]")

    elif args.command == "move-step":
        move_profile_step(
            step_id=args.step_id,
            after_step_id_text=args.step_pos[0],
            before_step_id_text=args.step_pos[1],
        )
        print(
            f"Moved profile step [{args.step_id}] "
            f"between {args.step_pos[0]} and {args.step_pos[1]}"
        )

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
