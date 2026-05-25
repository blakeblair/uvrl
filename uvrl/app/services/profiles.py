from __future__ import annotations

from dataclasses import dataclass

from uvrl.app.services.database import open_database


VALID_FAILURE_BEHAVIORS = {"stop_profile", "continue"}


@dataclass(frozen=True)
class Profile:
    profile_id: int
    profile_name: str
    description: str | None
    platform: str
    restore_configs_on_exit: bool
    is_default: bool
    is_archived: bool


@dataclass(frozen=True)
class ProfileStep:
    profile_step_id: int
    profile_id: int
    step_order: int
    step_name: str | None
    action_type: str
    is_enabled: bool
    config_location_id: int | None
    config_source_type: str | None
    config_variant_id: int | None
    config_backup_id: int | None
    app_id: int | None
    launch_arguments: str | None
    launch_working_directory: str | None
    wait_process_name: str | None
    wait_process_path: str | None
    wait_timeout_seconds: int
    delay_seconds: int | None
    url: str | None
    failure_behavior: str
    notes: str | None


def _validate_failure_behavior(failure_behavior: str) -> None:
    if failure_behavior not in VALID_FAILURE_BEHAVIORS:
        raise ValueError(
            f"Invalid failure_behavior: {failure_behavior}. "
            f"Expected one of: {', '.join(sorted(VALID_FAILURE_BEHAVIORS))}"
        )


def _next_step_order(profile_id: int) -> int:
    with open_database() as database:
        row = database.execute(
            """
            SELECT COALESCE(MAX(step_order), 0) + 1 AS next_order
            FROM profile_steps
            WHERE profile_id = ?;
            """,
            (profile_id,),
        ).fetchone()

    return int(row["next_order"])


def _resolve_step_order(profile_id: int, step_order: int | None) -> int:
    if step_order is not None:
        return step_order

    return _next_step_order(profile_id)


def _ensure_profile_exists(profile_id: int) -> None:
    with open_database() as database:
        row = database.execute(
            """
            SELECT profile_id
            FROM profiles
            WHERE profile_id = ?
              AND is_archived = 0;
            """,
            (profile_id,),
        ).fetchone()

    if row is None:
        raise ValueError(f"No active profile found with ID {profile_id}")


def add_profile(
    profile_name: str,
    description: str | None = None,
    platform: str = "any",
    restore_configs_on_exit: bool = False,
) -> int:
    with open_database() as database:
        cursor = database.execute(
            """
            INSERT INTO profiles (
                profile_name,
                description,
                platform,
                restore_configs_on_exit
            )
            VALUES (?, ?, ?, ?);
            """,
            (
                profile_name,
                description,
                platform,
                1 if restore_configs_on_exit else 0,
            ),
        )

        return int(cursor.lastrowid)


def list_profiles() -> list[Profile]:
    with open_database() as database:
        rows = database.execute(
            """
            SELECT
                profile_id,
                profile_name,
                description,
                platform,
                restore_configs_on_exit,
                is_default,
                is_archived
            FROM profiles
            WHERE is_archived = 0
            ORDER BY profile_name COLLATE NOCASE;
            """
        ).fetchall()

    return [
        Profile(
            profile_id=int(row["profile_id"]),
            profile_name=str(row["profile_name"]),
            description=row["description"],
            platform=str(row["platform"]),
            restore_configs_on_exit=bool(row["restore_configs_on_exit"]),
            is_default=bool(row["is_default"]),
            is_archived=bool(row["is_archived"]),
        )
        for row in rows
    ]


def print_profiles() -> None:
    profiles = list_profiles()

    if not profiles:
        print("No profiles registered.")
        return

    for profile in profiles:
        print(f"[{profile.profile_id}] {profile.profile_name}")
        print(f"  platform:                {profile.platform}")
        print(f"  restore configs on exit: {profile.restore_configs_on_exit}")

        if profile.description:
            print(f"  description:             {profile.description}")

        print()


def delete_profile(profile_id: int) -> None:
    with open_database() as database:
        row = database.execute(
            """
            SELECT profile_name
            FROM profiles
            WHERE profile_id = ?;
            """,
            (profile_id,),
        ).fetchone()

        if row is None:
            raise ValueError(f"No profile found with ID {profile_id}")

        database.execute(
            """
            DELETE FROM profiles
            WHERE profile_id = ?;
            """,
            (profile_id,),
        )


