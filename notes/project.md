# Otter Project Overview

## What is Otter?

**Otter** is a sophisticated X11 Window Switcher application for Linux desktop environments (Ubuntu Cinnamon and GTK-based desktops). It's a background application that displays high-quality window thumbnails when the user moves their cursor to a configurable screen edge.

### Location
- **Main File:** `/home/src/otter/otter.py`
- **Size:** 3,137 lines of Python code

## Key Features

- **Edge-triggered window switcher** - Shows thumbnails when cursor reaches a screen edge (north, south, east, or west)
- **High-quality thumbnails** - Captures and caches window screenshots for quick access
- **Shift key timed hide** - Press shift to temporarily hide window for configurable duration (see `--hide` option)
- **Advanced window operations** - Right-click context menus for:
  - Move window between displays
  - Resize to display
  - Minimize/Maximize
  - Switch to window/workspace
  - Move to different workspace
  - Drag mode for interactive repositioning
- **Multi-monitor support** - Intelligently positions windows across displays
- **Smart filtering** - Respects fullscreen applications (games/videos) and filters system windows
- **MRU ordering** - Most recently used windows appear first
- **Auto-hide** - Automatically hides when mouse leaves the window
- **Workspace support** - Visual color badges indicating window workspaces

## Technical Architecture

### Main Component
- **Primary Class:** `OtterWindowSwitcher` - Single monolithic class that encapsulates all functionality

### Key Subsystems

#### Window Management
- Window retrieval and validation
- Wnck screen recreation (every 2 hours to prevent corruption)
- Safe window lookups by X11 window ID

#### Mouse & Edge Detection
- Background mouse position monitoring
- Screen edge triggers
- Fullscreen detection

#### Screenshot & Thumbnail Handling
- High-quality window screenshot capture
- Screenshot caching (100-window limit)
- Isolated window capture
- Thumbnail scaling with quality preservation
- Workspace badge creation

#### UI & Display
- GTK-based window switcher popup
- Thumbnail widget creation
- Window positioning at screen edges
- Startup splash screen with progress
- Pre-processing of thumbnails on startup

#### Event Handling
- Mouse click, scroll, and position events
- Window open/close notifications
- Context menu operations
- Signal handling (SIGINT, SIGTERM)

## Dependencies

### System Requirements
- **Python:** 3.6+
- **Platform:** X11-only (no Wayland support)

### GTK/GUI Libraries (GObject Introspection)
- GTK 3.0 or 4.0
- Wnck (Window Navigator Construction Kit) 3.0
- GdkPixbuf
- Cairo

### System Packages
- `python3-gi` - GObject Introspection bindings
- `python3-gi-cairo` - Cairo support
- `gir1.2-gtk-3.0` - GTK 3.0 bindings
- `gir1.2-wnck-3.0` - Wnck 3.0 bindings

### Standard Library
- `os`, `sys`, `signal`, `argparse`, `time`, `threading`, `logging`, `typing`, `colorsys`

## Implementation Notes

- **Thread Safety:** Wnck access is protected via RLock (`self.wnck_lock`)
- **Performance:** Screenshot caching with periodic updates
- **Robustness:** Wnck screen recreation mechanism prevents library corruption
- **Configurability:** Extensive command-line arguments and config options
- **Version Support:** Handles both GTK 3.0 and 4.0 with fallback mechanisms

## Window Visibility State Machine

The otter window visibility is determined by a sophisticated state machine running a mouse position check every 100ms via `GLib.timeout_add()` in `setup_mouse_monitoring()` (line 311).

### Core State Variables

1. **`self.is_visible`** - Boolean flag indicating if window is currently displayed
2. **`self.HIDE_STATE`** - Semaphore (boolean) preventing hiding during critical operations
3. **`self._middle_click_mode`** - Flag for middle-click workspace switching workflow
4. **`self.window_clicked`** - Tracks if a window thumbnail was clicked

### Mouse Monitoring Loop

**`check_mouse_position()`** (lines 490-552) runs every 100ms and has two states:

#### Window Hidden State
Checks if mouse is within **5 pixels** of screen edge:
- **North (top):** `y - monitor_y <= 5`
- **South (bottom):** `monitor_y + monitor_height - y <= 5`
- **East (right):** `monitor_x + monitor_width - x <= 5`
- **West (left):** `x - monitor_x <= 5`

If edge triggered → calls `show_window()` (line 1932)
- Special case: Ignores trigger if fullscreen app active and `--main-character` enabled

#### Window Visible State
Checks if mouse moved away from edge:
```
Mouse > 100 pixels from edge AND not inside window → trigger hide
```

If conditions met → calls `hide_window()` with appropriate delay

### HIDE_STATE Semaphore

**Purpose:** Prevents unwanted window hiding during critical user interactions

**Mechanism:**
- **Value `True`** (normal): Window can hide normally
- **Value `False`** (protected): Hiding is blocked - `hide_window()` and `_do_hide()` return early

**When Set to False:**
- **Context Menu Opens** (line 2350): `show_context_menu()` sets `HIDE_STATE = False`

**When Restored to True:**
- **Context Menu Closes** (line 2419): `on_context_menu_closed()` sets `HIDE_STATE = True`

**Why It's Needed:** Without it, the window could hide while user interacts with context menu, causing poor UX.

### Event Handlers

**`on_leave_notify()`** (line 2184) - Mouse leaves window:
- Middle-click mode: 300ms+ delay before hide
- Window was clicked: Uses configured `hide_delay`
- Otherwise: 300ms minimum delay (prevents flicker)

**`on_enter_notify()`** (line 2209) - Mouse enters window:
- Resets `window_clicked` flag
- Window stays visible

