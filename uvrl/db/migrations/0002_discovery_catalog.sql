PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS discovery_catalog;

CREATE TABLE discovery_catalog (
    discovery_catalog_id INTEGER PRIMARY KEY AUTOINCREMENT,

    target_kind TEXT NOT NULL CHECK (
        target_kind IN ('app', 'config')
    ),

    display_name TEXT NOT NULL,

    category TEXT NOT NULL DEFAULT 'general',

    platform TEXT NOT NULL DEFAULT 'any' CHECK (
        platform IN ('linux', 'windows', 'any')
    ),

    match_type TEXT NOT NULL CHECK (
        match_type IN (
            'filename_exact',
            'filename_contains',
            'path_contains',
            'steam_app_id',
            'flatpak_app_id'
        )
    ),

    match_value TEXT NOT NULL,

    launch_kind TEXT CHECK (
        launch_kind IS NULL OR launch_kind IN (
            'native',
            'steam_app',
            'flatpak',
            'python',
            'bash',
            'powershell',
            'batch',
            'custom'
        )
    ),

    file_kind TEXT CHECK (
        file_kind IS NULL OR file_kind IN (
            'json',
            'vdf',
            'ini',
            'toml',
            'yaml',
            'text',
            'binary',
            'unknown'
        )
    ),

    steam_app_id TEXT,
    flatpak_app_id TEXT,

    priority INTEGER NOT NULL DEFAULT 100,

    is_enabled INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),

    notes TEXT,

    source_name TEXT,
    source_url TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(target_kind, platform, match_type, match_value)
);

CREATE INDEX IF NOT EXISTS idx_discovery_catalog_kind
    ON discovery_catalog(target_kind);

CREATE INDEX IF NOT EXISTS idx_discovery_catalog_category
    ON discovery_catalog(category);

CREATE INDEX IF NOT EXISTS idx_discovery_catalog_platform
    ON discovery_catalog(platform);

CREATE INDEX IF NOT EXISTS idx_discovery_catalog_display_name
    ON discovery_catalog(display_name);

CREATE INDEX IF NOT EXISTS idx_discovery_catalog_match
    ON discovery_catalog(match_type, match_value);


INSERT OR IGNORE INTO discovery_catalog (
    target_kind,
    display_name,
    category,
    platform,
    match_type,
    match_value,
    launch_kind,
    file_kind,
    steam_app_id,
    flatpak_app_id,
    priority,
    notes,
    source_name,
    source_url
)
VALUES

-- Steam and SteamVR

('app', 'Steam', 'utility', 'linux', 'filename_exact', 'steam', 'native', NULL, NULL, NULL, 10, 'Steam client executable on Linux.', NULL, NULL),
('app', 'Steam', 'utility', 'windows', 'filename_exact', 'steam.exe', 'native', NULL, NULL, NULL, 10, 'Steam client executable on Windows.', NULL, NULL),

('app', 'SteamVR', 'runtime', 'any', 'steam_app_id', '250820', 'steam_app', NULL, '250820', NULL, 10, 'SteamVR runtime.', NULL, NULL),

('app', 'OpenVR Space Calibrator', 'utility', 'any', 'steam_app_id', '3368750', 'steam_app', NULL, '3368750', NULL, 30, 'Steam app target for Space Calibrator.', NULL, NULL),
('app', 'OpenVR Space Calibrator', 'utility', 'windows', 'filename_contains', 'spacecalibrator', 'native', NULL, NULL, NULL, 60, 'Native Space Calibrator executable match.', NULL, NULL),
('app', 'OpenVR Space Calibrator', 'utility', 'linux', 'filename_contains', 'spacecalibrator', 'native', NULL, NULL, NULL, 60, 'Space Calibrator executable or wrapper match.', NULL, NULL),

('app', 'OVR Advanced Settings', 'utility', 'any', 'steam_app_id', '1009850', 'steam_app', NULL, '1009850', NULL, 70, 'Steam app target for OVR Advanced Settings.', NULL, NULL),
('app', 'OVR Toolkit', 'overlay', 'any', 'steam_app_id', '1068820', 'steam_app', NULL, '1068820', NULL, 70, 'Steam app target for OVR Toolkit.', NULL, NULL),
('app', 'XSOverlay', 'overlay', 'any', 'steam_app_id', '1173510', 'steam_app', NULL, '1173510', NULL, 70, 'Steam app target for XSOverlay.', NULL, NULL),

