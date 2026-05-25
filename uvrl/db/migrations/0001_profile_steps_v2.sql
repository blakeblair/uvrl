PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS profile_steps;

CREATE TABLE IF NOT EXISTS profile_steps (
    profile_step_id INTEGER PRIMARY KEY AUTOINCREMENT,

    profile_id INTEGER NOT NULL,

    step_order INTEGER NOT NULL,
    step_name TEXT,

    action_type TEXT NOT NULL CHECK (
        action_type IN (
            'set_config',
            'launch_executable',
            'wait_for_process',
            'delay',
            'open_url'
        )
    ),

    is_enabled INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),

    config_location_id INTEGER,

    config_source_type TEXT CHECK (
        config_source_type IS NULL
        OR config_source_type IN ('variant', 'backup')
    ),

    config_variant_id INTEGER,
    config_backup_id INTEGER,

    app_id INTEGER,
    launch_arguments TEXT,
    launch_working_directory TEXT,

    wait_process_name TEXT,
    wait_process_path TEXT,
    wait_timeout_seconds INTEGER NOT NULL DEFAULT 120 CHECK (wait_timeout_seconds >= 0),

    delay_seconds INTEGER CHECK (delay_seconds IS NULL OR delay_seconds >= 0),

    url TEXT,

    failure_behavior TEXT NOT NULL DEFAULT 'stop_profile' CHECK (
        failure_behavior IN ('stop_profile', 'continue')
    ),

    notes TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (profile_id)
        REFERENCES profiles(profile_id)
        ON DELETE CASCADE,

    FOREIGN KEY (config_location_id)
        REFERENCES config_locations(config_location_id)
        ON DELETE SET NULL,

    FOREIGN KEY (config_variant_id)
        REFERENCES config_variants(config_variant_id)
        ON DELETE SET NULL,

    FOREIGN KEY (config_backup_id)
        REFERENCES config_backups(config_backup_id)
        ON DELETE SET NULL,

    FOREIGN KEY (app_id)
        REFERENCES app_registry(app_id)
        ON DELETE SET NULL,

    UNIQUE(profile_id, step_order)
);

CREATE INDEX IF NOT EXISTS idx_profile_steps_profile_order
    ON profile_steps(profile_id, step_order);

CREATE INDEX IF NOT EXISTS idx_profile_steps_action_type
    ON profile_steps(action_type);

CREATE INDEX IF NOT EXISTS idx_profile_steps_app_id
    ON profile_steps(app_id);

CREATE INDEX IF NOT EXISTS idx_profile_steps_config_variant
    ON profile_steps(config_variant_id);

CREATE INDEX IF NOT EXISTS idx_profile_steps_config_backup
    ON profile_steps(config_backup_id);