**`on_button_press_event()`** (line 2276) - Handles mouse clicks:
- Right-click: Opens context menu (sets `HIDE_STATE = False`)
- Middle-click: Enters workspace switch mode (sets `_middle_click_mode = True`)

### Show/Hide Implementation

**`show_window()`** (line 1888):
1. Validates Wnck state
2. Populates window list
3. Displays GTK window via `window.show_all()`
4. Positions at triggered edge via `_position_window()`
5. Grabs keyboard focus
6. Sets `is_visible = True`

**`_position_window()`** (line 1934):
- **North:** Positions at top of monitor
- **South:** Positions at bottom of monitor
- **East:** Positions at right of monitor
- **West:** Positions at left of monitor

**`hide_window()`** (line 1999):
1. Checks `HIDE_STATE` - returns if False (protected)
2. Schedules `_do_hide()` with optional delay or calls immediately

**`_do_hide()`** (line 2014):
1. Checks `HIDE_STATE` - returns if False (protected)
2. Calls `window.hide()`
3. Sets `is_visible = False`

**`delayed_hide()`** (line 2232):
- Hides after delay with mouse position validation
- Creates 10-pixel buffer zone around window
- Only hides if mouse is outside buffered area

### Visibility State Flow

```
HIDDEN STATE (is_visible = False)
    ↓
[Check Mouse Position Every 100ms]
    ↓
[Mouse at Edge? (5px threshold)]
    ↓
YES → show_window()
    ├─ is_visible = True
    ├─ Position at edge
    └─ Populate windows
    ↓
VISIBLE STATE (is_visible = True)
    ↓
[Check Mouse Position Every 100ms]
    ↓
[Mouse moved 100px away AND not in window?]
    ↓
YES → Check HIDE_STATE semaphore
    ├─ If False (menu/context active): STAY VISIBLE
    └─ If True: Hide with delay
        ├─ delayed_hide() with 300ms+ delay
        ├─ Validates mouse position before hiding
        └─ is_visible = False
    ↓
HIDDEN STATE
```

### Protection Mechanisms

The `HIDE_STATE` semaphore prevents unwanted hiding in these scenarios:

1. **Context Menu Active**
   - Set to `False` when menu opens (line 2350)
   - Restored to `True` when menu closes (line 2419)
   - Prevents accidental hide while user interacts with menu

2. **Hide Operation Validation**
   - Both `hide_window()` and `_do_hide()` check semaphore
   - Prevents hiding if any protected operation is in progress

3. **Middle-Click Workflow**
   - Special handling in `on_leave_notify()` to extend delays
   - Minimum 300ms delay to prevent flicker during workspace switch

### Configuration Parameters

- **`hide_delay`**: Configurable delay (ms) before hiding after mouse leaves (default: 0)
  - Minimum 300ms enforced in certain scenarios to prevent flicker
- **`hide_duration`**: Duration (seconds) to hide window when shift key is pressed (default: 0 = disabled)
  - Enabled via `--hide X` command line argument
  - Supports decimal values (e.g., 2.5 seconds)
  - Range: 0 to 60 seconds
- **Edge Selection**: `north`, `south`, `east`, or `west` (default: `north`)
- **`main_character`**: When enabled, respects fullscreen applications

## Shift Key Timed Hide Feature

### Overview
Allows user to temporarily hide the Otter window by pressing shift, making it reappear after a configurable duration.

### Implementation
- **Detection Method:** GTK key-press-event handlers
- **Supported Keys:** Shift_L (left shift) and Shift_R (right shift)
- **State Variable:** `self.shift_hidden` - tracks if window is hidden by shift key
- **Configuration:** `--hide X` command line argument (X = seconds)

### Key Methods

**`setup_shift_key_monitoring()`** (line ~2891):
- Checks if `hide_duration > 0` (feature enabled)
- Connects `key-press-event` to `_on_key_press()` handler
- Logs monitoring status

**`_on_key_press(widget, event)`** (line ~2909):
- Detects shift key press via `Gdk.keyval_name(event.keyval)`
- Checks for 'Shift_L' or 'Shift_R'
- Hides window immediately with `self.window.hide()`
- Sets `self.shift_hidden = True`
- Schedules timeout: `GLib.timeout_add(duration_ms, _shift_hide_timeout)`

**`_shift_hide_timeout()`** (line ~2930):
- Called after hide duration expires
- Shows window with `self.window.show_all()`
- Sets `self.shift_hidden = False`
- Returns `False` (don't repeat)

### Event Flow
```
[Shift key pressed while window visible]
    ↓
_on_key_press() triggered
    ├─ Check keyname == 'Shift_L' or 'Shift_R'
    ├─ Hide window immediately
    ├─ Set shift_hidden = True
    └─ Schedule timeout (duration_ms)
    ↓
[Wait X seconds]
    ↓
_shift_hide_timeout() triggered
    ├─ Show window
    ├─ Set shift_hidden = False
    └─ Return False
```

### Requirements
- Window must have focus for key events (auto-focuses when shown)
- Feature disabled by default (`--hide 0` or not specified)
- Works with both left and right shift keys

### Technical Notes
- **Why GTK Events?** Keybinder3 cannot bind modifier keys directly
- **Why Not Polling?** Gdk modifier flags have timing issues (delayed by one event)
- **Solution:** GTK key events detect actual key names, not modifier state

### Related Files
- `SHIFT_KEY_FEATURE.md` - User-facing feature documentation
- `tests/test_shift_events.py` - Test program for shift detection
- `tests/test_timed_hide.md` - Testing guide

## Related Files
- `debug_otter.py`, `debug_otter_simple.py`, `debug_otter_verbose.py` - Debug/testing variants
- `tests/` - Unit test suite
- `README.md` - Comprehensive project documentation
- `SHIFT_KEY_FEATURE.md` - Shift key timed hide documentation
