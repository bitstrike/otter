# Otter Window Switcher

A sleek window switcher for GTK based window managers that appears when you move your mouse to the top of the screen.

## Features

- **Mouse-activated**: Move your mouse to the top of the screen (y=0) to activate
- **Multi-monitor support**: Works across multiple monitors, appearing on the monitor where your cursor is located
- **Smart positioning**: The window appears near your mouse cursor, ensuring full visibility
- **Edge-aware positioning**: Automatically adjusts position when near monitor edges
- **Top-edge positioning**: Window appears flush with the top edge of the monitor (y=0)
- **Race condition handling**: Properly handles timing between thumbnail generation and window positioning
- **Flickering prevention**: 500ms cooldown period prevents window flickering when mouse remains at y=0
- **Fancy title bar**: Beautiful gradient title bar with otter emoji (🦦) and app branding
- **High-quality thumbnails**: Shows crisp previews of your open windows with background caching
- **Isolated window capture**: Captures only the specific window content, not overlapping windows
- **Background screenshot caching**: Periodically captures window screenshots for better thumbnail quality
- **Mouse wheel scrolling**: Scroll through windows with your mouse wheel
  - **Vertical scrolling**: For multi-row layouts (default)
  - **Horizontal scrolling**: For single-row layouts (when `--nrows 1`)
- **Smooth scrolling**: Supports both discrete and smooth (touchpad) scrolling
- **Dynamic window sizing**: Automatically adjusts window width to show all columns
- **Persistent window**: Stays visible while mouse is inside the window area
- **Mouse-only interaction**: No keyboard shortcuts needed
- **Auto-hide**: Automatically hides when mouse moves away from both top area and window
- **System filtering**: Only shows user applications, not system windows

## Requirements

### System Dependencies (Ubuntu/Debian)
```bash
sudo apt-get install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-wnck-3.0
```

### Other Distributions
- **Fedora/RHEL**: `sudo dnf install python3-gobject gtk3-devel libwnck3-devel`
- **Arch Linux**: `sudo pacman -S python-gobject gtk3 libwnck3`

## Installation

1. Clone or download the files
2. Install system dependencies (see above)
3. Make the script executable: `chmod +x otter.py`

## Usage

### Running Otter
```bash
python3 otter.py
```

The application will run in the background. To activate the window switcher:

1. **Move your mouse to the top of the screen** (y=0)
2. The window switcher will appear under your cursor
3. **Click on any window thumbnail** to switch to that window
4. **Move mouse away** to close
5. **Use mouse wheel** to scroll through many windows (vertical for multi-row, horizontal for single-row)

**Note:** When you click a thumbnail, the window switcher stays visible until you move your mouse away (respecting the `--delay` setting).

### Command Line Options

You can customize the layout and appearance using command line arguments:

```bash
# Use default settings (4 columns, auto rows)
python3 otter.py

# 5 columns, auto rows
python3 otter.py --ncols 5

# 2 rows, auto columns
python3 otter.py --nrows 2

# Larger thumbnails (200px width)
python3 otter.py --xsize 200

# 6 columns, smaller thumbnails
python3 otter.py --ncols 6 --xsize 120

# Disable title bar to save space
python3 otter.py --notitle

# Add delay before hiding
python3 otter.py --delay 1000

# Combine options
python3 otter.py --notitle --delay 500 --ncols 3

# Show help
python3 otter.py --help
```

#### Available Options

- `--nrows NUM`: Number of rows of application thumbnails (auto-calculates columns)
- `--ncols NUM`: Number of columns of application thumbnails (auto-calculates rows, default: 4)  
- `--xsize PIXELS`: Width in pixels for application thumbnails (height auto-calculated, default: 160)
- `--notitle`: Disable the fancy title bar to save screen space
- `--delay MILLISECONDS`: Delay in milliseconds before hiding the window (default: 0)

**Note:** `--nrows` and `--ncols` are mutually exclusive. Specify only one of them. 
```

## How It Works

1. **Background monitoring**: Continuously monitors mouse position across all monitors
2. **Multi-monitor detection**: Automatically detects which monitor contains the mouse cursor
3. **Window detection**: Uses Wnck library to detect active windows
4. **Screenshot caching**: Periodically captures high-quality window screenshots in the background
5. **Isolated capture**: Uses multiple methods to capture only the target window content without overlaps
6. **Thumbnail generation**: Uses cached screenshots for crisp thumbnails, falls back to icons or placeholders
6. **Smart filtering**: Excludes system applications and background processes
7. **Responsive UI**: GTK3-based interface with smooth interactions

## Customization

### Command Line Customization

The easiest way to customize the application is through command line arguments:

- **Layout**: Use `--nrows` OR `--ncols` to control the grid layout (mutually exclusive)
- **Thumbnail size**: Use `--xsize` to set the width of thumbnails (height is auto-calculated)
- **Title bar**: Use `--notitle` to disable the fancy title bar and save screen space
- **Hide delay**: Use `--delay` to set a delay before hiding the window

### Code Customization

For advanced customization, you can modify `otter.py`:

- **Trigger sensitivity**: Adjust `y <= 5` in `check_mouse_position()`
- **Window styling**: Modify the CSS in `create_window()`
- **Cache update frequency**: Modify `cache_update_interval` (default: 2000ms)
- **System app filtering**: Update the `system_apps` list

## Troubleshooting

### Common Issues

1. **"Unknown import symbol" errors**: These are false positives from linters - the app will still work
2. **No windows detected**: Make sure you have user applications open
3. **Thumbnails not working**: Falls back to colored placeholders with window names
4. **Mouse detection issues**: Ensure you're moving to the very top edge of the screen
5. **Column visibility issues**: The app automatically adjusts window width to show all columns
6. **Positioning issues**: The app now properly handles race conditions between thumbnail generation and window positioning
7. **Flickering issues**: The app now prevents flickering with a 500ms cooldown period after showing the window

### Debug Mode
Add debug prints to see what's happening:
```python
print(f"Mouse position: {x}, {y}")
print(f"Found {len(windows)} windows")
```

## Architecture

- **OtterWindowSwitcher**: Main application class
- **Mouse monitoring**: Uses GDK to track cursor position
- **Window management**: Uses Wnck for window detection and control
- **UI rendering**: GTK3 with custom CSS styling
- **Thumbnail generation**: Pixbuf-based screenshot capture
- **Dynamic sizing**: Calculates required width based on column count and thumbnail size
- **Smart positioning**: Uses GLib.idle_add to ensure window positioning happens after layout completion
- **Flickering prevention**: Cooldown mechanism prevents window flickering during rapid mouse movements

## License

This project is open source. Feel free to modify and distribute.