-- VR platforms and games

('app', 'VRChat', 'vr_platform', 'any', 'steam_app_id', '438100', 'steam_app', NULL, '438100', NULL, 10, 'Prefer Steam app ID so Steam handles the correct VRChat launcher and EAC path.', NULL, NULL),

('app', 'Resonite', 'vr_platform', 'any', 'steam_app_id', '2519830', 'steam_app', NULL, '2519830', NULL, 20, 'Steam app target for Resonite.', NULL, NULL),
('app', 'Resonite', 'vr_platform', 'windows', 'filename_contains', 'resonite', 'native', NULL, NULL, NULL, 60, 'Native Resonite executable fallback.', NULL, NULL),
('app', 'Resonite', 'vr_platform', 'linux', 'filename_contains', 'resonite', 'native', NULL, NULL, NULL, 60, 'Native Resonite executable or wrapper fallback.', NULL, NULL),

('app', 'ChilloutVR', 'vr_platform', 'any', 'steam_app_id', '661130', 'steam_app', NULL, '661130', NULL, 30, 'Steam app target for ChilloutVR.', NULL, NULL),
('app', 'ChilloutVR', 'vr_platform', 'windows', 'filename_contains', 'chilloutvr', 'native', NULL, NULL, NULL, 70, 'Native ChilloutVR executable fallback.', NULL, NULL),
('app', 'ChilloutVR', 'vr_platform', 'linux', 'filename_contains', 'chilloutvr', 'native', NULL, NULL, NULL, 70, 'Native ChilloutVR executable or wrapper fallback.', NULL, NULL),

('app', 'NeosVR', 'vr_platform', 'any', 'steam_app_id', '740250', 'steam_app', NULL, '740250', NULL, 80, 'Legacy NeosVR Steam app target.', NULL, NULL),
('app', 'NeosVR', 'vr_platform', 'windows', 'filename_contains', 'neos', 'native', NULL, NULL, NULL, 90, 'Native NeosVR executable fallback.', NULL, NULL),
('app', 'NeosVR', 'vr_platform', 'linux', 'filename_contains', 'neos', 'native', NULL, NULL, NULL, 90, 'Native NeosVR executable or wrapper fallback.', NULL, NULL),

('app', 'Half-Life: Alyx', 'vr_platform', 'any', 'steam_app_id', '546560', 'steam_app', NULL, '546560', NULL, 50, 'Steam app target for Half-Life: Alyx.', NULL, NULL),

('app', 'Massive Loop', 'vr_platform', 'any', 'filename_contains', 'massiveloop', 'native', NULL, NULL, NULL, 100, 'User-mentioned VR platform or game. Verify exact executable or Steam app ID later.', NULL, NULL),
('app', 'RhubarbVR', 'vr_platform', 'any', 'filename_contains', 'rhubarbvr', 'native', NULL, NULL, NULL, 100, 'User-mentioned VR platform or game. Verify exact executable or Steam app ID later.', NULL, NULL),

-- Streaming, runtimes, and compatibility

('app', 'WiVRn Server', 'streaming', 'linux', 'filename_exact', 'wivrn-server', 'native', NULL, NULL, NULL, 10, 'WiVRn server executable.', 'LVRA Wiki', 'https://wiki.vronlinux.org/'),
('app', 'WiVRn', 'streaming', 'linux', 'filename_contains', 'wivrn', 'native', NULL, NULL, NULL, 20, 'Fallback WiVRn executable match.', 'LVRA Wiki', 'https://wiki.vronlinux.org/'),

('app', 'WayVR', 'streaming', 'linux', 'filename_exact', 'wayvr', 'native', NULL, NULL, NULL, 20, 'WayVR executable.', NULL, NULL),
('app', 'WayVR', 'streaming', 'linux', 'filename_contains', 'wayvr', 'native', NULL, NULL, NULL, 40, 'Fallback WayVR executable match.', NULL, NULL),

('app', 'Virtual Desktop Classic', 'streaming', 'any', 'steam_app_id', '382110', 'steam_app', NULL, '382110', NULL, 50, 'Steam app target for Virtual Desktop Classic.', NULL, NULL),
('app', 'Virtual Desktop Streamer', 'streaming', 'windows', 'filename_exact', 'VirtualDesktop.Streamer.exe', 'native', NULL, NULL, NULL, 20, 'Native Virtual Desktop Streamer executable.', NULL, NULL),
('app', 'Virtual Desktop', 'streaming', 'windows', 'filename_contains', 'virtualdesktop', 'native', NULL, NULL, NULL, 70, 'Fallback Virtual Desktop native match.', NULL, NULL),

