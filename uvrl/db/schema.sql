PRAGMA foreign_keys = ON;

-- ============================================================
-- UVRL SQLite Schema
-- ============================================================
-- Stores:
-- app registry
-- config locations
-- config variants
-- config backups
-- profiles
-- profile steps
-- user scripts
-- app settings
-- ============================================================


-- ------------------------------------------------------------
-- App registry
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS app_registry (
    app_id INTEGER PRIMARY KEY AUTOINCREMENT,

    display_name TEXT NOT NULL,
    internal_name TEXT,

    launch_kind TEXT NOT NULL DEFAULT 'native',
    -- native, steam_app, flatpak, python, bash, powershell, batch, custom

    platform TEXT NOT NULL DEFAULT 'any',
    -- linux, windows, any

    executable_path TEXT,
    working_directory TEXT,
    default_arguments TEXT,

    steam_app_id TEXT,
    flatpak_app_id TEXT,

    source TEXT NOT NULL DEFAULT 'manual',
    -- manual, discovered, built_in

    is_managed INTEGER NOT NULL DEFAULT 1,
    is_hidden INTEGER NOT NULL DEFAULT 0,

    notes TEXT,

    last_seen_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_app_registry_unique_native
    ON app_registry(executable_path, platform)
    WHERE executable_path IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_app_registry_unique_steam
    ON app_registry(steam_app_id, platform)
    WHERE steam_app_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_app_registry_unique_flatpak
    ON app_registry(flatpak_app_id, platform)
    WHERE flatpak_app_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_app_registry_display_name
    ON app_registry(display_name);

CREATE INDEX IF NOT EXISTS idx_app_registry_platform
    ON app_registry(platform);


-- ------------------------------------------------------------
-- Config locations
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS config_locations (
    config_location_id INTEGER PRIMARY KEY AUTOINCREMENT,

    display_name TEXT NOT NULL,

    file_path TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'any',
    -- linux, windows, any

    file_kind TEXT NOT NULL DEFAULT 'unknown',
    -- json, vdf, ini, toml, yaml, text, binary, unknown

    app_id INTEGER,

    is_managed INTEGER NOT NULL DEFAULT 1,
    is_hidden INTEGER NOT NULL DEFAULT 0,

    notes TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (app_id)
        REFERENCES app_registry(app_id)
        ON DELETE SET NULL,

    UNIQUE(file_path, platform)
);

CREATE INDEX IF NOT EXISTS idx_config_locations_file_path
    ON config_locations(file_path);

CREATE INDEX IF NOT EXISTS idx_config_locations_app_id
    ON config_locations(app_id);


-- ------------------------------------------------------------
-- Config variants
-- ------------------------------------------------------------
-- Stored in SQL and also exported as individual files under:
-- data/config_variants/
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS config_variants (
    config_variant_id INTEGER PRIMARY KEY AUTOINCREMENT,

    config_location_id INTEGER NOT NULL,

    variant_name TEXT NOT NULL,
    description TEXT,

    content_text TEXT,
    content_blob BLOB,

    content_encoding TEXT NOT NULL DEFAULT 'utf-8',
    content_sha256 TEXT,

    exported_file_path TEXT,

    is_default INTEGER NOT NULL DEFAULT 0,
    is_archived INTEGER NOT NULL DEFAULT 0,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (config_location_id)
        REFERENCES config_locations(config_location_id)
        ON DELETE CASCADE,

    UNIQUE(config_location_id, variant_name)
);

CREATE INDEX IF NOT EXISTS idx_config_variants_location
    ON config_variants(config_location_id);


-- ------------------------------------------------------------
-- Profiles
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS profiles (
    profile_id INTEGER PRIMARY KEY AUTOINCREMENT,

    profile_name TEXT NOT NULL UNIQUE,
    description TEXT,

    platform TEXT NOT NULL DEFAULT 'any',
    -- linux, windows, any

    restore_configs_on_exit INTEGER NOT NULL DEFAULT 0,

    is_default INTEGER NOT NULL DEFAULT 0,
    is_archived INTEGER NOT NULL DEFAULT 0,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- ------------------------------------------------------------
-- Config backups
-- ------------------------------------------------------------
-- Stored in SQL and also exported as individual files under:
-- data/config_backups/
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS config_backups (
    config_backup_id INTEGER PRIMARY KEY AUTOINCREMENT,

    config_location_id INTEGER NOT NULL,
    profile_id INTEGER,

    backup_reason TEXT NOT NULL DEFAULT 'before_variant_apply',
    -- before_variant_apply, manual_backup, before_restore, other

    original_file_path TEXT NOT NULL,

    content_text TEXT,
    content_blob BLOB,

    content_encoding TEXT NOT NULL DEFAULT 'utf-8',
    content_sha256 TEXT,

    exported_file_path TEXT,

    backed_up_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    restored_at TEXT,

    notes TEXT,

    FOREIGN KEY (config_location_id)
        REFERENCES config_locations(config_location_id)
        ON DELETE CASCADE,

    FOREIGN KEY (profile_id)
        REFERENCES profiles(profile_id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_config_backups_location
    ON config_backups(config_location_id);

CREATE INDEX IF NOT EXISTS idx_config_backups_profile
    ON config_backups(profile_id);


-- ------------------------------------------------------------
-- User scripts
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS user_scripts (
    script_id INTEGER PRIMARY KEY AUTOINCREMENT,

    script_name TEXT NOT NULL,
    description TEXT,

    script_kind TEXT NOT NULL DEFAULT 'bash',
    -- bash, python, powershell, batch, custom

    platform TEXT NOT NULL DEFAULT 'any',
    -- linux, windows, any

    script_content TEXT NOT NULL,

    working_directory TEXT,
    default_arguments TEXT,

    is_managed INTEGER NOT NULL DEFAULT 1,
    is_archived INTEGER NOT NULL DEFAULT 0,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(script_name, platform)
);

CREATE INDEX IF NOT EXISTS idx_user_scripts_name
    ON user_scripts(script_name);


-- ------------------------------------------------------------
-- Profile steps
-- ------------------------------------------------------------
-- Ordered actions inside a profile.
--
-- Initial UVRL step types:
--
-- set_config
--   Write stored config content to a managed config location.
--   Source may be a config variant or a config backup/original.
--
-- launch_executable
--   Launch an app from app_registry.
--   Elevation prompts are handled by the user/OS.
--
-- wait_for_process
--   Wait until a process name or process path is detected.
--
-- delay
--   Wait a fixed number of seconds.
--
-- open_url
--   Open a URL in the user's default browser.
--   UVRL does not fetch, download, parse, or contact the URL internally.
-- ------------------------------------------------------------

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

    -- set_config fields
    config_location_id INTEGER,

    config_source_type TEXT CHECK (
        config_source_type IS NULL
        OR config_source_type IN ('variant', 'backup')
    ),

    config_variant_id INTEGER,
    config_backup_id INTEGER,

    -- launch_executable fields
    app_id INTEGER,
    launch_arguments TEXT,
    launch_argument_mode TEXT NOT NULL DEFAULT 'supplement',
    launch_working_directory TEXT,

    -- wait_for_process fields
    wait_process_name TEXT,
    wait_process_path TEXT,
    wait_timeout_seconds INTEGER NOT NULL DEFAULT 120 CHECK (wait_timeout_seconds >= 0),

    -- delay fields
    delay_seconds INTEGER CHECK (delay_seconds IS NULL OR delay_seconds >= 0),

    -- open_url fields
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


-- ------------------------------------------------------------
-- App settings
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS app_settings (
    setting_key TEXT PRIMARY KEY,

    setting_value TEXT,
    value_type TEXT NOT NULL DEFAULT 'string',
    -- string, integer, float, boolean, json

    description TEXT,

    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO app_settings (
    setting_key,
    setting_value,
    value_type,
    description
)
VALUES
    (
        'config_variants_directory',
        'data/config_variants',
        'string',
        'Directory where exported config variant files are stored.'
    ),
    (
        'config_backups_directory',
        'data/config_backups',
        'string',
        'Directory where exported original config backup files are stored.'
    ),
    (
        'updates_url',
        'https://github.com/blakeblair/uvrl',
        'string',
        'Manual update check URL. UVRL opens this in the user default browser and does not fetch it internally.'
    );
