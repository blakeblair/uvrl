from __future__ import annotations

from dataclasses import dataclass

from uvrl.app.services.database import open_database


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    step_id: int | None
    step_order: int | None
    message: str


@dataclass(frozen=True)
class ProfileValidationResult:
    profile_id: int
    profile_name: str
    issues: list[ValidationIssue]

    @property
    def is_valid(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


def _add_error(
    issues: list[ValidationIssue],
    message: str,
    step_id: int | None = None,
    step_order: int | None = None,
) -> None:
    issues.append(
        ValidationIssue(
            severity="error",
            step_id=step_id,
            step_order=step_order,
            message=message,
        )
    )


def _add_warning(
    issues: list[ValidationIssue],
    message: str,
    step_id: int | None = None,
    step_order: int | None = None,
) -> None:
    issues.append(
        ValidationIssue(
            severity="warning",
            step_id=step_id,
            step_order=step_order,
            message=message,
        )
    )


def validate_profile(profile_id: int) -> ProfileValidationResult:
    issues: list[ValidationIssue] = []

    with open_database() as database:
        profile = database.execute(
            """
            SELECT
                profile_id,
                profile_name
            FROM profiles
            WHERE profile_id = ?
              AND is_archived = 0;
            """,
            (profile_id,),
        ).fetchone()

        if profile is None:
            return ProfileValidationResult(
                profile_id=profile_id,
                profile_name="(missing profile)",
                issues=[
                    ValidationIssue(
                        severity="error",
                        step_id=None,
                        step_order=None,
                        message=f"No active profile found with ID {profile_id}.",
                    )
                ],
            )

        steps = database.execute(
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

        if not steps:
            _add_warning(issues, "Profile has no steps.")

        seen_orders: set[int] = set()

        for step in steps:
            step_id = int(step["profile_step_id"])
            step_order = int(step["step_order"])
            action_type = str(step["action_type"])

            if step_order in seen_orders:
                _add_error(
                    issues,
                    f"Duplicate step order {step_order}.",
                    step_id=step_id,
                    step_order=step_order,
                )
            seen_orders.add(step_order)

            if not bool(step["is_enabled"]):
                _add_warning(
                    issues,
                    "Step is disabled and will be skipped.",
                    step_id=step_id,
                    step_order=step_order,
                )

            failure_behavior = str(step["failure_behavior"])
            if failure_behavior not in {"stop_profile", "continue"}:
                _add_error(
                    issues,
                    f"Invalid failure behavior: {failure_behavior}.",
                    step_id=step_id,
                    step_order=step_order,
                )

            if action_type == "set_config":
                config_source_type = step["config_source_type"]
                config_location_id = step["config_location_id"]
                config_variant_id = step["config_variant_id"]
                config_backup_id = step["config_backup_id"]

                if config_source_type not in {"variant", "backup"}:
                    _add_error(
                        issues,
                        "set_config requires config_source_type to be variant or backup.",
                        step_id=step_id,
                        step_order=step_order,
                    )

                if config_location_id is None:
                    _add_error(
                        issues,
                        "set_config requires config_location_id.",
                        step_id=step_id,
                        step_order=step_order,
                    )

                if config_source_type == "variant":
                    if config_variant_id is None:
                        _add_error(
                            issues,
                            "set_config with source variant requires config_variant_id.",
                            step_id=step_id,
                            step_order=step_order,
                        )
                    else:
                        variant = database.execute(
                            """
                            SELECT config_location_id
                            FROM config_variants
                            WHERE config_variant_id = ?
                              AND is_archived = 0;
                            """,
                            (config_variant_id,),
                        ).fetchone()

                        if variant is None:
                            _add_error(
                                issues,
                                f"Config variant [{config_variant_id}] does not exist or is archived.",
                                step_id=step_id,
                                step_order=step_order,
                            )
                        elif config_location_id is not None and int(variant["config_location_id"]) != int(config_location_id):
                            _add_error(
                                issues,
                                "set_config config_location_id does not match the selected variant.",
                                step_id=step_id,
                                step_order=step_order,
                            )

                    if config_backup_id is not None:
                        _add_warning(
                            issues,
                            "set_config source is variant, but config_backup_id is also set and will be ignored.",
                            step_id=step_id,
                            step_order=step_order,
                        )

                if config_source_type == "backup":
                    if config_backup_id is None:
                        _add_error(
                            issues,
                            "set_config with source backup requires config_backup_id.",
                            step_id=step_id,
                            step_order=step_order,
                        )
                    else:
                        backup = database.execute(
                            """
                            SELECT config_location_id
                            FROM config_backups
                            WHERE config_backup_id = ?;
                            """,
                            (config_backup_id,),
                        ).fetchone()

                        if backup is None:
                            _add_error(
                                issues,
                                f"Config backup [{config_backup_id}] does not exist.",
                                step_id=step_id,
                                step_order=step_order,
                            )
                        elif config_location_id is not None and int(backup["config_location_id"]) != int(config_location_id):
                            _add_error(
                                issues,
                                "set_config config_location_id does not match the selected backup.",
                                step_id=step_id,
                                step_order=step_order,
                            )

                    if config_variant_id is not None:
                        _add_warning(
                            issues,
                            "set_config source is backup, but config_variant_id is also set and will be ignored.",
                            step_id=step_id,
                            step_order=step_order,
                        )

            elif action_type == "launch_executable":
                app_id = step["app_id"]

                if app_id is None:
                    _add_error(
                        issues,
                        "launch_executable requires app_id.",
                        step_id=step_id,
                        step_order=step_order,
                    )
                else:
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
                        _add_error(
                            issues,
                            f"App [{app_id}] does not exist or is hidden.",
                            step_id=step_id,
                            step_order=step_order,
                        )

            elif action_type == "wait_for_process":
                process_name = step["wait_process_name"]
                process_path = step["wait_process_path"]
                timeout_seconds = int(step["wait_timeout_seconds"])

                if not process_name and not process_path:
                    _add_error(
                        issues,
                        "wait_for_process requires wait_process_name or wait_process_path.",
                        step_id=step_id,
                        step_order=step_order,
                    )

                if timeout_seconds < 0:
                    _add_error(
                        issues,
                        "wait_for_process timeout must be 0 or greater.",
                        step_id=step_id,
                        step_order=step_order,
                    )

            elif action_type == "delay":
                delay_seconds = step["delay_seconds"]

                if delay_seconds is None:
                    _add_error(
                        issues,
                        "delay requires delay_seconds.",
                        step_id=step_id,
                        step_order=step_order,
                    )
                elif int(delay_seconds) < 0:
                    _add_error(
                        issues,
                        "delay_seconds must be 0 or greater.",
                        step_id=step_id,
                        step_order=step_order,
                    )

            elif action_type == "open_url":
                url = step["url"]

                if not url:
                    _add_error(
                        issues,
                        "open_url requires url.",
                        step_id=step_id,
                        step_order=step_order,
                    )
                elif not (
                    str(url).startswith("http://")
                    or str(url).startswith("https://")
                    or str(url).startswith("file://")
                ):
                    _add_warning(
                        issues,
                        "open_url should usually start with http://, https://, or file://.",
                        step_id=step_id,
                        step_order=step_order,
                    )

            else:
                _add_error(
                    issues,
                    f"Unknown action_type: {action_type}.",
                    step_id=step_id,
                    step_order=step_order,
                )

    return ProfileValidationResult(
        profile_id=profile_id,
        profile_name=str(profile["profile_name"]),
        issues=issues,
    )


def print_profile_validation(profile_id: int) -> None:
    result = validate_profile(profile_id)

    print(f"Profile [{result.profile_id}] {result.profile_name}")

    if not result.issues:
        print("Validation passed. No issues found.")
        return

    for issue in result.issues:
        location = ""

        if issue.step_id is not None:
            location = f" step [{issue.step_id}]"

            if issue.step_order is not None:
                location += f" order #{issue.step_order}"

        print(f"{issue.severity.upper()}:{location} {issue.message}")

    if result.is_valid:
        print("Validation completed with warnings.")
    else:
        print("Validation failed.")