('app', 'Steam Link', 'streaming', 'any', 'filename_contains', 'steamlink', 'native', NULL, NULL, NULL, 80, 'Steam Link related executable or wrapper.', NULL, NULL),

('app', 'ALVR', 'streaming', 'linux', 'filename_contains', 'alvr', 'native', NULL, NULL, NULL, 30, 'ALVR Linux launcher or streamer.', 'LVRA Wiki', 'https://wiki.vronlinux.org/'),
('app', 'ALVR', 'streaming', 'windows', 'filename_contains', 'alvr', 'native', NULL, NULL, NULL, 30, 'ALVR Windows launcher or streamer.', NULL, NULL),

('app', 'ALXR', 'streaming', 'linux', 'filename_contains', 'alxr', 'native', NULL, NULL, NULL, 35, 'ALXR executable or launcher.', 'LVRA Wiki', 'https://wiki.vronlinux.org/'),
('app', 'ALXR', 'streaming', 'windows', 'filename_contains', 'alxr', 'native', NULL, NULL, NULL, 35, 'ALXR executable or launcher.', NULL, NULL),

('app', 'Monado', 'runtime', 'linux', 'filename_contains', 'monado', 'native', NULL, NULL, NULL, 40, 'Monado related executable.', 'LVRA Wiki', 'https://wiki.vronlinux.org/'),
('app', 'Envision', 'runtime', 'linux', 'filename_contains', 'envision', 'native', NULL, NULL, NULL, 50, 'Envision related executable or launcher.', 'LVRA Wiki', 'https://wiki.vronlinux.org/'),

('app', 'XRizer', 'compatibility', 'linux', 'filename_contains', 'xrizer', 'native', NULL, NULL, NULL, 35, 'XRizer related executable or wrapper.', 'LVRA Wiki', 'https://wiki.vronlinux.org/'),
('app', 'OpenComposite', 'compatibility', 'linux', 'filename_contains', 'opencomposite', 'native', NULL, NULL, NULL, 35, 'OpenComposite related executable or wrapper. Alternative to XRizer in some workflows.', 'LVRA Wiki', 'https://wiki.vronlinux.org/'),
('app', 'OpenComposite', 'compatibility', 'windows', 'filename_contains', 'opencomposite', 'native', NULL, NULL, NULL, 45, 'OpenComposite launcher or runtime switcher on Windows.', NULL, NULL),

-- Overlays and desktop in VR tools

('app', 'wlx-overlay-s', 'overlay', 'linux', 'filename_contains', 'wlx-overlay', 'native', NULL, NULL, NULL, 50, 'wlx-overlay-s or related desktop overlay executable.', 'LVRA Wiki', 'https://wiki.vronlinux.org/'),
('app', 'wlx-overlay', 'overlay', 'linux', 'filename_contains', 'wlx', 'native', NULL, NULL, NULL, 80, 'Fallback wlx overlay match.', 'LVRA Wiki', 'https://wiki.vronlinux.org/'),

-- VRChat peripheral and support tools

('app', 'VRCX', 'utility', 'windows', 'filename_exact', 'VRCX.exe', 'native', NULL, NULL, NULL, 60, 'VRCX on Windows.', NULL, NULL),
('app', 'VRCX', 'utility', 'linux', 'filename_contains', 'vrcx', 'native', NULL, NULL, NULL, 70, 'VRCX on Linux if installed as native or wrapper.', NULL, NULL),

('app', 'VRCOSC', 'peripheral', 'windows', 'filename_exact', 'VRCOSC.exe', 'native', NULL, NULL, NULL, 50, 'VRCOSC on Windows.', NULL, NULL),
('app', 'VRCOSC', 'peripheral', 'linux', 'filename_contains', 'vrcosc', 'native', NULL, NULL, NULL, 60, 'VRCOSC on Linux if installed as native or wrapper.', NULL, NULL),

('app', 'VRChat Face Tracking', 'peripheral', 'windows', 'filename_contains', 'vrchatfacetracking', 'native', NULL, NULL, NULL, 60, 'VRChat Face Tracking executable.', NULL, NULL),
('app', 'VRChat Face Tracking', 'peripheral', 'linux', 'filename_contains', 'vrchatfacetracking', 'native', NULL, NULL, NULL, 70, 'VRChat Face Tracking executable or wrapper.', NULL, NULL),

