from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from uvrl.app.services.database import (
    CONFIG_VARIANTS_DIR,
    PROJECT_ROOT,
    ensure_runtime_directories,
    open_database,
)


CONFIG_VARIANT_WORKING_DIR = PROJECT_ROOT / "data" / "config_variant_working"


@dataclass(frozen=True)
class ConfigVariantImportResult:
    config_variant_id: int
    variant_name: str
    variant_export_path: str | None
    variant_created: bool
    matched_existing_variant_id: int | None
    matched_existing_variant_name: str | None


@dataclass(frozen=True)
class ConfigVariantWorkingCopyResult:
    config_location_id: int
    config_display_name: str
    original_config_path: str
    working_file_path: str
    opened_with_default_app: bool


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _utc_timestamp_for_filename() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_") or "unnamed"


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


def _write_export_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _open_with_default_app(path: Path) -> bool:
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

        return True
    except Exception:
        return False


def _find_config_location(
    config_location_id: int | None = None,
    config_path: str | None = None,
):
    if config_location_id is None and config_path is None:
        raise ValueError("Provide either config_location_id or config_path.")

    with open_database() as database:
        if config_location_id is not None:
            row = database.execute(
                """
                SELECT
                    config_location_id,
                    display_name,
                    file_path,
                    file_kind
                FROM config_locations
                WHERE config_location_id = ?;
                """,
                (config_location_id,),
            ).fetchone()

            if row is None:
                raise ValueError(f"No config location found with ID {config_location_id}")

            return row

        wanted_path = Path(str(config_path)).expanduser().resolve()

        rows = database.execute(
            """
            SELECT
                config_location_id,
                display_name,
                file_path,
                file_kind
            FROM config_locations;
            """
        ).fetchall()

    for row in rows:
        stored_path = Path(row["file_path"]).expanduser().resolve()

        if stored_path == wanted_path:
            return row

    raise ValueError(f"No managed config location found for path: {wanted_path}")


def _find_matching_variant_for_location(
    config_location_id: int,
    content_sha256: str,
    target_variant_dir: Path,
    variant_export_dir_was_provided: bool,
) -> tuple[int, str, str | None] | None:
    with open_database() as database:
        rows = database.execute(
            """
            SELECT
                config_variant_id,
                variant_name,
                exported_file_path
            FROM config_variants
            WHERE config_location_id = ?
              AND content_sha256 = ?
              AND is_archived = 0
            ORDER BY config_variant_id;
            """,
            (config_location_id, content_sha256),
        ).fetchall()

    if not rows:
        return None

    if not variant_export_dir_was_provided:
        first = rows[0]
        return (
            int(first["config_variant_id"]),
            first["variant_name"],
            first["exported_file_path"],
        )

    for row in rows:
        if _is_under_directory(row["exported_file_path"], target_variant_dir):
            return (
                int(row["config_variant_id"]),
                row["variant_name"],
                row["exported_file_path"],
            )

    return None


def import_variant_from_file(
    config_location_id: int | None,
    config_path: str | None,
    variant_file_path: str,
    variant_name: str,
    description: str | None = None,
    variant_export_dir: str | None = None,
) -> ConfigVariantImportResult:
    """
    Import an explicitly selected modified config file as a variant of an
    explicitly selected original managed config.

    This does not back up or overwrite the original config. Backups belong to
    apply and restore operations.
    """
    ensure_runtime_directories()

    variant_export_dir_was_provided = variant_export_dir is not None
    variant_base_dir = _resolve_export_dir(variant_export_dir, CONFIG_VARIANTS_DIR)

    config_location = _find_config_location(
        config_location_id=config_location_id,
        config_path=config_path,
    )

    resolved_config_location_id = int(config_location["config_location_id"])

    source_path = Path(variant_file_path).expanduser()

    if not source_path.is_absolute():
        source_path = PROJECT_ROOT / source_path

    source_path = source_path.resolve()

    if not source_path.exists():
        raise FileNotFoundError(f"Variant source file does not exist: {source_path}")

    content = source_path.read_bytes()
    content_sha256 = _sha256_bytes(content)
    content_text, content_blob, content_encoding = _split_content_for_sql(content)

    matching_variant = _find_matching_variant_for_location(
        config_location_id=resolved_config_location_id,
        content_sha256=content_sha256,
        target_variant_dir=variant_base_dir,
        variant_export_dir_was_provided=variant_export_dir_was_provided,
    )

    if matching_variant is not None:
        existing_id, existing_name, existing_export_path = matching_variant

        return ConfigVariantImportResult(
            config_variant_id=existing_id,
            variant_name=existing_name,
            variant_export_path=existing_export_path,
            variant_created=False,
            matched_existing_variant_id=existing_id,
            matched_existing_variant_name=existing_name,
        )

    extension = _extension_from_path(source_path)
    variant_slug = _slugify(variant_name)

    with open_database() as database:
        cursor = database.execute(
            """
            INSERT INTO config_variants (
                config_location_id,
                variant_name,
                description,
                content_text,
                content_blob,
                content_encoding,
                content_sha256,
                exported_file_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL);
            """,
            (
                resolved_config_location_id,
                variant_name,
                description,
                content_text,
                content_blob,
                content_encoding,
                content_sha256,
            ),
        )

        config_variant_id = int(cursor.lastrowid)

        variant_file = (
            variant_base_dir
            / str(resolved_config_location_id)
            / f"{config_variant_id}_{variant_slug}_{content_sha256[:12]}{extension}"
        )

        _write_export_file(variant_file, content)
        variant_export_path = _relative_to_project(variant_file)

        database.execute(
            """
            UPDATE config_variants
            SET exported_file_path = ?
            WHERE config_variant_id = ?;
            """,
            (variant_export_path, config_variant_id),
        )

    return ConfigVariantImportResult(
        config_variant_id=config_variant_id,
        variant_name=variant_name,
        variant_export_path=variant_export_path,
        variant_created=True,
        matched_existing_variant_id=None,
        matched_existing_variant_name=None,
    )