def add_set_config_step(
    profile_id: int,
    config_variant_id: int | None = None,
    config_backup_id: int | None = None,
    step_order: int | None = None,
    step_name: str | None = None,
    failure_behavior: str = "stop_profile",
    notes: str | None = None,
) -> int:
    _ensure_profile_exists(profile_id)
    _validate_failure_behavior(failure_behavior)

    if (config_variant_id is None) == (config_backup_id is None):
        raise ValueError("Provide exactly one of config_variant_id or config_backup_id.")

    if config_variant_id is not None:
        config_source_type = "variant"

        with open_database() as database:
            row = database.execute(
                """
                SELECT config_location_id
                FROM config_variants
                WHERE config_variant_id = ?
                  AND is_archived = 0;
                """,
                (config_variant_id,),
            ).fetchone()

        if row is None:
            raise ValueError(f"No active config variant found with ID {config_variant_id}")

        config_location_id = int(row["config_location_id"])

    else:
        config_source_type = "backup"

        with open_database() as database:
            row = database.execute(
                """
                SELECT config_location_id
                FROM config_backups
                WHERE config_backup_id = ?;
                """,
                (config_backup_id,),
            ).fetchone()

        if row is None:
            raise ValueError(f"No config backup found with ID {config_backup_id}")

        config_location_id = int(row["config_location_id"])

    resolved_order = _resolve_step_order(profile_id, step_order)

    with open_database() as database:
        cursor = database.execute(
            """
            INSERT INTO profile_steps (
                profile_id,
                step_order,
                step_name,
                action_type,
                config_location_id,
                config_source_type,
                config_variant_id,
                config_backup_id,
                failure_behavior,
                notes
            )
            VALUES (?, ?, ?, 'set_config', ?, ?, ?, ?, ?, ?);
            """,
            (
                profile_id,
                resolved_order,
                step_name,
                config_location_id,
                config_source_type,
                config_variant_id,
                config_backup_id,
                failure_behavior,
                notes,
            ),
        )

        return int(cursor.lastrowid)


def add_launch_executable_step(
    profile_id: int,
    app_id: int,
    step_order: int | None = None,
    step_name: str | None = None,
    launch_arguments: str | None = None,
    launch_working_directory: str | None = None,
    failure_behavior: str = "stop_profile",
    notes: str | None = None,
) -> int:
    _ensure_profile_exists(profile_id)
    _validate_failure_behavior(failure_behavior)

    with open_database() as database:
        app = database.execute(
            """
            SELECT app_id
            FROM app_registry
            WHERE app_id = ?
              AND is_hidden = 0;
            """,
            (app_id,),
        ).fetchone()

    if app is None:
        raise ValueError(f"No active app found with ID {app_id}")

    resolved_order = _resolve_step_order(profile_id, step_order)

    with open_database() as database:
        cursor = database.execute(
            """
            INSERT INTO profile_steps (
                profile_id,
                step_order,
                step_name,
                action_type,
                app_id,
                launch_arguments,
                launch_working_directory,
                failure_behavior,
                notes
            )
            VALUES (?, ?, ?, 'launch_executable', ?, ?, ?, ?, ?);
            """,
            (
                profile_id,
                resolved_order,
                step_name,
                app_id,
                launch_arguments,
                launch_working_directory,
                failure_behavior,
                notes,
            ),
        )

        return int(cursor.lastrowid)


def add_wait_for_process_step(
    profile_id: int,
    process_name: str | None = None,
    process_path: str | None = None,
    timeout_seconds: int = 120,
    step_order: int | None = None,
    step_name: str | None = None,
    failure_behavior: str = "stop_profile",
    notes: str | None = None,
) -> int:
    _ensure_profile_exists(profile_id)
    _validate_failure_behavior(failure_behavior)

    if not process_name and not process_path:
        raise ValueError("Provide process_name or process_path.")

    if timeout_seconds < 0:
        raise ValueError("timeout_seconds must be 0 or greater.")

    resolved_order = _resolve_step_order(profile_id, step_order)

    with open_database() as database:
        cursor = database.execute(
            """
            INSERT INTO profile_steps (
                profile_id,
                step_order,
                step_name,
                action_type,
                wait_process_name,
                wait_process_path,
                wait_timeout_seconds,
                failure_behavior,
                notes
            )
            VALUES (?, ?, ?, 'wait_for_process', ?, ?, ?, ?, ?);
            """,
            (
                profile_id,
                resolved_order,
                step_name,
                process_name,
                process_path,
                timeout_seconds,
                failure_behavior,
                notes,
            ),
        )

        return int(cursor.lastrowid)


