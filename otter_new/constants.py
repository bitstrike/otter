"""Constants and default values"""

# Workspace color palette (supports up to 10 workspaces)
WORKSPACE_COLORS = [
    "#E74C3C",  # 1: Red
    "#27AE60",  # 2: Green
    "#2980B9",  # 3: Blue
    "#F39C12",  # 4: Orange
    "#8E44AD",  # 5: Purple
    "#16A085",  # 6: Dark Teal
    "#C0392B",  # 7: Dark Red
    "#D35400",  # 8: Dark Orange
    "#2C3E50",  # 9: Dark Blue-Gray
    "#E67E22",  # 10: Burnt Orange
]

# System applications to filter out
SYSTEM_APPS = [
    'gnome-shell',
    'cinnamon',
    'gnome-settings-daemon',
    'gnome-panel',
    'mate-panel',
    'xfce4-panel',
    'plasma-desktop',
    'kwin',
    'compiz',
    'metacity',
    'mutter',
    'unity',
    'unity-panel-service',
    'Desktop',
    'Otter Window Switcher',
]

# Default configuration
DEFAULT_CONFIG = {
    'nrows': None,
    'ncols': 4,
    'xsize': 160,
    'show_title': True,
    'hide_delay': 0,
    'hide_duration': 0,
    'north': True,
    'south': False,
    'east': False,
    'west': False,
    'recent': False,
    'main_character': False,
    'ignore_list': [],
}

# Performance tuning
EDGE_TRIGGER_THRESHOLD = 5  # pixels
MOUSE_POLL_INTERVAL = 100   # milliseconds
CACHE_UPDATE_INTERVAL = 5000  # milliseconds
MAX_CACHE_SIZE = 100  # screenshots

# Wnck management
WNCK_RECREATION_INTERVAL = 3600  # 1 hour
WNCK_MAX_CALLS = 10000
WNCK_GRACE_PERIOD = 2.0  # seconds after recreation
