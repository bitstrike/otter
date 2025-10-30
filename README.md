# Otter Window Switcher

A handy mouse-activated window switcher for GTK-based Linux desktop environments. Built with Python, GTK3, and Wnck.

![otter in action](otter.png)

## Features

### Functionality
- **Mouse-activated**: Move your mouse to any screen edge (north/south/east/west) to activate
- **Multi-monitor support**: Works across multiple monitors, appearing on the monitor where your cursor is located
- **Smart positioning**: Window appears near your mouse cursor with intelligent edge detection
- **Context menu**: Right-click on thumbnails for window operations (move, resize, minimize, maximize, workspace management)
- **Middle-click**: Middle-click on thumbnails to switch to the app's workspace without activating the window
- **Drag mode**: Drag windows by moving them with your mouse cursor
- **MRU ordering**: Most Recently Used sorting keeps frequently accessed windows at the front
- **Fullscreen respect**: Optional mode that won't trigger during fullscreen games/videos (--main-character)
- **High-quality thumbnails**: Shows previews of open windows with periodic caching for performance
- **Mouse wheel scrolling**: Scroll through windows with vertical/horizontal mouse wheel
- **Auto-hide**: Automatically hides when mouse moves away
- **Minimized windows**: Shows all windows including minimized ones (with visual distinction)
- **Multi-workspace support**: Move windows between workspaces, switch to window locations
- **Window operations**: Minimize, maximize, move to display, resize to display
- **System filtering**: Only shows user applications, not system windows
- **GTK theme integration**: Automatically follows your system GTK theme colors for a consistent, native appearance

### Technical Features
- **Edge-aware positioning**: Automatically adjusts position when near monitor edges
- **Race condition handling**: Properly handles timing between thumbnail generation and window positioning
- **Flickering prevention**: Cooldown mechanism prevents window flickering
- **Defensive programming**: Comprehensive error handling for long-term stability
- **Wnck state management**: Periodic screen object recreation prevents memory corruption
- **Logging system**: Production-ready logging for debugging and monitoring

## Requirements

### Python Version
- Python 3.6 or higher

### System Dependencies

**Ubuntu/Debian:**
- `python3-gi`
- `python3-gi-cairo`
- `gir1.2-gtk-3.0`
- `gir1.2-wnck-3.0`

**Fedora/RHEL:**
- `python3-gobject`
- `gtk3-devel`
- `libwnck3-devel`

**Arch Linux:**
- `python-gobject`
- `gtk3`
- `libwnck3`

**Note:** All Python modules are from the standard library or system GObject Introspection bindings. No pip packages required! Using pip for GTK/Wnck is not recommended and may cause issues - use your system package manager instead.

## Installation

1. Clone or download the files
2. Install system dependencies using your package manager (see Requirements above)
3. Make the script executable: `chmod +x otter.py`

## Usage

### Basic Usage
```bash
./otter.py
```

The application runs in the background. To activate:

1. **Move your mouse to the top edge** of the screen (default: north)
2. The window switcher appears under your cursor
3. **Click on any thumbnail** to switch to that window
4. **Middle-click on any thumbnail** to switch to that app's workspace without activating it
5. **Right-click** for context menu with window operations
6. **Mouse wheel** to scroll through windows
7. **Move mouse away** to auto-hide

### Command Line Options

```bash
# Basic examples
./otter.py                              # Default: north edge, 4 columns
./otter.py --south                      # Trigger on bottom edge
./otter.py --east                       # Trigger on right edge
./otter.py --west                       # Trigger on left edge

# Layout customization
./otter.py --ncols 6                    # 6 columns, auto rows
./otter.py --nrows 2                    # 2 rows, auto columns
./otter.py --xsize 200                  # Larger thumbnails (200px width)
./otter.py --notitle                    # Disable title bar

# Advanced features
./otter.py --recent                     # MRU ordering (most recent first)
./otter.py --main-character             # Don't trigger during fullscreen apps
./otter.py --delay 500                  # 500ms delay before hiding

# Combined example (gaming setup)
./otter.py --east --ncols 6 --notitle --recent --main-character

# Show help
./otter.py --help
```