def add_delay_step(
    profile_id: int,
    delay_seconds: int,
    step_order: int | None = None,
    step_name: str | None = None,
    failure_behavior: str = "stop_profile",
    notes: str | None = None,
) -> int:
    _ensure_profile_exists(profile_id)
    _validate_failure_behavior(failure_behavior)

    if delay_seconds < 0:
        raise ValueError("delay_seconds must be 0 or greater.")

    resolved_order = _resolve_step_order(profile_id, step_order)

    with open_database() as database:
        cursor = database.execute(
            """
            INSERT INTO profile_steps (
                profile_id,
                step_order,
                step_name,
                action_type,
                delay_seconds,
                failure_behavior,
                notes
            )
            VALUES (?, ?, ?, 'delay', ?, ?, ?);
            """,
            (
                profile_id,
                resolved_order,
                step_name,
                delay_seconds,
                failure_behavior,
                notes,
            ),
        )

        return int(cursor.lastrowid)


def add_open_url_step(
    profile_id: int,
    url: str,
    step_order: int | None = None,
    step_name: str | None = None,
    failure_behavior: str = "stop_profile",
    notes: str | None = None,
) -> int:
    _ensure_profile_exists(profile_id)
    _validate_failure_behavior(failure_behavior)

    if not url:
        raise ValueError("url must not be empty.")

    resolved_order = _resolve_step_order(profile_id, step_order)

    with open_database() as database:
        cursor = database.execute(
            """
            INSERT INTO profile_steps (
                profile_id,
                step_order,
                step_name,
                action_type,
                url,
                failure_behavior,
                notes
            )
            VALUES (?, ?, ?, 'open_url', ?, ?, ?);
            """,
            (
                profile_id,
                resolved_order,
                step_name,
                url,
                failure_behavior,
                notes,
            ),
        )

        return int(cursor.lastrowid)


def list_profile_steps(profile_id: int) -> list[ProfileStep]:
    _ensure_profile_exists(profile_id)

    with open_database() as database:
        rows = database.execute(
            """
            SELECT
                profile_step_id,
                profile_id,
                step_order,
                step_name,
                action_type,
                is_enabled,
                config_location_id,
                config_source_type,
                config_variant_id,
                config_backup_id,
                app_id,
                launch_arguments,
                launch_working_directory,
                wait_process_name,
                wait_process_path,
                wait_timeout_seconds,
                delay_seconds,
                url,
                failure_behavior,
                notes
            FROM profile_steps
            WHERE profile_id = ?
            ORDER BY step_order;
            """,
            (profile_id,),
        ).fetchall()

    return [
        ProfileStep(
            profile_step_id=int(row["profile_step_id"]),
            profile_id=int(row["profile_id"]),
            step_order=int(row["step_order"]),
            step_name=row["step_name"],
            action_type=str(row["action_type"]),
            is_enabled=bool(row["is_enabled"]),
            config_location_id=row["config_location_id"],
            config_source_type=row["config_source_type"],
            config_variant_id=row["config_variant_id"],
            config_backup_id=row["config_backup_id"],
            app_id=row["app_id"],
            launch_arguments=row["launch_arguments"],
            launch_working_directory=row["launch_working_directory"],
            wait_process_name=row["wait_process_name"],
            wait_process_path=row["wait_process_path"],
            wait_timeout_seconds=int(row["wait_timeout_seconds"]),
            delay_seconds=row["delay_seconds"],
            url=row["url"],
            failure_behavior=str(row["failure_behavior"]),
            notes=row["notes"],
        )
        for row in rows
    ]


