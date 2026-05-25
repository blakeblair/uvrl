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
class ApplyConfigVariantResult:
    config_variant_id: int
    variant_name: str
    target_path: str

    applied: bool
    already_applied: bool

    backup_created: bool
    backup_id: int | None
    backup_export_path: str | None
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


def _content_from_variant_row(row) -> bytes:
    if row["content_blob"] is not None:
        return bytes(row["content_blob"])

    if row["content_text"] is not None:
        encoding = row["content_encoding"] or "utf-8"
        return str(row["content_text"]).encode(encoding)

    exported_file_path = row["exported_file_path"]

    if exported_file_path:
        exported_path = _stored_path_to_absolute(exported_file_path)

        if exported_path is None:
            raise ValueError("Variant exported file path could not be resolved.")

        return exported_path.read_bytes()

    raise ValueError("Variant has no stored content and no exported file path.")


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


def apply_config_variant(
    config_variant_id: int,
    backup_export_dir: str | None = None,
) -> ApplyConfigVariantResult:
    """
    Apply a stored config variant to its real target config file.

    This overwrites the real config file.

    Safety behavior:
    - If the target file already matches the variant, no write occurs.
    - If the target file differs, the current file is backed up first.
    - Duplicate backups are blocked unless backup_export_dir points to a
      different export location that does not already contain that backup.
    """
    ensure_runtime_directories()

    backup_export_dir_was_provided = backup_export_dir is not None
    backup_base_dir = _resolve_export_dir(backup_export_dir, CONFIG_BACKUPS_DIR)

    with open_database() as database:
        variant = database.execute(
            """
            SELECT
                cv.config_variant_id,
                cv.config_location_id,
                cv.variant_name,
                cv.content_text,
                cv.content_blob,
                cv.content_encoding,
                cv.content_sha256,
                cv.exported_file_path,
                cl.file_path
            FROM config_variants cv
            JOIN config_locations cl
                ON cl.config_location_id = cv.config_location_id
            WHERE cv.config_variant_id = ?
              AND cv.is_archived = 0;
            """,
            (config_variant_id,),
        ).fetchone()

    if variant is None:
        raise ValueError(f"No active config variant found with ID {config_variant_id}")

    config_location_id = int(variant["config_location_id"])
    variant_name = str(variant["variant_name"])
    target_path = Path(variant["file_path"]).expanduser()
    variant_content = _content_from_variant_row(variant)
    variant_sha256 = _sha256_bytes(variant_content)

    if target_path.exists():
        current_content = target_path.read_bytes()
    else:
        current_content = b""

    current_sha256 = _sha256_bytes(current_content)

    if target_path.exists() and current_sha256 == variant_sha256:
        return ApplyConfigVariantResult(
            config_variant_id=config_variant_id,
            variant_name=variant_name,
            target_path=str(target_path),
            applied=False,
            already_applied=True,
            backup_created=False,
            backup_id=None,
            backup_export_path=None,
            matched_existing_backup_id=None,
        )

    current_text, current_blob, current_encoding = _split_content_for_sql(current_content)

    matched_existing_backup_id = None
    backup_created = False
    backup_id: int | None = None
    backup_export_path: str | None = None

    if target_path.exists():
        matched_existing_backup_id = _find_matching_backup_for_location(
            config_location_id=config_location_id,
            content_sha256=current_sha256,
            target_backup_dir=backup_base_dir,
            backup_export_dir_was_provided=backup_export_dir_was_provided,
        )

    with open_database() as database:
        if target_path.exists() and matched_existing_backup_id is None:
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
                    "before_variant_apply",
                    str(target_path),
                    current_text,
                    current_blob,
                    current_encoding,
                    current_sha256,
                    f"Automatic backup created before applying config variant {config_variant_id}.",
                ),
            )

            backup_id = int(cursor.lastrowid)

            timestamp = _utc_timestamp_for_filename()
            extension = _extension_from_path(target_path)
            backup_file = (
                backup_base_dir
                / str(config_location_id)
                / f"{backup_id}_{timestamp}_before_variant_apply_{current_sha256[:12]}{extension}"
            )

            _write_export_file(backup_file, current_content)
            backup_export_path = _relative_to_project(backup_file)

            database.execute(
                """
                UPDATE config_backups
                SET exported_file_path = ?
                WHERE config_backup_id = ?;
                """,
                (backup_export_path, backup_id),
            )

            backup_created = True

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(variant_content)

    return ApplyConfigVariantResult(
        config_variant_id=config_variant_id,
        variant_name=variant_name,
        target_path=str(target_path),
        applied=True,
        already_applied=False,
        backup_created=backup_created,
        backup_id=backup_id,
        backup_export_path=backup_export_path,
        matched_existing_backup_id=matched_existing_backup_id,
    )