('app', 'VRCVideoCacher', 'utility', 'any', 'steam_app_id', '4296960', 'steam_app', NULL, '4296960', NULL, 40, 'Steam app target for VRCVideoCacher.', NULL, NULL),
('app', 'VRCVideoCacher', 'utility', 'windows', 'filename_contains', 'vrcvideocacher', 'native', NULL, NULL, NULL, 50, 'Native VRCVideoCacher executable.', NULL, NULL),
('app', 'VRCVideoCacher', 'utility', 'linux', 'filename_contains', 'vrcvideocacher', 'native', NULL, NULL, NULL, 50, 'Native VRCVideoCacher executable or wrapper.', NULL, NULL),

('app', 'OyasumiVR', 'utility', 'any', 'steam_app_id', '2538150', 'steam_app', NULL, '2538150', NULL, 50, 'Steam app target for OyasumiVR.', NULL, NULL),
('app', 'OyasumiVR', 'utility', 'windows', 'filename_exact', 'OyasumiVR.exe', 'native', NULL, NULL, NULL, 60, 'Native OyasumiVR executable on Windows.', NULL, NULL),
('app', 'OyasumiVR', 'utility', 'linux', 'filename_contains', 'oyasumivr', 'native', NULL, NULL, NULL, 60, 'Native OyasumiVR executable or wrapper on Linux.', NULL, NULL),

('app', 'VRCT', 'utility', 'any', 'filename_contains', 'vrct', 'native', NULL, NULL, NULL, 80, 'VRCT translation tool.', NULL, NULL),

('app', 'Voicemod', 'peripheral', 'windows', 'filename_contains', 'voicemod', 'native', NULL, NULL, NULL, 80, 'Voicemod executable.', NULL, NULL),

('app', 'bHaptics Player', 'peripheral', 'windows', 'filename_contains', 'bhapticsplayer', 'native', NULL, NULL, NULL, 70, 'bHaptics Player executable.', NULL, NULL),
('app', 'bHaptics OSC', 'peripheral', 'any', 'filename_contains', 'bhapticsosc', 'native', NULL, NULL, NULL, 70, 'bHaptics OSC bridge executable.', NULL, NULL),

('app', 'BiteTech', 'peripheral', 'any', 'filename_contains', 'bitetech', 'native', NULL, NULL, NULL, 80, 'BiteTech executable.', NULL, NULL),

('app', 'UDCAP Driver', 'peripheral', 'windows', 'filename_contains', 'udcap', 'native', NULL, NULL, NULL, 80, 'UDCAP driver or support executable.', NULL, NULL),
('app', 'UDCAP Driver', 'peripheral', 'linux', 'filename_contains', 'udcap', 'native', NULL, NULL, NULL, 80, 'UDCAP driver or support executable.', NULL, NULL),

('app', 'BrainFlowsIntoVRChat', 'peripheral', 'any', 'path_contains', 'brainflowsintovrchat', 'python', NULL, NULL, NULL, 60, 'BrainFlowsIntoVRChat project path match.', NULL, NULL),

('app', 'oscavmgr', 'peripheral', 'linux', 'filename_exact', 'oscavmgr', 'native', NULL, NULL, NULL, 50, 'OSC avatar manager executable.', NULL, NULL),
('app', 'oscavmgr', 'peripheral', 'windows', 'filename_contains', 'oscavmgr', 'native', NULL, NULL, NULL, 60, 'OSC avatar manager executable.', NULL, NULL),

('app', 'VRCAdvert', 'peripheral', 'any', 'filename_contains', 'vrcadvert', 'native', NULL, NULL, NULL, 60, 'VRCAdvert executable.', NULL, NULL),

('app', 'motoc', 'peripheral', 'any', 'filename_contains', 'motoc', 'native', NULL, NULL, NULL, 90, 'User-provided target. Verify exact executable name later.', NULL, NULL),

-- Creative, capture, and dev tools

('app', 'OBS Studio', 'utility', 'linux', 'filename_exact', 'obs', 'native', NULL, NULL, NULL, 70, 'OBS Studio executable on Linux.', NULL, NULL),
('app', 'OBS Studio', 'utility', 'windows', 'filename_exact', 'obs64.exe', 'native', NULL, NULL, NULL, 70, 'OBS Studio executable on Windows.', NULL, NULL),

