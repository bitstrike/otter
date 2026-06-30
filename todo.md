# Otter TODO

## Signal Handler Accumulation (Performance Degradation)

After running for days, mouseover highlight becomes noticeably delayed.

**Root cause:** `recreate_wnck_screen()` connects `window-opened`/`window-closed` signals to the same singleton screen object without disconnecting previous handlers. After N recreations, each window event fires the callback N times.

**Fix:**
1. Store handler IDs from `connect()` in `_initialize_wnck()`
2. Call `disconnect()` on stored IDs before reconnecting in `recreate_wnck_screen()`

**Secondary factors:**
- `window_is_valid()` iterates full window list per window — O(n²) in `_populate_windows()`
- `Gtk.events_pending()` busy-loop in `_force_window_resize()` adds latency
- Screenshot cache growth if `update_cache` misses cycles while visible


## Overlay Eating Button Click Events

- [x] Gtk.Overlay in thumbnail button intercepts left-click before it reaches the parent Gtk.Button
- [x] Fix: handle button==1 in `on_button_press` so clicks on the overlay/image area still trigger window activation


## Performance Fixes

- [x] Signal handler accumulation: store handler IDs, disconnect before reconnect in `recreate_wnck_screen()`
- [x] O(n^2) in `get_window_by_xid()`: skip `window_is_valid()` per candidate, just match XID directly
- [x] O(n^2) in `populate()`: remove per-window `get_window_by_xid()` re-validation (already validated in `get_user_windows()`)
- [x] Remove `Gtk.events_pending()` busy-loop from `_force_window_resize()`
- [x] Remove blocking `time.sleep(0.2)` calls in `recreate_wnck_screen()`
- [x] Redundant `window_is_valid()` double-call in `get_screenshot()`
- [x] SYSTEM_APPS list rebuilt as lowercase list each iteration - pre-build a frozen set

## Dead Code Removal

- [x] Unreachable second `return False` in `_activate_window_after_switch()`
- [x] `get_all_monitors()` in geometry.py (never called)
- [x] `DEFAULT_CONFIG` in constants.py (never referenced)
- [x] `CACHE_UPDATE_INTERVAL` in constants.py (hardcoded 5000 in main.py instead)
- [x] `get_window_id()` in windows.py (trivial wrapper, only caller can use `window.get_xid()` directly)

## Icon Pixbuf Copy Allocation

- [ ] `raw_icon.copy()` in `get_user_windows()` allocates a new 48x48 RGBA pixbuf per window on every call. Cache icons by XID and only re-copy when the window list membership changes.