#### Available Options

**Layout Options** (mutually exclusive):
- `--nrows NUM`: Number of rows (auto-calculates columns)
- `--ncols NUM`: Number of columns (auto-calculates rows, default: 4)

**Appearance Options**:
- `--xsize PIXELS`: Thumbnail width in pixels (height auto-calculated, default: 160)
- `--notitle`: Disable the fancy title bar to save screen space

**Behavior Options**:
- `--delay MILLISECONDS`: Delay before hiding the window (default: 0)
- `--recent`: Order thumbnails by most recently used (MRU)
- `--main-character`: Disable edge trigger when fullscreen app is active (gaming mode)

**Edge Trigger Options** (mutually exclusive):
- `--north`: Trigger at top edge (default)
- `--south`: Trigger at bottom edge
- `--east`: Trigger at right edge (recommended for gaming)
- `--west`: Trigger at left edge

**Notes:**
- `--nrows` and `--ncols` are mutually exclusive - specify only one
- Edge trigger options are mutually exclusive - specify only one
- `--delay` may cause minor visual flickering on hide
- `--main-character` prevents interrupting games like Minecraft when in fullscreen

## Context Menu Features

Right-click on any window thumbnail to access:

- **Move to Current Display**: Move window to the monitor where your cursor is
- **Resize to Current Display**: Resize window to fit the current monitor
- **Minimize**: Minimize the window
- **Maximize**: Maximize the window
- **Switch to App**: Jump to the window's workspace/display and activate it
- **Go to App's Workspace**: Switch to the app's workspace without activating the window (same as middle-click)
- **Move to Workspace**: Submenu to move window to specific workspace
- **Drag App**: Enter drag mode - window follows your cursor until clicked

## Customization

### Command Line Customization

The easiest way to customize is through command line arguments:

- **Edge trigger**: Use `--north`, `--south`, `--east`, or `--west`
- **Layout**: Use `--nrows` OR `--ncols` to control grid layout
- **Thumbnail size**: Use `--xsize` to set thumbnail width
- **Title bar**: Use `--notitle` to disable for minimal appearance
- **Hide delay**: Use `--delay` to set auto-hide delay
- **MRU ordering**: Use `--recent` for smart window ordering
- **Gaming mode**: Use `--main-character` to respect fullscreen apps

### Code Customization

For advanced customization, modify `otter.py`:

- **Trigger sensitivity**: Adjust `<= 5` in edge detection code (line ~256)
- **Window styling**: Modify CSS in `create_window()` (line ~524)
- **Cache update frequency**: Modify `cache_update_interval` (default: 2000ms, line ~174)
- **System app filtering**: Update `system_apps` list (line ~757)
- **Wnck recreation interval**: Modify `wnck_recreation_interval` (default: 3600s, line ~166)

## Debug Mode

For detailed debugging, use the debug wrappers:

```bash
# Simple debug logging
./debug_otter_simple.py --east --ncols 6 --notitle --recent

# Ultra-verbose logging (generates large logs)
./debug_otter_verbose.py --east --ncols 6 --notitle --recent
```

Debug logs are saved to `otter_debug_*.log` files with timestamps.

## Version History

- **v2.0.0**: Complete refactoring with bug fixes, logging, defensive programming
- **v2.1.0**: Added MRU ordering (--recent)
- **v2.2.0**: Added fullscreen detection (--main-character)
- **v2.3.0**: Periodic Wnck recreation for long-term stability
- **v2.4.0**: GTK theme support, middle-click workspace switching, HIDE_STATE semaphore

## License

This project is licensed under the GNU General Public License v3.0 (GPL-3.0).

```
Otter Window Switcher - Mouse-activated window switcher for Linux
Copyright (C) 2025

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
```

---

**Tip**: For gaming setups, try: `./otter.py --east --main-character --recent --notitle`

This positions the trigger on the right edge (away from game UI), respects fullscreen mode, orders windows by recent use, and saves screen space.