('app', 'Unity Editor', 'utility', 'any', 'filename_contains', 'unity', 'native', NULL, NULL, NULL, 100, 'Unity executable or launcher. Broad match, review manually.', NULL, NULL),
('app', 'Blender', 'utility', 'linux', 'filename_exact', 'blender', 'native', NULL, NULL, NULL, 100, 'Blender executable on Linux.', NULL, NULL),
('app', 'Blender', 'utility', 'windows', 'filename_exact', 'blender.exe', 'native', NULL, NULL, NULL, 100, 'Blender executable on Windows.', NULL, NULL),


-- Configs

('config', 'Steam localconfig.vdf', 'config', 'linux', 'filename_exact', 'localconfig.vdf', NULL, 'vdf', NULL, NULL, 10, 'Steam user localconfig.vdf may contain per-app LaunchOptions. Review path to ensure it is under Steam userdata.', NULL, NULL),
('config', 'Steam localconfig.vdf', 'config', 'windows', 'filename_exact', 'localconfig.vdf', NULL, 'vdf', NULL, NULL, 10, 'Steam user localconfig.vdf may contain per-app LaunchOptions. Review path to ensure it is under Steam userdata.', NULL, NULL),

('config', 'Steam app manifest', 'config', 'linux', 'filename_contains', 'appmanifest_', NULL, 'vdf', NULL, NULL, 40, 'Steam app manifest .acf files. Useful for Steam discovery, not usually a profile overwrite target.', NULL, NULL),
('config', 'Steam app manifest', 'config', 'windows', 'filename_contains', 'appmanifest_', NULL, 'vdf', NULL, NULL, 40, 'Steam app manifest .acf files. Useful for Steam discovery, not usually a profile overwrite target.', NULL, NULL),

('config', 'SteamVR settings', 'config', 'linux', 'filename_exact', 'steamvr.vrsettings', NULL, 'json', NULL, NULL, 20, 'SteamVR settings file.', NULL, NULL),
('config', 'SteamVR settings', 'config', 'windows', 'filename_exact', 'steamvr.vrsettings', NULL, 'json', NULL, NULL, 20, 'SteamVR settings file.', NULL, NULL),

('config', 'OpenVR paths', 'config', 'linux', 'filename_exact', 'openvrpaths.vrpath', NULL, 'json', NULL, NULL, 30, 'OpenVR runtime path configuration.', NULL, NULL),
('config', 'OpenVR paths', 'config', 'windows', 'filename_exact', 'openvrpaths.vrpath', NULL, 'json', NULL, NULL, 30, 'OpenVR runtime path configuration.', NULL, NULL),

('config', 'WiVRn config', 'config', 'linux', 'path_contains', 'wivrn', NULL, 'unknown', NULL, NULL, 20, 'WiVRn related config file or directory match.', 'LVRA Wiki', 'https://wiki.vronlinux.org/'),
('config', 'WayVR config', 'config', 'linux', 'path_contains', 'wayvr', NULL, 'unknown', NULL, NULL, 30, 'WayVR related config file or directory match.', NULL, NULL),
('config', 'Monado config', 'config', 'linux', 'path_contains', 'monado', NULL, 'unknown', NULL, NULL, 40, 'Monado related config file.', 'LVRA Wiki', 'https://wiki.vronlinux.org/'),
('config', 'Envision config', 'config', 'linux', 'path_contains', 'envision', NULL, 'unknown', NULL, NULL, 50, 'Envision related config file.', 'LVRA Wiki', 'https://wiki.vronlinux.org/'),
('config', 'XRizer config', 'config', 'linux', 'path_contains', 'xrizer', NULL, 'unknown', NULL, NULL, 45, 'XRizer related config file.', 'LVRA Wiki', 'https://wiki.vronlinux.org/'),
('config', 'OpenComposite config', 'config', 'linux', 'path_contains', 'opencomposite', NULL, 'unknown', NULL, NULL, 45, 'OpenComposite related config file.', 'LVRA Wiki', 'https://wiki.vronlinux.org/'),
('config', 'ALVR config', 'config', 'linux', 'path_contains', 'alvr', NULL, 'unknown', NULL, NULL, 40, 'ALVR related config file.', 'LVRA Wiki', 'https://wiki.vronlinux.org/'),
('config', 'ALVR config', 'config', 'windows', 'path_contains', 'alvr', NULL, 'unknown', NULL, NULL, 40, 'ALVR related config file.', NULL, NULL),
('config', 'ALXR config', 'config', 'linux', 'path_contains', 'alxr', NULL, 'unknown', NULL, NULL, 45, 'ALXR related config file.', 'LVRA Wiki', 'https://wiki.vronlinux.org/'),
('config', 'ALXR config', 'config', 'windows', 'path_contains', 'alxr', NULL, 'unknown', NULL, NULL, 45, 'ALXR related config file.', NULL, NULL),