def create_working_variant_from_original(
    config_location_id: int | None,
    config_path: str | None,
    variant_name: str,
    working_dir: str | None = None,
    open_editor: bool = True,
) -> ConfigVariantWorkingCopyResult:
    """
    Copy the original managed config to a working file and optionally open it
    with the OS default app.

    This does not create a database variant yet. After editing, import the
    working file with variant-import.
    """
    ensure_runtime_directories()

    config_location = _find_config_location(
        config_location_id=config_location_id,
        config_path=config_path,
    )

    resolved_config_location_id = int(config_location["config_location_id"])
    display_name = str(config_location["display_name"])

    original_path = Path(config_location["file_path"]).expanduser()

    if not original_path.exists():
        raise FileNotFoundError(f"Original config file does not exist: {original_path}")

    base_working_dir = _resolve_export_dir(working_dir, CONFIG_VARIANT_WORKING_DIR)
    timestamp = _utc_timestamp_for_filename()
    variant_slug = _slugify(variant_name)
    extension = _extension_from_path(original_path)

    working_file = (
        base_working_dir
        / str(resolved_config_location_id)
        / f"{timestamp}_{variant_slug}{extension}"
    )

    working_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(original_path, working_file)

    opened = False

    if open_editor:
        opened = _open_with_default_app(working_file)

    return ConfigVariantWorkingCopyResult(
        config_location_id=resolved_config_location_id,
        config_display_name=display_name,
        original_config_path=str(original_path),
        working_file_path=_relative_to_project(working_file),
        opened_with_default_app=opened,
    )


def print_config_variants() -> None:
    with open_database() as database:
        rows = database.execute(
            """
            SELECT
                cv.config_variant_id,
                cv.variant_name,
                cv.config_location_id,
                cl.display_name AS config_display_name,
                cv.content_sha256,
                cv.exported_file_path,
                cv.created_at
            FROM config_variants cv
            JOIN config_locations cl
                ON cl.config_location_id = cv.config_location_id
            WHERE cv.is_archived = 0
            ORDER BY cl.display_name COLLATE NOCASE, cv.config_variant_id;
            """
        ).fetchall()

    if not rows:
        print("No config variants registered.")
        return

    for row in rows:
        print(f"[{row['config_variant_id']}] {row['variant_name']}")
        print(f"  config:   [{row['config_location_id']}] {row['config_display_name']}")
        print(f"  sha256:   {row['content_sha256']}")
        print(f"  exported: {row['exported_file_path']}")
        print(f"  created:  {row['created_at']}")
        print()

@dataclass(frozen=True)
class ConfigVariantDeleteResult:
    config_variant_id: int
    variant_name: str
    exported_file_path: str | None
    database_row_deleted: bool
    exported_file_deleted: bool
    exported_file_missing: bool


def delete_config_variant(
    config_variant_id: int,
    delete_exported_file: bool = True,
) -> ConfigVariantDeleteResult:
    """
    Delete a config variant from SQLite.

    By default, also deletes the exported variant file on disk.
    """
    with open_database() as database:
        variant = database.execute(
            """
            SELECT
                config_variant_id,
                variant_name,
                exported_file_path
            FROM config_variants
            WHERE config_variant_id = ?;
            """,
            (config_variant_id,),
        ).fetchone()

        if variant is None:
            raise ValueError(f"No config variant found with ID {config_variant_id}")

        variant_name = str(variant["variant_name"])
        exported_file_path = variant["exported_file_path"]

        exported_file_deleted = False
        exported_file_missing = False

        if delete_exported_file and exported_file_path:
            exported_path = _stored_path_to_absolute(exported_file_path)

            if exported_path is not None and exported_path.exists():
                exported_path.unlink()
                exported_file_deleted = True
            else:
                exported_file_missing = True

        database.execute(
            """
            DELETE FROM config_variants
            WHERE config_variant_id = ?;
            """,
            (config_variant_id,),
        )

    return ConfigVariantDeleteResult(
        config_variant_id=config_variant_id,
        variant_name=variant_name,
        exported_file_path=exported_file_path,
        database_row_deleted=True,
        exported_file_deleted=exported_file_deleted,
        exported_file_missing=exported_file_missing,
    )