def print_profile_steps(profile_id: int) -> None:
    try:
        steps = list_profile_steps(profile_id)
    except ValueError as error:
        print(error)
        return

    if not steps:
        print(f"No steps registered for profile [{profile_id}].")
        return

    for step in steps:
        print(f"[{step.profile_step_id}] #{step.step_order} {step.action_type}")

        if step.step_name:
            print(f"  name:      {step.step_name}")

        if step.action_type == "set_config":
            print(f"  source:    {step.config_source_type}")
            print(f"  location:  {step.config_location_id}")

            if step.config_variant_id is not None:
                print(f"  variant:   {step.config_variant_id}")

            if step.config_backup_id is not None:
                print(f"  backup:    {step.config_backup_id}")

        elif step.action_type == "launch_executable":
            print(f"  app_id:    {step.app_id}")

            if step.launch_arguments:
                print(f"  args:      {step.launch_arguments}")

            if step.launch_working_directory:
                print(f"  cwd:       {step.launch_working_directory}")

        elif step.action_type == "wait_for_process":
            if step.wait_process_name:
                print(f"  process:   {step.wait_process_name}")

            if step.wait_process_path:
                print(f"  path:      {step.wait_process_path}")

            print(f"  timeout:   {step.wait_timeout_seconds}")

        elif step.action_type == "delay":
            print(f"  seconds:   {step.delay_seconds}")

        elif step.action_type == "open_url":
            print(f"  url:       {step.url}")

        print(f"  enabled:   {step.is_enabled}")
        print(f"  on fail:   {step.failure_behavior}")

        if step.notes:
            print(f"  notes:     {step.notes}")

        print()


def delete_profile_step(profile_step_id: int) -> None:
    with open_database() as database:
        row = database.execute(
            """
            SELECT profile_step_id
            FROM profile_steps
            WHERE profile_step_id = ?;
            """,
            (profile_step_id,),
        ).fetchone()

        if row is None:
            raise ValueError(f"No profile step found with ID {profile_step_id}")

        database.execute(
            """
            DELETE FROM profile_steps
            WHERE profile_step_id = ?;
            """,
            (profile_step_id,),
        )
def move_profile_step(
    step_id: int,
    after_step_id_text: str,
    before_step_id_text: str,
) -> None:
    with open_database() as database:
        moving_step = database.execute(
            """
            SELECT profile_step_id, profile_id
            FROM profile_steps
            WHERE profile_step_id = ?;
            """,
            (step_id,),
        ).fetchone()

        if moving_step is None:
            raise ValueError(f"No profile step found with ID {step_id}")

        profile_id = int(moving_step["profile_id"])

        rows = database.execute(
            """
            SELECT profile_step_id
            FROM profile_steps
            WHERE profile_id = ?
            ORDER BY step_order, profile_step_id;
            """,
            (profile_id,),
        ).fetchall()

        ordered_step_ids = [
            int(row["profile_step_id"])
            for row in rows
            if int(row["profile_step_id"]) != step_id
        ]

        try:
            after_step_id = int(after_step_id_text)
        except ValueError as error:
            raise ValueError("--step-pos first value must be a step ID") from error

        if after_step_id not in ordered_step_ids:
            raise ValueError(f"Step [{after_step_id}] is not in the same profile as step [{step_id}]")

        after_index = ordered_step_ids.index(after_step_id)

        if before_step_id_text == "end":
            insert_index = after_index + 1

            if insert_index != len(ordered_step_ids):
                insert_index = len(ordered_step_ids)

        else:
            try:
                before_step_id = int(before_step_id_text)
            except ValueError as error:
                raise ValueError("--step-pos second value must be a step ID or end") from error

            if before_step_id not in ordered_step_ids:
                raise ValueError(f"Step [{before_step_id}] is not in the same profile as step [{step_id}]")

            before_index = ordered_step_ids.index(before_step_id)

            if before_index < after_index:
                raise ValueError("The before step must come after the after step.")

            insert_index = before_index

        ordered_step_ids.insert(insert_index, step_id)

        for index, profile_step_id in enumerate(ordered_step_ids, start=1):
            database.execute(
                """
                UPDATE profile_steps
                SET step_order = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE profile_step_id = ?;
                """,
                (index, profile_step_id),
            )
