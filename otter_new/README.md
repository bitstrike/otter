# Otter Window Switcher - New Implementation

Clean, modular reimplementation of Otter Window Switcher.

## Architecture

### Module Structure (8 files, ~2,600 lines)

```
otter_new/
├── main.py          # Entry point & main application (~350 lines)
├── config.py        # CLI parsing & validation (~200 lines)
├── constants.py     # Colors, defaults, system apps (~70 lines)
├── geometry.py      # Screen/monitor utilities (~200 lines)
├── windows.py       # WindowManager - Wnck operations (~400 lines)
├── screenshots.py   # ScreenshotManager - capture & caching (~350 lines)
├── input.py         # Edge detection, events, shift monitor (~400 lines)
└── ui.py            # UI components, styling (~650 lines)
```

### Key Design Principles

1. **Never store Wnck objects** - Only store XIDs, retrieve windows fresh
2. **Modular separation** - Each file has single responsibility
3. **Clean interfaces** - Managers expose simple APIs
4. **Error resilience** - Graceful degradation on failures
5. **Type hints** - Better IDE support and documentation

## Components

### WindowManager (windows.py)
- Manages Wnck screen lifecycle
- Queries user windows (filters system apps)
- XID-based window lookup (prevents segfaults)
- MRU timestamp tracking
- Fullscreen detection
- Automatic Wnck recreation (prevents corruption)

### ScreenshotManager (screenshots.py)
- High-quality window screenshots
- Two-tier caching (current + last valid)
- Handles minimized windows
- Startup preprocessing with splash
- Automatic cache cleanup

### EdgeDetector (input.py)
- Polls mouse position
- Multi-monitor aware
- Configurable edges (north/south/east/west)
- Main character mode (respects fullscreen)

### ShiftMonitor (input.py)
- Monitors shift key presses
- Temporary hide with configurable duration
- Works with both left and right shift

### EventHandler (input.py)
- Left-click: Activate window
- Middle-click: Switch workspace
- Right-click: Context menu
- Mouse wheel: Scroll
- Enter/leave: Auto-hide

### SwitcherWindow (ui.py)
- Main GTK window
- Grid layout (configurable rows/columns)
- Scrollable container
- Workspace badges
- GTK theme integration
- CSS styling

### ContextMenu (ui.py)
- Move to display
- Resize to display
- Minimize/Maximize
- Switch to workspace
- Move to workspace
- Drag mode

## Usage

```bash
# Run the new implementation
./otter2.py

# Same CLI as original
./otter2.py --south --recent --ncols 6
./otter2.py --list
./otter2.py --help
```

## Improvements Over Original

### Code Quality
- ✅ Modular structure (8 files vs 1 monolith)
- ✅ Type hints throughout
- ✅ Clear separation of concerns
- ✅ Consistent error handling
- ✅ Better logging

### Stability
- ✅ Never stores Wnck objects (prevents segfaults)
- ✅ XID-based window lookup
- ✅ Graceful error handling
- ✅ Resource cleanup

### Maintainability
- ✅ Each module < 700 lines
- ✅ Single responsibility per file
- ✅ Easy to test components
- ✅ Clear interfaces

### Performance
- ✅ Efficient caching
- ✅ Lazy screenshot capture
- ✅ Minimal Wnck calls
- ✅ Smart cache eviction

## Testing

```bash
# Test imports
python3 -c "from otter_new.main import main; print('OK')"

# Test window listing
./otter2.py --list

# Test with debug logging
./otter2.py --debug
```

## Migration from Original

The new implementation is **100% CLI compatible** with the original:

```bash
# All these work identically
./otter.py --south --recent
./otter2.py --south --recent

./otter.py --ncols 6 --xsize 200
./otter2.py --ncols 6 --xsize 200

./otter.py --list
./otter2.py --list
```

## Development

### Adding Features

1. **New window operation**: Add to `ContextMenu` in `ui.py`
2. **New input handler**: Add to `EventHandler` in `input.py`
3. **New screenshot method**: Add to `ScreenshotManager` in `screenshots.py`
4. **New CLI option**: Add to `parse_arguments()` in `config.py`

### Debugging

```bash
# Enable debug logging
./otter2.py --debug

# Check specific module
python3 -c "from otter_new.windows import WindowManager; print('OK')"
```

## File Sizes

```
main.py         ~350 lines  - Application orchestration
ui.py           ~650 lines  - UI components
windows.py      ~400 lines  - Window management
screenshots.py  ~350 lines  - Screenshot handling
input.py        ~400 lines  - Input handling
geometry.py     ~200 lines  - Geometry utilities
config.py       ~200 lines  - Configuration
constants.py    ~70 lines   - Constants
─────────────────────────────
Total:          ~2,620 lines
```

Compare to original: **3,269 lines in one file**

## Known Limitations

- Requires X11 (no Wayland support)
- Requires Wnck 3.0
- GTK 3.0 only

## Future Enhancements

- [ ] Config file support (YAML/TOML)
- [ ] Custom keyboard shortcuts
- [ ] Window grouping by application
- [ ] Search/filter windows
- [ ] Themes/skins
- [ ] Animations
- [ ] Plugin system
