from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from uvrl.app.services.database import (
    CONFIG_BACKUPS_DIR,
    PROJECT_ROOT,
    ensure_runtime_directories,
    open_database,
)


@dataclass(frozen=True)
class RestoreBackupResult:
    restored_backup_id: int
    restored_to_path: str

    pre_restore_backup_created: bool
    pre_restore_backup_id: int | None
    pre_restore_backup_export_path: str | None

    matched_existing_backup_id: int | None


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _utc_timestamp_for_filename() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _relative_to_project(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _resolve_export_dir(path_text: str | None, default_path: Path) -> Path:
    if path_text is None:
        return default_path

    path = Path(path_text).expanduser()

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    return path.resolve()


def _stored_path_to_absolute(path_text: str | None) -> Path | None:
    if not path_text:
        return None

    path = Path(path_text).expanduser()

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    return path.resolve()


def _is_under_directory(path_text: str | None, directory: Path) -> bool:
    stored_path = _stored_path_to_absolute(path_text)

    if stored_path is None:
        return False

    directory = directory.resolve()

    try:
        stored_path.relative_to(directory)
        return True
    except ValueError:
        return False


def _extension_from_path(path: Path) -> str:
    return path.suffix if path.suffix else ".config"


def _split_content_for_sql(content: bytes) -> tuple[str | None, bytes | None, str]:
    try:
        return content.decode("utf-8"), None, "utf-8"
    except UnicodeDecodeError:
        return None, content, "binary"


def _content_from_backup_row(row) -> bytes:
    if row["content_blob"] is not None:
        return bytes(row["content_blob"])

    if row["content_text"] is not None:
        encoding = row["content_encoding"] or "utf-8"
        return str(row["content_text"]).encode(encoding)

    exported_file_path = row["exported_file_path"]

    if exported_file_path:
        exported_path = _stored_path_to_absolute(exported_file_path)

        if exported_path is None:
            raise ValueError("Backup exported file path could not be resolved.")

        return exported_path.read_bytes()

    raise ValueError("Backup has no stored content and no exported file path.")


def _write_export_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _find_matching_backup_for_location(
    config_location_id: int,
    content_sha256: str,
    target_backup_dir: Path,
    backup_export_dir_was_provided: bool,
) -> int | None:
    with open_database() as database:
        rows = database.execute(
            """
            SELECT
                config_backup_id,
                exported_file_path
            FROM config_backups
            WHERE config_location_id = ?
              AND content_sha256 = ?
            ORDER BY config_backup_id;
            """,
            (config_location_id, content_sha256),
        ).fetchall()

    if not rows:
        return None

    if not backup_export_dir_was_provided:
        return int(rows[0]["config_backup_id"])

    for row in rows:
        if _is_under_directory(row["exported_file_path"], target_backup_dir):
            return int(row["config_backup_id"])

    return None


def print_config_backups() -> None:
    with open_database() as database:
        rows = database.execute(
            """
            SELECT
                cb.config_backup_id,
                cb.config_location_id,
                cl.display_name AS config_display_name,
                cb.profile_id,
                cb.backup_reason,
                cb.original_file_path,
                cb.content_sha256,
                cb.exported_file_path,
                cb.backed_up_at,
                cb.restored_at
            FROM config_backups cb
            JOIN config_locations cl
                ON cl.config_location_id = cb.config_location_id
            ORDER BY cb.config_backup_id;
            """
        ).fetchall()

    if not rows:
        print("No config backups registered.")
        return

    for row in rows:
        print(f"[{row['config_backup_id']}] {row['backup_reason']}")
        print(f"  config:    [{row['config_location_id']}] {row['config_display_name']}")
        print(f"  original:  {row['original_file_path']}")
        print(f"  sha256:    {row['content_sha256']}")
        print(f"  exported:  {row['exported_file_path']}")
        print(f"  backed up: {row['backed_up_at']}")

        if row["restored_at"]:
            print(f"  restored:  {row['restored_at']}")

        print()


def restore_config_from_backup(
    config_backup_id: int,
    create_pre_restore_backup: bool = True,
    backup_export_dir: str | None = None,
) -> RestoreBackupResult:
    """
    Restore a real config file from a stored backup.

    Duplicate rule for the pre-restore backup:
    - Duplicate backup content is rejected by default.
    - A duplicate backup is allowed only when backup_export_dir is provided
      and no matching backup already exists in that target directory.
    """
    ensure_runtime_directories()

    backup_export_dir_was_provided = backup_export_dir is not None
    backup_base_dir = _resolve_export_dir(backup_export_dir, CONFIG_BACKUPS_DIR)

    with open_database() as database:
        backup = database.execute(
            """
            SELECT
                cb.config_backup_id,
                cb.config_location_id,
                cb.content_text,
                cb.content_blob,
                cb.content_encoding,
                cb.content_sha256,
                cb.exported_file_path,
                cl.file_path
            FROM config_backups cb
            JOIN config_locations cl
                ON cl.config_location_id = cb.config_location_id
            WHERE cb.config_backup_id = ?;
            """,
            (config_backup_id,),
        ).fetchone()

    if backup is None:
        raise ValueError(f"No config backup found with ID {config_backup_id}")

    config_location_id = int(backup["config_location_id"])
    target_path = Path(backup["file_path"]).expanduser()
    restore_content = _content_from_backup_row(backup)

    pre_restore_backup_created = False
    pre_restore_backup_id: int | None = None
    pre_restore_backup_export_path: str | None = None
    matched_existing_backup_id: int | None = None

    with open_database() as database:
        if create_pre_restore_backup and target_path.exists():
            current_content = target_path.read_bytes()
            current_sha256 = _sha256_bytes(current_content)
            current_text, current_blob, current_encoding = _split_content_for_sql(current_content)

            matched_existing_backup_id = _find_matching_backup_for_location(
                config_location_id=config_location_id,
                content_sha256=current_sha256,
                target_backup_dir=backup_base_dir,
                backup_export_dir_was_provided=backup_export_dir_was_provided,
            )

            if matched_existing_backup_id is None:
                cursor = database.execute(
                    """
                    INSERT INTO config_backups (
                        config_location_id,
                        profile_id,
                        backup_reason,
                        original_file_path,
                        content_text,
                        content_blob,
                        content_encoding,
                        content_sha256,
                        exported_file_path,
                        notes
                    )
                    VALUES (?, NULL, ?, ?, ?, ?, ?, ?, NULL, ?);
                    """,
                    (
                        config_location_id,
                        "before_restore",
                        str(target_path),
                        current_text,
                        current_blob,
                        current_encoding,
                        current_sha256,
                        f"Automatic backup created before restoring backup {config_backup_id}.",
                    ),
                )

                pre_restore_backup_id = int(cursor.lastrowid)

                timestamp = _utc_timestamp_for_filename()
                extension = _extension_from_path(target_path)
                export_path = (
                    backup_base_dir
                    / str(config_location_id)
                    / f"{pre_restore_backup_id}_{timestamp}_before_restore_{current_sha256[:12]}{extension}"
                )

                _write_export_file(export_path, current_content)
                pre_restore_backup_export_path = _relative_to_project(export_path)

                database.execute(
                    """
                    UPDATE config_backups
                    SET exported_file_path = ?
                    WHERE config_backup_id = ?;
                    """,
                    (pre_restore_backup_export_path, pre_restore_backup_id),
                )

                pre_restore_backup_created = True

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(restore_content)

        database.execute(
            """
            UPDATE config_backups
            SET restored_at = CURRENT_TIMESTAMP
            WHERE config_backup_id = ?;
            """,
            (config_backup_id,),
        )

    return RestoreBackupResult(
        restored_backup_id=config_backup_id,
        restored_to_path=str(target_path),
        pre_restore_backup_created=pre_restore_backup_created,
        pre_restore_backup_id=pre_restore_backup_id,
        pre_restore_backup_export_path=pre_restore_backup_export_path,
        matched_existing_backup_id=matched_existing_backup_id,
    )