('config', 'VRCOSC config', 'config', 'any', 'path_contains', 'vrcosc', NULL, 'unknown', NULL, NULL, 60, 'VRCOSC related config file.', NULL, NULL),
('config', 'VRCX config', 'config', 'any', 'path_contains', 'vrcx', NULL, 'unknown', NULL, NULL, 70, 'VRCX related config file.', NULL, NULL),
('config', 'VRChat Face Tracking config', 'config', 'any', 'path_contains', 'vrchatfacetracking', NULL, 'unknown', NULL, NULL, 70, 'VRChat Face Tracking related config file.', NULL, NULL),
('config', 'VRCVideoCacher config', 'config', 'any', 'path_contains', 'vrcvideocacher', NULL, 'unknown', NULL, NULL, 50, 'VRCVideoCacher related config file.', NULL, NULL),
('config', 'OyasumiVR config', 'config', 'any', 'path_contains', 'oyasumivr', NULL, 'unknown', NULL, NULL, 60, 'OyasumiVR related config file.', NULL, NULL),
('config', 'VRCT config', 'config', 'any', 'path_contains', 'vrct', NULL, 'unknown', NULL, NULL, 80, 'VRCT related config file.', NULL, NULL),
('config', 'Voicemod config', 'config', 'windows', 'path_contains', 'voicemod', NULL, 'unknown', NULL, NULL, 80, 'Voicemod related config file.', NULL, NULL),
('config', 'bHaptics config', 'config', 'any', 'path_contains', 'bhaptics', NULL, 'unknown', NULL, NULL, 70, 'bHaptics related config file.', NULL, NULL),
('config', 'BiteTech config', 'config', 'any', 'path_contains', 'bitetech', NULL, 'unknown', NULL, NULL, 80, 'BiteTech related config file.', NULL, NULL),
('config', 'UDCAP config', 'config', 'any', 'path_contains', 'udcap', NULL, 'unknown', NULL, NULL, 80, 'UDCAP related config file.', NULL, NULL),
('config', 'BrainFlowsIntoVRChat config', 'config', 'any', 'path_contains', 'brainflowsintovrchat', NULL, 'unknown', NULL, NULL, 70, 'BrainFlowsIntoVRChat project config or script folder.', NULL, NULL),
('config', 'oscavmgr config', 'config', 'any', 'path_contains', 'oscavmgr', NULL, 'unknown', NULL, NULL, 60, 'oscavmgr related config file.', NULL, NULL),
('config', 'VRCAdvert config', 'config', 'any', 'path_contains', 'vrcadvert', NULL, 'unknown', NULL, NULL, 60, 'VRCAdvert related config file.', NULL, NULL),
('config', 'motoc config', 'config', 'any', 'path_contains', 'motoc', NULL, 'unknown', NULL, NULL, 90, 'motoc related config file.', NULL, NULL),

('config', 'wlx-overlay config', 'config', 'linux', 'path_contains', 'wlx', NULL, 'unknown', NULL, NULL, 70, 'wlx overlay related config file.', 'LVRA Wiki', 'https://wiki.vronlinux.org/'),
('config', 'Virtual Desktop config', 'config', 'windows', 'path_contains', 'virtual desktop', NULL, 'unknown', NULL, NULL, 50, 'Virtual Desktop related config file.', NULL, NULL),
('config', 'Steam Link config', 'config', 'any', 'path_contains', 'steamlink', NULL, 'unknown', NULL, NULL, 80, 'Steam Link related config file.', NULL, NULL),

('config', 'OBS Studio config', 'config', 'linux', 'path_contains', 'obs-studio', NULL, 'unknown', NULL, NULL, 80, 'OBS Studio config directory on Linux.', NULL, NULL),
('config', 'OBS Studio config', 'config', 'windows', 'path_contains', 'obs-studio', NULL, 'unknown', NULL, NULL, 80, 'OBS Studio config directory on Windows.', NULL, NULL);