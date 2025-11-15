# Shift Key Detection Tests

This directory contains test programs to verify shift key detection functionality.

## Test Programs

### 1. simple_shift_test.py
**Purpose:** Minimal test to verify Keybinder3 is working on your system

**Usage:**
```bash
python3 tests/simple_shift_test.py
```

**What it does:**
- Imports and initializes Keybinder3
- Binds both shift keys
- Prints a message every time you press a shift key
- Press Ctrl+C to exit

**Expected output:**
```
Starting shift key test...
✓ Imports successful
✓ GTK initialized
✓ Keybinder initialized

Binding shift keys...
Left shift bound: True
Right shift bound: True

==================================================
Press shift keys now (Ctrl+C to exit)
==================================================

>>> SHIFT KEY DETECTED: <Shift_L>
>>> SHIFT KEY DETECTED: <Shift_R>
```

### 2. test_shift_key.py
**Purpose:** Full-featured test with press/release detection

**Usage:**
```bash
python3 tests/test_shift_key.py
```

**What it does:**
- Tests both shift key press and release detection
- Uses polling to detect when shift is released
- Counts total presses and releases
- Shows summary on exit

**Expected output:**
```
============================================================
Shift Key Detection Test Program
============================================================

This program tests Keybinder3 shift key detection.
Press Ctrl+C to exit.

✓ GTK initialized
✓ Keybinder initialized

Binding shift keys...
✓ Left shift key bound
✓ Right shift key bound

============================================================
Ready! Press shift keys to test detection.
Press Ctrl+C to exit.
============================================================

🔽 SHIFT DOWN (press #1) - Key: <Shift_L>
🔼 SHIFT RELEASE (release #1)
🔽 SHIFT DOWN (press #2) - Key: <Shift_R>
🔼 SHIFT RELEASE (release #2)
```

## Troubleshooting

### Keybinder3 not available
If you get an import error, install Keybinder3:
```bash
sudo apt install gir1.2-keybinder-3.0
```

### Segmentation fault or "cannot register existing type 'GdkDisplayManager'"
This happens when GTK version is not specified before importing. The tests have been fixed to require GTK 3.0 explicitly, which is required by Keybinder3.

**The fix:** Always call `gi.require_version('Gtk', '3.0')` BEFORE importing from `gi.repository`.

### No shift keys detected
1. Make sure you're running on X11 (not Wayland)
2. Check if another application is capturing shift keys
3. Try running with sudo (some systems require elevated permissions for global hotkeys)

### Shift detection works in tests but not in otter.py
1. Check that otter.py is printing the shift messages to stdout
2. Look for "Keybinder initialized successfully" in the logs
3. Verify the window is visible when you press shift (shift only hides visible windows)

## Integration with Otter

The shift key detection in otter.py works as follows:
1. When otter window is visible and you press shift → window hides
2. When you release shift → window shows again
3. If window is not visible, shift key does nothing

To see shift detection messages in otter.py, look for:
- `🔽 SHIFT DOWN - <Shift_L>` or `<Shift_R>`
- `🔼 SHIFT RELEASE`
- `→ Hiding window` / `→ Showing window`
