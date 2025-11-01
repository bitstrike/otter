#!/usr/bin/env python3

"""
Otter - X11 Window Switcher for Ubuntu Cinnamon Desktop
A background application that shows active windows when mouse cursor is moved to screen edge
"""

# Suppress accessibility bus warnings (harmless)
import os
os.environ['NO_AT_BRIDGE'] = '1'

# Otter - X11 Window Switcher for Ubuntu Cinnamon Desktop
import gi
import logging
import sys
import signal
import argparse
import time
import threading
from typing import List, Dict, Optional, Tuple
import colorsys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Detect and set GTK version BEFORE any imports
# IMPORTANT: Wnck 3.0 requires GTK 3.0, so we need to check compatibility
gtk_version = None

# First, try to load Wnck to see what GTK version it requires
try:
    gi.require_version("Wnck", "3.0")
    # Wnck 3.0 is available - it requires GTK 3.0
    gi.require_version("Gtk", "3.0")
    gtk_version = "3.0"
    logger.info("Using GTK 3.0 (required by Wnck 3.0)")
except ValueError as e:
    # Wnck 3.0 not available or incompatible
    logger.warning(f"Wnck 3.0 setup failed: {e}")
    try:
        # Try alternative setup with GTK 4.0 and older Wnck
        gi.require_version("Gtk", "4.0")
        gi.require_version("Wnck", "3.0")
        gtk_version = "4.0"
        logger.info("Using GTK 4.0 with Wnck")
    except ValueError:
        try:
            # Fallback: GTK 3.0 only
            gi.require_version("Gtk", "3.0")
            try:
                gi.require_version("Wnck", "3.0")
            except ValueError:
                logger.warning("Wnck not available, proceeding without window management")
            gtk_version = "3.0"
            logger.info("Using GTK 3.0")
        except ValueError:
            logger.error("Neither GTK 4.0 nor GTK 3.0 available")
            sys.exit(1)

# Import after versions are set
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf

# Try to import Wnck (may not be available)
try:
    from gi.repository import Wnck
    WNCK_AVAILABLE = True
except ImportError:
    logger.warning("Wnck not available - window management features disabled")
    Wnck = None
    WNCK_AVAILABLE = False

try:
    from gi.repository import GdkX11
    WAYLAND_SUPPORT = False
except ImportError:
    GdkX11 = None
    logger.info("GdkX11 not available - Wayland compatibility mode enabled")
    WAYLAND_SUPPORT = True

# Suppress accessibility warnings if available
try:
    os.environ['NO_AT_BRIDGE'] = '1'
except Exception:
    pass

class OtterWindowSwitcher:
    # Workspace color palette (supports up to 10 workspaces with distinct colors)
    # Colors are vibrant and highly distinct for quick visual scanning
    # Chosen to maximize contrast and avoid confusion between adjacent workspaces
    WORKSPACE_COLORS = [
        "#E74C3C",  # 1: Red (bright, high contrast)
        "#27AE60",  # 2: Green (distinct from red)
        "#2980B9",  # 3: Blue (distinctly different from green)
        "#F39C12",  # 4: Orange (bright, distinct from blue)
        "#8E44AD",  # 5: Purple (distinct from orange)
        "#16A085",  # 6: Dark Teal (distinct from purple)
        "#C0392B",  # 7: Dark Red (different from bright red)
        "#D35400",  # 8: Dark Orange (distinct from orange)
        "#2C3E50",  # 9: Dark Blue-Gray (distinct from all)
        "#E67E22",  # 10: Burnt Orange (distinct from all others)
    ]

    def __init__(self, args=None):
        """Initialize the window switcher"""
        logger.info("Initializing Otter Window Switcher")

        # Threading lock for Wnck access (prevents race conditions and corruption)
        self.wnck_lock = threading.RLock()

        # Parse arguments and set up configuration
        if args:
            self.config = {
                'nrows': args.nrows,
                'ncols': args.ncols,
                'xsize': args.xsize,
                'show_title': not args.notitle,
                'hide_delay': args.delay,
                'north': args.north,
                'south': args.south,
                'east': args.east,
                'west': args.west,
                'recent': args.recent,
                'main_character': args.main_character
            }
        else:
            self.config = self.get_default_config()

        # Initialize GTK and Wnck
        try:
            Gtk.init()
        except Exception as e:
            logger.error(f"Failed to initialize GTK: {e}")
            raise

        # Initialize Wnck if available (with thread safety)
        if WNCK_AVAILABLE:
            try:
                with self.wnck_lock:
                    self.screen_wnck = Wnck.Screen.get_default()
                    if self.screen_wnck:
                        try:
                            self.screen_wnck.force_update()
                        except Exception as force_update_error:
                            logger.warning(f"force_update() failed during init: {force_update_error}")
                            # Don't fail on force_update - screen is still usable
            except Exception as e:
                logger.error(f"Failed to initialize Wnck: {e}")
                self.screen_wnck = None
        else:
            logger.warning("Wnck not available - window switching disabled")
            self.screen_wnck = None

        # Window state
        self.window = None
        self.is_visible = False
        self.window_clicked = False
        self.HIDE_STATE = True  # Semaphore: True = window can hide, False = window cannot hide
        self._middle_click_mode = False  # Flag to keep otter visible during middle-click workflow

        # Drag mode state - initialize here to avoid AttributeError
        self.drag_active = False
        self.drag_window = None
        self.drag_signal_id = None

        # Screenshot cache with size limit
        self.screenshot_cache = {}
        self.window_buttons = []
        self.max_cache_size = 100  # Limit cache size to 100 windows

        # Most Recently Used (MRU) tracking
        # Dictionary mapping window XID to timestamp of last activation
        self.mru_timestamps = {}

        # Wnck health tracking
        self.wnck_last_recreation = time.time()
        self.wnck_recreation_interval = 120  # Recreate Wnck screen every 2 minutes (VERY aggressive for testing)
        self.wnck_call_count = 0
        self.wnck_just_recreated = False  # Flag to skip immediate force_update after recreation
        self.wnck_recreating = False  # Lock flag to prevent concurrent Wnck access during recreation

        # Monitoring IDs
        self.monitor_id = None
        self.screenshot_monitor_id = None
        self.delayed_hide_id = None

        # Cache update interval
        self.cache_update_interval = 2000  # 2 seconds
        self.last_valid_screenshots = {}

        # Set up the window
        self.create_window()

        # Set up monitoring
        self.setup_mouse_monitoring()
        self.setup_screenshot_caching()

        # Connect to window changes
        if self.screen_wnck:
            self.screen_wnck.connect("window-opened", self.on_window_changed)
            self.screen_wnck.connect("window-closed", self.on_window_changed)

    def get_default_config(self):
        """Get default configuration"""
        return {
            'nrows': None,  # Will be calculated based on window count
            'ncols': 4,     # Default to 4 columns (can be None when nrows is specified)
            'xsize': 160,
            'show_title': True,  # Show the fancy title bar
            'hide_delay': 0,     # Delay in milliseconds before hiding (default: 0)
            'north': True,  # Default to north edge
            'south': False,
            'east': False,
            'west': False,
            'recent': False,  # Most recently used ordering
            'main_character': False  # Respect fullscreen apps
        }

    def window_is_valid(self, window) -> bool:
        """Check if a window object is still valid (not deleted/corrupted).

        This prevents segfaults from accessing stale window pointers.
        """
        if not window:
            return False

        try:
            # Try a safe read-only operation that indicates the window is valid
            # get_name() is the safest Wnck method - it doesn't access WnckClassGroup
            name = window.get_name()
            return name is not None
        except Exception as e:
            logger.debug(f"Window validation failed: {e}")
            return False

    def calculate_layout_dimensions(self, window_count):
        """Calculate the missing dimension (rows or columns) based on window count"""
        if self.config['nrows'] is not None:
            # User specified rows, calculate columns
            ncols = max(1, (window_count + self.config['nrows'] - 1) // self.config['nrows'])
            return self.config['nrows'], ncols
        else:
            # User specified columns (or default), calculate rows
            nrows = max(1, (window_count + self.config['ncols'] - 1) // self.config['ncols'])
            return nrows, self.config['ncols']

    def setup_mouse_monitoring(self):
        """Set up monitoring for mouse position"""
        self.monitor_id = GLib.timeout_add(100, self.check_mouse_position)

    def setup_screenshot_caching(self):
        """Set up background screenshot caching for better thumbnails"""
        self.screenshot_monitor_id = GLib.timeout_add(self.cache_update_interval, self.update_screenshot_cache)

    def check_mouse_position(self):
        """Check if mouse cursor is at the specified screen edge and show/hide window accordingly"""
        try:
            # Get current mouse position
            display = Gdk.Display.get_default()
            seat = display.get_default_seat()
            pointer = seat.get_pointer()
            screen, x, y = pointer.get_position()
            # Get the monitor where the mouse cursor is located
            monitor = display.get_monitor_at_point(x, y)
            geometry = monitor.get_geometry()
            # Monitor bounds (absolute coordinates)
            monitor_x = geometry.x
            monitor_y = geometry.y
            monitor_width = geometry.width
            monitor_height = geometry.height
            
            # Handle drag mode
            if self.drag_active and self.drag_window:
                try:
                    # Move window to follow mouse
                    geometry = self.drag_window.get_geometry()
                    new_x = x - geometry.width // 2
                    new_y = y - geometry.height // 2
                    self.drag_window.move(new_x, new_y)
                except Exception as e:
                    logger.error(f"Error in drag mode: {e}")
                    self.drag_active = False
            
            # Only check for edge trigger when window is NOT visible
            if not self.is_visible:
                # Check if --main-character is enabled and active window is fullscreen
                if self.config.get('main_character') and self.is_active_window_fullscreen():
                    return True  # Continue monitoring but don't trigger (respect the main character!)

                # Check if mouse is at the specified edge of the screen
                if self.config.get('north'):
                    # North edge (top)
                    if y - monitor_y <= 5: 
                        self.show_window()
                elif self.config.get('south'):
                    # South edge (bottom)
                    if monitor_y + monitor_height - y <= 5:
                        self.show_window()
                elif self.config.get('east'):
                    # East edge (right)
                    if monitor_x + monitor_width - x <= 5:
                        self.show_window()
                elif self.config.get('west'):
                    # West edge (left)
                    if x - monitor_x <= 5:
                        self.show_window()
            else:
                # Window is visible - only check for hide conditions
                if (y > monitor_y + 100 or
                    x > monitor_x + monitor_width - 100 or
                    x < monitor_x + 100 or
                    y < monitor_y + 100) and not self.mouse_in_window():
                    # Hide when mouse moves away from the edge AND not in window
                    self.hide_window()
        except Exception as e:
            logger.error(f"Error checking mouse position: {e}")
        return True  # Continue monitoring


    def mouse_in_window(self):
        """Check if mouse cursor is currently inside the window"""
        if not self.window or not self.window.get_window():
            return False

        try:
            # Get current mouse position
            display = Gdk.Display.get_default()
            seat = display.get_default_seat()
            pointer = seat.get_pointer()
            screen, x, y = pointer.get_position()

            # Get window bounds
            window_x, window_y = self.window.get_position()
            window_width = self.window.get_allocated_width()
            window_height = self.window.get_allocated_height()

            # Check if mouse is within window bounds
            return (window_x <= x <= window_x + window_width and
                    window_y <= y <= window_y + window_height)
        except Exception as e:
            logger.error(f"Error checking mouse in window: {e}")
            return False

    def update_screenshot_cache(self):
        """Update screenshot cache for all visible windows"""
        try:
            # Only update if switcher is visible (avoid long idle processing)
            if not self.is_visible:
                # Clean up old cache entries even when not visible
                try:
                    if self.screen_wnck:
                        current_windows = self.get_user_windows()
                        existing_window_ids = {self.get_window_id(w['window']) for w in current_windows}
                        cached_window_ids = set(self.screenshot_cache.keys())

                        for window_id in cached_window_ids - existing_window_ids:
                            try:
                                del self.screenshot_cache[window_id]
                                del self.last_valid_screenshots[window_id]
                            except (KeyError, AttributeError):
                                pass
                except Exception as e:
                    logger.debug(f"Error cleaning cache during idle: {e}")
                return True

            current_windows = self.get_user_windows()

            # Clean up cache for windows that no longer exist
            existing_window_ids = {self.get_window_id(w['window']) for w in current_windows}
            cached_window_ids = set(self.screenshot_cache.keys())

            for window_id in cached_window_ids - existing_window_ids:
                try:
                    del self.screenshot_cache[window_id]
                    if window_id in self.last_valid_screenshots:
                        del self.last_valid_screenshots[window_id]
                except (KeyError, AttributeError):
                    pass

            # Enforce cache size limit
            if len(self.screenshot_cache) > self.max_cache_size:
                # Remove oldest entries (simple FIFO)
                keys_to_remove = list(self.screenshot_cache.keys())[:(len(self.screenshot_cache) - self.max_cache_size)]
                for key in keys_to_remove:
                    try:
                        del self.screenshot_cache[key]
                        if key in self.last_valid_screenshots:
                            del self.last_valid_screenshots[key]
                    except (KeyError, AttributeError):
                        pass

            # Update screenshots for current windows
            for window_info in current_windows:
                try:
                    window = window_info['window']
                    window_id = self.get_window_id(window)

                    # Capture screenshot
                    screenshot = self.capture_high_quality_screenshot(window)
                    if screenshot:
                        self.screenshot_cache[window_id] = screenshot
                except Exception as e:
                    logger.debug(f"Error capturing screenshot for window: {e}")

        except Exception as e:
            logger.error(f"Error updating screenshot cache: {e}")

        return True  # Continue periodic updates

    def get_window_id(self, window):
        """Get a unique identifier for a window"""
        try:
            return window.get_xid()
        except Exception as xid_error:
            # Fallback to window name + pid if XID not available
            logger.debug(f"get_xid() failed, using fallback: {xid_error}")
            try:
                app = window.get_application()
                pid = app.get_pid() if app else 0
                name = window.get_name() if window else "unknown"
                return f"{name}_{pid}"
            except Exception as fallback_error:
                logger.error(f"CRITICAL: get_application() failed in get_window_id(): {fallback_error}")
                # Last resort fallback
                try:
                    return f"unknown_{id(window)}"
                except:
                    return "unknown_window"

    # Update the capture_high_quality_screenshot method:
    def capture_high_quality_screenshot(self, window):
        """Capture high-quality screenshot, handling minimized windows."""
        try:
            window_id = self.get_window_id(window)
            
            # If window is minimized, use last known valid screenshot
            if window.is_minimized():
                if window_id in self.last_valid_screenshots:
                    return self.last_valid_screenshots[window_id]
                else:
                    # No valid screenshot available, return None to use icon
                    return None
            
            # Try to capture screenshot for non-minimized windows
            isolated_pixbuf = self.capture_isolated_window(window)
            if isolated_pixbuf:
                scaled = self.scale_pixbuf_high_quality(isolated_pixbuf)
                if scaled:
                    # Store as last valid screenshot
                    self.last_valid_screenshots[window_id] = scaled
                    return scaled

            raised_pixbuf = self.capture_with_temporary_raise(window)
            if raised_pixbuf:
                scaled = self.scale_pixbuf_high_quality(raised_pixbuf)
                if scaled:
                    self.last_valid_screenshots[window_id] = scaled
                    return scaled

            # Fallback to screen area capture
            screen_pixbuf = self.capture_screen_area(window)
            if screen_pixbuf:
                self.last_valid_screenshots[window_id] = screen_pixbuf
                return screen_pixbuf
                
            # If all fails and we have a cached screenshot, use it
            if window_id in self.last_valid_screenshots:
                return self.last_valid_screenshots[window_id]

        except Exception as e:
            logger.error(f"Error capturing screenshot: {e}")
            # Try to return cached screenshot on error
            window_id = self.get_window_id(window)
            if window_id in self.last_valid_screenshots:
                return self.last_valid_screenshots[window_id]

        return None


    def capture_isolated_window(self, window):
        """Try to capture the window content directly without overlaps"""
        try:
            # Check if GdkX11 is available
            if not GdkX11:
                return None

            # Get the X11 window ID
            try:
                xid = window.get_xid()
            except Exception as e:
                logger.debug(f"Failed to get XID: {e}")
                return None

            if not xid:
                return None

            # Get the GDK window from XID
            display = Gdk.Display.get_default()
            if not display:
                logger.debug("No display available")
                return None

            try:
                gdk_window = GdkX11.X11Window.foreign_new_for_display(display, xid)
            except Exception as e:
                logger.debug(f"Failed to create GDK window from XID: {e}")
                return None

            # NULL check - foreign_new_for_display can return None
            if not gdk_window:
                logger.debug(f"GDK window creation returned None for XID {xid}")
                return None

            try:
                if gdk_window.is_viewable():
                    # Get window dimensions
                    width = gdk_window.get_width()
                    height = gdk_window.get_height()

                    if width > 0 and height > 0:
                        # Capture directly from the window
                        pixbuf = Gdk.pixbuf_get_from_window(gdk_window, 0, 0, width, height)
                        # NULL check for pixbuf
                        if pixbuf:
                            return pixbuf
                        else:
                            logger.debug(f"pixbuf_get_from_window returned None for window {xid}")
            except Exception as e:
                logger.debug(f"Error during viewable check or capture: {e}")

        except Exception as e:
            logger.debug(f"Error in isolated capture: {e}")

        return None

    def capture_with_temporary_raise(self, window):
        """Temporarily raise window to top, capture it, then restore"""
        try:
            # Check if window is minimized
            if window.is_minimized():
                return None

            if not self.screen_wnck:
                return None

            # Store current active window
            active_window = self.screen_wnck.get_active_window()

            # Temporarily activate the target window
            timestamp = Gtk.get_current_event_time()
            window.activate(timestamp)

            # Use GLib timeout instead of blocking sleep
            # For now, we'll do a short non-blocking idle call
            GLib.idle_add(self._do_capture_after_raise, window, active_window, timestamp)
            return None  # Will be handled asynchronously

        except Exception as e:
            logger.error(f"Error in temporary raise capture: {e}")

        return None

    def _do_capture_after_raise(self, window, active_window, timestamp):
        """Capture window content after it has been raised (called via idle callback)"""
        try:
            # Validate that window still exists (defensive check)
            if not self.window_is_valid(window):
                logger.debug("Window is no longer valid, skipping deferred capture")
                return False

            # Capture the window area
            geometry = window.get_geometry()
            x, y, width, height = geometry

            if width > 0 and height > 0:
                root_window = Gdk.get_default_root_window()
                if root_window:
                    pixbuf = Gdk.pixbuf_get_from_window(root_window, x, y, width, height)

                    # Store in cache (with null check)
                    if pixbuf:
                        window_id = self.get_window_id(window)
                        scaled = self.scale_pixbuf_high_quality(pixbuf)
                        if scaled:
                            self.screenshot_cache[window_id] = scaled

            # Restore the previously active window (with validation)
            if active_window and active_window != window and self.screen_wnck:
                if self.window_is_valid(active_window):
                    try:
                        active_window.activate(timestamp + 1)
                    except Exception as restore_error:
                        logger.debug(f"Could not restore previous window: {restore_error}")

        except Exception as e:
            logger.debug(f"Error in deferred capture: {e}")

        return False

    def capture_screen_area(self, window):
        """Fallback method: capture screen area (may include overlaps)"""
        try:
            geometry = window.get_geometry()
            x, y, width, height = geometry

            if width <= 0 or height <= 0:
                return None

            root_window = Gdk.get_default_root_window()
            pixbuf = Gdk.pixbuf_get_from_window(root_window, x, y, width, height)

            return self.scale_pixbuf_high_quality(pixbuf) if pixbuf else None

        except Exception as e:
            logger.error(f"Error in screen area capture: {e}")
            return None

    def scale_pixbuf_high_quality(self, pixbuf):
        """Scale a pixbuf to thumbnail size with high quality"""
        if not pixbuf:
            return None

        try:
            # Use configurable thumbnail size
            thumbnail_width = self.config['xsize']

            # Calculate scaling to maintain aspect ratio
            original_width = pixbuf.get_width()
            original_height = pixbuf.get_height()

            if original_width > 0 and original_height > 0:
                # Calculate height based on aspect ratio
                aspect_ratio = original_height / original_width
                thumbnail_height = int(thumbnail_width * aspect_ratio)

                scale_x = thumbnail_width / original_width
                scale_y = thumbnail_height / original_height
                scale = min(scale_x, scale_y)

                new_width = int(original_width * scale)
                new_height = int(original_height * scale)

                # Use high-quality scaling with proper enum
                scaled_pixbuf = pixbuf.scale_simple(
                    new_width, new_height,
                    GdkPixbuf.InterpType.HYPER
                )
                return scaled_pixbuf

        except Exception as e:
            logger.error(f"Error scaling pixbuf: {e}")

        return None

    def create_window(self):
        """Create the main application window"""
        self.window = Gtk.Window()
        self.window.set_title("Otter App Switcher")  # Removed emoji for professional appearance
        self.window.set_decorated(False)  # No window decorations
        self.window.set_keep_above(True)  # Keep window on top
        self.window.set_skip_taskbar_hint(True)  # Don't show in taskbar
        self.window.set_skip_pager_hint(True)  # Don't show in pager

        # Set window type hint for proper behavior
        # POPUP is GTK 4.0+, use UTILITY for GTK 3.0 compatibility
        try:
            # Try POPUP first (GTK 4.0)
            self.window.set_type_hint(Gdk.WindowTypeHint.POPUP)
        except AttributeError:
            # Fallback to UTILITY (GTK 3.0)
            self.window.set_type_hint(Gdk.WindowTypeHint.UTILITY)

        # Connect signals
        self.window.connect("destroy", self.on_destroy)
        self.window.connect("leave-notify-event", self.on_leave_notify)
        self.window.connect("enter-notify-event", self.on_enter_notify)
        self.window.connect("scroll-event", self.on_scroll_event)

        # Enable mouse tracking
        self.window.add_events(Gdk.EventMask.LEAVE_NOTIFY_MASK |
                              Gdk.EventMask.ENTER_NOTIFY_MASK |
                              Gdk.EventMask.SCROLL_MASK)

        # Create main container with dark theme styling
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_start(15)
        main_box.set_margin_end(15)
        main_box.set_margin_top(15)
        main_box.set_margin_bottom(15)

        # Style the window using system theme colors
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            window {
                background-color: alpha(@theme_bg_color, 0.95);
                border-radius: 10px;
                border: 2px solid @borders;
            }
            .title-bar {
                background: @theme_bg_color;
                border-radius: 8px;
                padding: 8px;
                margin-bottom: 10px;
                border: 1px solid @borders;
            }
            .window-button {
                background-color: alpha(@theme_base_color, 0.9);
                border-radius: 8px;
                border: 1px solid @borders;
                padding: 8px;
                margin: 4px;
            }
            .minimized-window-button {
                opacity: 0.6;
                border: 2px solid @warning_color;
            }
            .window-button:hover {
                background-color: alpha(@theme_selected_bg_color, 0.5);
                border: 2px solid @theme_selected_bg_color;
            }
            .workspace-badge {
                background-color: alpha(@theme_selected_bg_color, 0.85);
                color: @theme_selected_fg_color;
                border-radius: 50%;
                padding: 4px;
                margin: 4px;
                border: 1px solid @theme_selected_bg_color;
            }
            label {
                color: @theme_fg_color;
            }
            """)
        
        style_context = Gtk.StyleContext()
        style_context.add_provider_for_screen(Gdk.Screen.get_default(),
                                            css_provider,
                                            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # Create fancy title bar with otter emoji (only if show_title is True)
        if self.config['show_title']:
            title_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            title_bar.get_style_context().add_class("title-bar")

            # Add otter emoji
            otter_label = Gtk.Label()
            otter_label.set_markup("<span size='x-large'>🦦</span>")
            otter_label.set_halign(Gtk.Align.START)
            title_bar.pack_start(otter_label, False, False, 0)

            # Add title text
            title_label = Gtk.Label()
            title_label.set_markup("<span size='large' weight='bold'>Otter App Switcher</span>")
            title_label.set_halign(Gtk.Align.CENTER)
            title_label.set_hexpand(True)
            title_bar.pack_start(title_label, True, True, 0)

            # Add subtitle
            subtitle_label = Gtk.Label()
            subtitle_label.set_markup("<span size='small' alpha='70%'>Active Windows</span>")
            subtitle_label.set_halign(Gtk.Align.END)
            title_bar.pack_start(subtitle_label, False, False, 0)

            main_box.pack_start(title_bar, False, False, 0)

        # Create scrollable window for the list
        self.scroll_window = Gtk.ScrolledWindow()

        # Configure scroll policies based on layout
        if self.config['nrows'] == 1 and self.config['ncols'] > 1:
            # Single row layout: enable horizontal scrolling, disable vertical
            self.scroll_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
            self.scroll_window.set_min_content_height(150)  # Smaller height for single row
            self.scroll_window.set_max_content_height(200)
        else:
            # Multi-row layout: enable vertical scrolling, disable horizontal
            self.scroll_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            self.scroll_window.set_min_content_height(200)
            self.scroll_window.set_max_content_height(400)

        # Create flow box for window thumbnails
        self.flow_box = Gtk.FlowBox()
        self.flow_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flow_box.set_homogeneous(False)
        self.flow_box.set_row_spacing(10)
        self.flow_box.set_column_spacing(10)

        self.scroll_window.add(self.flow_box)
        main_box.pack_start(self.scroll_window, True, True, 0)

        # Add instructions
        instructions = Gtk.Label()
        instructions.set_markup("<span size='small'><i>Click on a window to switch to it. Move mouse away to close.</i></span>")
        instructions.set_halign(Gtk.Align.CENTER)
        main_box.pack_start(instructions, False, False, 0)

        self.window.add(main_box)

        # Position window at top center of screen
        self.window.set_position(Gtk.WindowPosition.CENTER)

        # Initially hide the window
        self.window.hide()

    def get_user_windows(self) -> List[Dict]:
        """Get list of user windows, including minimized windows"""
        windows = []

        if not self.screen_wnck:
            return windows

        # If recreation is in progress, return empty list (don't touch Wnck)
        if self.wnck_recreating:
            logger.debug("Wnck recreation in progress, skipping query")
            return windows

        # Use lock to prevent Wnck access during other operations
        with self.wnck_lock:
            # Periodically recreate Wnck screen to prevent corruption
            if self.should_recreate_wnck():
                self.recreate_wnck_screen()

            # Track Wnck usage
            self.wnck_call_count += 1

            try:
                # CRITICAL: Force Wnck to update its internal state before querying
                # This prevents accessing stale/corrupted WnckClassGroup objects
                # EXCEPT right after recreation - let it initialize naturally first
                if self.wnck_just_recreated:
                    logger.debug("Skipping force_update immediately after recreation")
                    self.wnck_just_recreated = False  # Reset flag
                else:
                    try:
                        self.screen_wnck.force_update()
                    except Exception as force_update_error:
                        # If force_update fails, Wnck state is corrupted - recreate immediately
                        logger.error(f"force_update() failed (Wnck corruption detected): {force_update_error}")
                        logger.info("Attempting immediate Wnck recreation due to corruption...")
                        if self.recreate_wnck_screen():
                            # Try one more time with fresh screen
                            try:
                                self.screen_wnck.force_update()
                            except Exception as retry_error:
                                logger.error(f"force_update() failed after recreation: {retry_error}")
                                return windows
                        else:
                            logger.error("Failed to recreate Wnck screen after corruption")
                            return windows

                # Get all windows from Wnck
                try:
                    window_list = self.screen_wnck.get_windows()
                except Exception as get_windows_error:
                    # If get_windows fails, Wnck state is corrupted
                    logger.error(f"get_windows() failed (Wnck corruption detected): {get_windows_error}")
                    return windows

                if not window_list:
                    return windows

                for window in window_list:
                    try:
                        # Validate window object is still valid (defensive check)
                        if not self.window_is_valid(window):
                            logger.debug("Window failed validation, skipping")
                            continue

                        # Include normal windows, even if minimized
                        try:
                            window_type = window.get_window_type()
                            if window_type != Wnck.WindowType.NORMAL:
                                continue
                        except Exception as type_error:
                            logger.debug(f"get_window_type() failed: {type_error}")
                            # Assume it's not a normal window if we can't determine type
                            continue

                        # Get window name (safe operation)
                        try:
                            window_name = window.get_name() or "Unknown"
                        except Exception as name_error:
                            logger.debug(f"get_name() failed: {name_error}")
                            window_name = "Unknown"

                        # IMPORTANT: Skip get_application() entirely to avoid WnckClassGroup corruption
                        # Instead, use window name as app identifier
                        app_name = window_name

                        # Skip common system applications and our own window
                        system_apps = [
                            'gnome-shell', 'cinnamon', 'gnome-settings-daemon',
                            'gnome-panel', 'mate-panel', 'xfce4-panel', 'plasma-desktop',
                            'kwin', 'compiz', 'metacity', 'mutter', 'unity',
                            'unity-panel-service', 'Desktop', 'Otter Window Switcher'
                        ]

                        # Skip if it's a system app or our own window
                        if (app_name.lower() not in [app.lower() for app in system_apps] and
                            window_name != "Otter Window Switcher" and
                            window_name and len(window_name.strip()) > 0):

                            try:
                                is_minimized = window.is_minimized()
                            except Exception as min_error:
                                logger.debug(f"is_minimized() failed: {min_error}")
                                is_minimized = False

                            try:
                                icon = window.get_icon() if window.get_icon() else None
                            except Exception as icon_error:
                                logger.debug(f"get_icon() failed: {icon_error}")
                                icon = None

                            # Get XID once and cache it to avoid calling get_xid() on potentially stale objects
                            try:
                                xid = window.get_xid()
                            except Exception as xid_error:
                                logger.debug(f"get_xid() failed during window collection: {xid_error}")
                                xid = None

                            # Get workspace information for corner badge display
                            workspace_index = None
                            workspace_name = "Unknown"
                            try:
                                workspace = window.get_workspace()
                                if workspace:
                                    # Find workspace index (1-indexed for user display)
                                    all_workspaces = self.screen_wnck.get_workspaces()
                                    for idx, ws in enumerate(all_workspaces):
                                        if ws == workspace:
                                            workspace_index = idx + 1  # 1-indexed
                                            workspace_name = ws.get_name()
                                            break
                            except Exception as ws_error:
                                # Gracefully degrade - badge will show "?" if lookup fails
                                logger.debug(f"Failed to get workspace info: {ws_error}")

                            windows.append({
                                'window': window,
                                'name': window_name,
                                'app_name': app_name,
                                'icon': icon,
                                'is_minimized': is_minimized,
                                'xid': xid,  # Cache XID for MRU sorting
                                'workspace_index': workspace_index,      # 1-indexed workspace number
                                'workspace_name': workspace_name         # Workspace name
                            })

                    except Exception as e:
                        logger.debug(f"Error processing window: {e}")
                        continue

            except Exception as e:
                logger.error(f"Error getting user windows: {e}")
                return []

        # Apply MRU ordering if --recent flag is enabled
        if self.config.get('recent', False):
            # First, sort alphabetically by application name
            windows.sort(key=lambda w: w['app_name'].lower())

            # Then, stable sort by MRU timestamp (most recent first)
            # Windows with no timestamp get timestamp 0 (appear at the end)
            try:
                def safe_get_timestamp(w):
                    """Safely get MRU timestamp for a window using cached XID"""
                    xid = w.get('xid')
                    if xid is not None:
                        return self.mru_timestamps.get(xid, 0)
                    return 0  # Windows without XID get lowest priority

                windows.sort(key=safe_get_timestamp, reverse=True)
            except Exception as e:
                logger.debug(f"Error applying MRU sort: {e}")

        return windows

    def create_window_thumbnail(self, window_info: Dict) -> Gtk.Widget:
        """Create a thumbnail button for a window with workspace badge indicator"""
        window = window_info['window']
        name = window_info['name']
        app_name = window_info['app_name']
        icon = window_info['icon']
        is_minimized = window_info.get('is_minimized', False)
        workspace_index = window_info.get('workspace_index')  # Get workspace for badge

        # Create main button
        button = Gtk.Button()
        button.get_style_context().add_class("window-button")
        if is_minimized:
            button.get_style_context().add_class("minimized-window-button")
        button.set_relief(Gtk.ReliefStyle.NONE)

        # Create vertical box for content
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)

        # Try to get window screenshot/thumbnail with workspace badge overlay
        thumbnail = self.get_window_thumbnail_with_badge(window, workspace_index)
        if thumbnail:
            vbox.pack_start(thumbnail, False, False, 0)
        elif icon:
            # Use window icon if available
            icon_image = Gtk.Image()
            icon_image.set_from_pixbuf(icon)
            icon_image.set_pixel_size(48)
            vbox.pack_start(icon_image, False, False, 0)
        else:
            # Use default icon
            icon_image = Gtk.Image()
            icon_image.set_from_icon_name("application-x-executable", Gtk.IconSize.LARGE_TOOLBAR)
            vbox.pack_start(icon_image, False, False, 0)

        # Add window name label
        label = Gtk.Label()
        # Truncate long names
        display_name = name[:25] + "..." if len(name) > 25 else name
        label.set_markup(f"<span size='small'>{display_name}</span>")
        label.set_line_wrap(True)
        label.set_max_width_chars(20)
        vbox.pack_start(label, False, False, 0)

        # Add app name if different from window name
        if app_name and app_name != name:
            app_label = Gtk.Label()
            app_label.set_markup(f"<span size='x-small' alpha='70%'>{app_name}</span>")
            vbox.pack_start(app_label, False, False, 0)

        button.add(vbox)

        # Connect click event
        button.connect("clicked", self.on_window_clicked, window)
        button.connect("button-press-event", self.on_button_press_event, window)

        return button



    def get_window_thumbnail(self, window) -> Optional[Gtk.Widget]:
        """Get a thumbnail image of the window"""
        try:
            # First, try to get cached screenshot
            window_id = self.get_window_id(window)
            cached_screenshot = self.screenshot_cache.get(window_id)

            if cached_screenshot:
                # Use cached high-quality screenshot
                image = Gtk.Image()
                image.set_from_pixbuf(cached_screenshot)

                # Create frame for the thumbnail
                frame = Gtk.Frame()
                frame.set_shadow_type(Gtk.ShadowType.IN)
                frame.add(image)

                return frame

            # Fallback: try to get window icon
            pixbuf = window.get_icon() or window.get_mini_icon()

            if pixbuf:
                # Scale the icon to thumbnail size using configurable size
                thumbnail_width = self.config['xsize']

                # Calculate scaling to maintain aspect ratio
                original_width = pixbuf.get_width()
                original_height = pixbuf.get_height()

                if original_width > 0 and original_height > 0:
                    # Calculate height based on aspect ratio
                    aspect_ratio = original_height / original_width
                    thumbnail_height = int(thumbnail_width * aspect_ratio)

                    scale_x = thumbnail_width / original_width
                    scale_y = thumbnail_height / original_height
                    scale = min(scale_x, scale_y)

                    new_width = int(original_width * scale)
                    new_height = int(original_height * scale)

                    scaled_pixbuf = pixbuf.scale_simple(new_width, new_height, 3)  # High quality scaling

                    # Create image widget
                    image = Gtk.Image()
                    image.set_from_pixbuf(scaled_pixbuf)

                    # Create frame for the thumbnail
                    frame = Gtk.Frame()
                    frame.set_shadow_type(Gtk.ShadowType.IN)
                    frame.add(image)

                    return frame

            # Final fallback: create a drawing area with window representation
            return self.create_fallback_thumbnail(window)

        except Exception as e:
            logger.error(f"Error creating thumbnail: {e}")
            return self.create_fallback_thumbnail(window)

    def get_window_thumbnail_with_badge(self, window, workspace_index):
        """Get thumbnail with workspace badge overlay in top-right corner.

        Returns a Gtk.Overlay containing the thumbnail with a workspace
        badge. The badge is pass-through so clicks pass to activate window.
        """
        try:
            window_id = self.get_window_id(window)
            cached_screenshot = self.screenshot_cache.get(window_id)

            if not cached_screenshot:
                return None

            # Create base thumbnail with frame
            image = Gtk.Image()
            image.set_from_pixbuf(cached_screenshot)
            frame = Gtk.Frame()
            frame.set_shadow_type(Gtk.ShadowType.IN)
            frame.add(image)

            # Only add badge overlay if we have workspace info
            if workspace_index is None:
                return frame

            # Create overlay container for badge positioning
            overlay = Gtk.Overlay()
            overlay.add(frame)

            # Create and add the workspace badge
            badge = self.create_workspace_badge(workspace_index)
            if badge:
                overlay.add_overlay(badge)
                # Allow clicks to pass through badge to activate window
                overlay.set_overlay_pass_through(badge, True)

            return overlay

        except Exception as e:
            logger.debug(f"Error creating thumbnail with badge: {e}")
            return None

    def create_workspace_badge(self, workspace_index):
        """Create a workspace indicator badge for the top-right corner.

        Creates a small circular badge displaying the workspace number (1-indexed).
        Color-coded by workspace (different color for each workspace).
        Positioned absolutely at top-right, doesn't interfere with window clicks.
        """
        try:
            # Container box positioned at top-right corner
            badge_container = Gtk.Box()
            badge_container.set_size_request(40, 40)
            badge_container.set_halign(Gtk.Align.END)      # Right alignment
            badge_container.set_valign(Gtk.Align.START)    # Top alignment
            badge_container.set_margin_end(2)              # Small margin from edge
            badge_container.set_margin_top(2)

            # Badge label - displays workspace number (1-indexed for users)
            badge_label = Gtk.Label()
            display_text = str(workspace_index) if workspace_index else "?"
            badge_label.set_markup(f"<span size='11000' weight='bold'>{display_text}</span>")
            badge_label.set_justify(Gtk.Justification.CENTER)

            # Get color for this workspace (cycle through palette for workspaces > 10)
            if workspace_index and workspace_index > 0:
                color_index = (workspace_index - 1) % len(self.WORKSPACE_COLORS)
                workspace_color = self.WORKSPACE_COLORS[color_index]

                # Create CSS provider with workspace-specific styling
                css_provider = Gtk.CssProvider()
                css_data = f"""
                    label {{
                        background-color: {workspace_color};
                        color: white;
                        border-radius: 50%;
                        padding: 4px;
                        margin: 4px;
                        border: 1px solid {workspace_color};
                    }}
                """.encode('utf-8')
                css_provider.load_from_data(css_data)

                # Apply color-specific CSS to the badge label
                badge_context = badge_label.get_style_context()
                badge_context.add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            else:
                # Fallback styling for unknown workspace
                badge_context = badge_label.get_style_context()
                badge_context.add_class("workspace-badge")

            badge_container.pack_start(badge_label, True, True, 0)
            badge_container.show_all()

            return badge_container

        except Exception as e:
            logger.debug(f"Error creating workspace badge: {e}")
            return None

    def capture_window_screenshot(self, window):
        """Capture a screenshot of the window"""
        try:
            # Get the GDK window
            gdk_window = window.get_xid()
            if not gdk_window:
                return None

            # Get window geometry
            geometry = window.get_geometry()
            x, y, width, height = geometry

            if width <= 0 or height <= 0:
                return None

            # Get the root window
            root_window = Gdk.get_default_root_window()

            # Capture the window area
            pixbuf = Gdk.pixbuf_get_from_window(root_window, x, y, width, height)

            return pixbuf

        except Exception as e:
            logger.error(f"Error capturing window screenshot: {e}")
            return None

    def create_fallback_thumbnail(self, window):
        """Create a fallback thumbnail when screenshot fails"""
        drawing_area = Gtk.DrawingArea()
        # Use configurable size with 4:3 aspect ratio
        thumbnail_width = self.config['xsize']
        thumbnail_height = int(thumbnail_width * 0.75)  # 4:3 aspect ratio
        drawing_area.set_size_request(thumbnail_width, thumbnail_height)

        def draw_callback(widget, cr):
            # Get window name for color variation
            window_name = window.get_name() or "Unknown"
            hash_value = hash(window_name) % 360

            # Create a colored rectangle based on window name
            import colorsys
            r, g, b = colorsys.hsv_to_rgb(hash_value / 360.0, 0.6, 0.8)

            cr.set_source_rgba(r, g, b, 0.8)
            cr.rectangle(0, 0, thumbnail_width, thumbnail_height)
            cr.fill()

            # Add a border
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.8)
            cr.set_line_width(2)
            cr.rectangle(1, 1, thumbnail_width - 2, thumbnail_height - 2)
            cr.stroke()

            # Add window name text
            cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
            cr.select_font_face("Sans", 0, 0)
            cr.set_font_size(10)

            # Truncate long names
            display_name = window_name[:15] + "..." if len(window_name) > 15 else window_name
            text_extents = cr.text_extents(display_name)

            # Center the text
            x = (thumbnail_width - text_extents.width) / 2
            y = (thumbnail_height + text_extents.height) / 2

            cr.move_to(x, y)
            cr.show_text(display_name)

        drawing_area.connect("draw", draw_callback)
        return drawing_area

    def populate_windows(self):
        """Populate the window list with current windows"""
        try:
            # Clear existing buttons safely
            try:
                for child in self.flow_box.get_children():
                    self.flow_box.remove(child)
            except Exception as e:
                logger.debug(f"Error clearing children: {e}")

            self.window_buttons.clear()

            # Get user windows with comprehensive error handling
            try:
                self.windows_list = self.get_user_windows()
            except Exception as e:
                logger.error(f"Error getting user windows: {e}")
                self.windows_list = []

            if not self.windows_list:
                # Show message if no windows found
                try:
                    label = Gtk.Label()
                    label.set_markup("<span size='large'>No active windows found</span>")
                    label.set_halign(Gtk.Align.CENTER)
                    self.flow_box.add(label)
                except Exception as e:
                    logger.debug(f"Error showing no windows message: {e}")
            else:
                # Calculate dynamic dimensions based on window count
                window_count = len(self.windows_list)
                nrows, ncols = self.calculate_layout_dimensions(window_count)

                # Update flow box configuration with calculated dimensions
                try:
                    self.flow_box.set_min_children_per_line(ncols)
                    self.flow_box.set_max_children_per_line(ncols)
                except Exception as e:
                    logger.debug(f"Error setting flow box dimensions: {e}")

                # Update scroll window configuration based on layout
                if nrows == 1 and ncols > 1:
                    # Single row layout: enable horizontal scrolling, disable vertical
                    try:
                        self.scroll_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)

                        # Calculate required width for all columns
                        thumbnail_width = self.config['xsize']
                        spacing = 10  # column spacing
                        margin = 30   # window margins
                        required_width = ncols * thumbnail_width + (ncols - 1) * spacing + margin

                        # Set minimum width to ensure all columns are visible
                        self.scroll_window.set_min_content_width(required_width)

                        # Also set the main window to be wide enough
                        self.window.set_default_size(required_width + 100, -1)
                    except Exception as e:
                        logger.debug(f"Error setting scroll configuration: {e}")
                else:
                    # Multi-row layout: enable vertical scrolling, disable horizontal
                    try:
                        self.scroll_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
                    except Exception as e:
                        logger.debug(f"Error setting scroll policy: {e}")

                # Create thumbnail buttons for each window
                for window_info in self.windows_list:
                    try:
                        thumbnail = self.create_window_thumbnail(window_info)
                        self.window_buttons.append(thumbnail)
                        self.flow_box.add(thumbnail)
                    except Exception as e:
                        logger.debug(f"Error creating thumbnail: {e}")
                        continue

            try:
                self.flow_box.show_all()
            except Exception as e:
                logger.debug(f"Error showing flow box: {e}")

        except Exception as e:
            logger.error(f"Error in populate_windows: {e}")

    def recreate_wnck_screen(self):
        """Recreate the Wnck screen object to prevent corruption"""
        if not WNCK_AVAILABLE:
            return False

        try:
            # Set lock to prevent other code from touching Wnck during recreation
            self.wnck_recreating = True
            logger.info("Recreating Wnck screen object...")

            # Disconnect signals from old screen first
            if self.screen_wnck:
                try:
                    # Try to disconnect all handlers (best effort)
                    GLib.signal_handlers_destroy(self.screen_wnck)
                except:
                    pass

            # Longer delay to let old screen settle and any pending events clear
            time.sleep(0.2)

            # Create new screen
            self.screen_wnck = Wnck.Screen.get_default()

            # DON'T call force_update immediately after creation
            # Let it initialize naturally first

            # Reconnect signals to new screen
            self.screen_wnck.connect("window-opened", self.on_window_changed)
            self.screen_wnck.connect("window-closed", self.on_window_changed)

            self.wnck_last_recreation = time.time()
            self.wnck_call_count = 0
            self.wnck_just_recreated = True  # Skip immediate force_update

            # Longer delay before returning to let Wnck settle completely
            time.sleep(0.2)

            # Clear lock
            self.wnck_recreating = False

            logger.info("Wnck screen recreated successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to recreate Wnck screen: {e}")
            self.wnck_recreating = False  # Clear lock even on failure
            return False

    def should_recreate_wnck(self) -> bool:
        """Check if we should recreate the Wnck screen object"""
        # Recreate every hour as preventive maintenance
        if time.time() - self.wnck_last_recreation > self.wnck_recreation_interval:
            logger.info(f"Wnck screen object is {self.wnck_recreation_interval}s old, recreating...")
            return True

        # Recreate after many calls (potential memory fragmentation)
        if self.wnck_call_count > 10000:
            logger.info(f"Wnck has been called {self.wnck_call_count} times, recreating...")
            return True

        return False

    def is_active_window_fullscreen(self) -> bool:
        """Check if the currently active window is fullscreen"""
        if not self.screen_wnck:
            return False

        try:
            # Get the active window
            active_window = self.screen_wnck.get_active_window()
            if not active_window:
                return False

            # Check if window is fullscreen
            return active_window.is_fullscreen()

        except Exception as e:
            # If we can't determine, assume not fullscreen to be safe
            logger.debug(f"Error checking fullscreen status: {e}")
            return False

    def show_window(self):
        """Show the window switcher"""
        if not self.is_visible and self.window:
            # Reset the clicked flag when showing the window
            self.window_clicked = False

            # Populate windows first to ensure final window size
            self.populate_windows()

            # Show window to get its final size
            self.window.show_all()

            # Use idle_add to position the window after layout is complete
            GLib.idle_add(self._position_window)

            # Ensure window gets focus for keyboard events
            self.window.present()
            self.window.grab_focus()

            # Force keyboard focus
            GLib.idle_add(self.grab_keyboard_focus)

            self.is_visible = True

    def _position_window(self):
        """Position the window after layout is complete"""
        if not self.window or not self.is_visible:
            return False

        # Get current mouse position
        display = Gdk.Display.get_default()
        seat = display.get_default_seat()
        pointer = seat.get_pointer()
        screen, mouse_x, mouse_y = pointer.get_position()

        # Get the monitor where the mouse cursor is located
        monitor = display.get_monitor_at_point(mouse_x, mouse_y)
        geometry = monitor.get_geometry()

        # Monitor bounds (absolute coordinates)
        monitor_x = geometry.x
        monitor_y = geometry.y
        monitor_width = geometry.width
        monitor_height = geometry.height

        # Get window dimensions after layout is complete
        window_width = self.window.get_allocated_width()
        window_height = self.window.get_allocated_height()

        # Calculate X and Y positions based on the specified edge
        if self.config.get('north', True):
            # North edge: position at the top of the screen
            x = mouse_x - window_width // 2
            y = monitor_y
        elif self.config.get('south', False):
            # South edge: position at the bottom of the screen
            x = mouse_x - window_width // 2
            y = monitor_y + monitor_height - window_height
        elif self.config.get('east', False):
            # East edge: position at the right of the screen
            x = monitor_x + monitor_width - window_width
            y = mouse_y - window_height // 2
        elif self.config.get('west', False):
            # West edge: position at the left of the screen
            x = monitor_x
            y = mouse_y - window_height // 2

        # Ensure window stays fully on the current monitor
        monitor_left = monitor_x
        monitor_right = monitor_x + monitor_width
        monitor_top = monitor_y
        monitor_bottom = monitor_y + monitor_height

        if x < monitor_left:
            x = monitor_left
        elif x + window_width > monitor_right:
            x = monitor_right - window_width

        if y < monitor_top:
            y = monitor_top
        elif y + window_height > monitor_bottom:
            y = monitor_bottom - window_height

        # Move window to calculated position
        self.window.move(x, y)

        return False  # Don't repeat


    def hide_window(self):
        """Hide the window switcher with configurable delay"""
        # Check HIDE_STATE semaphore
        if not self.HIDE_STATE:
            logger.debug("hide_window: HIDE_STATE is False, not hiding")
            return

        if self.is_visible and self.window:
            if self.config['hide_delay'] > 0:
                # Use configurable delay
                GLib.timeout_add(self.config['hide_delay'], self._do_hide)
            else:
                # Hide immediately
                self._do_hide()

    def _do_hide(self):
        """Actually hide the window (called after delay if configured)"""
        # Check HIDE_STATE semaphore
        if not self.HIDE_STATE:
            logger.debug("_do_hide: HIDE_STATE is False, not hiding")
            return False

        if self.window:
            self.window.hide()
            self.is_visible = False
        return False  # Don't repeat

    def on_window_clicked(self, button, window):
        """Handle window selection"""
        try:
            # Validate window still exists before attempting to activate
            if not self.window_is_valid(window):
                logger.warning("Window is no longer valid, cannot activate")
                return

            # Activate the selected window
            timestamp = Gtk.get_current_event_time()
            try:
                window.activate(timestamp)
            except Exception as activate_error:
                logger.error(f"Failed to activate window: {activate_error}")
                # Check if this is Wnck corruption
                if "Wnck" in str(activate_error) or "ClassGroup" in str(activate_error):
                    logger.error("CRITICAL: Possible Wnck corruption during activate, flagging for recreation")
                    self.wnck_last_recreation = 0
                return  # Don't continue on activation failure

            # Record MRU timestamp if --recent flag is enabled
            if self.config.get('recent', False):
                try:
                    xid = window.get_xid()
                    if xid:  # Validate XID is not None
                        self.mru_timestamps[xid] = time.time()
                        logger.debug(f"Updated MRU timestamp for window XID {xid}")
                except Exception as e:
                    logger.debug(f"Error recording MRU timestamp: {e}")

            # Mark that a window was clicked - don't hide immediately
            # The window will be hidden when mouse leaves (respecting --delay)
            self.window_clicked = True
        except Exception as e:
            logger.error(f"Error in on_window_clicked handler: {e}")

    def grab_keyboard_focus(self):
        """Ensure window has keyboard focus"""
        if self.window and self.window.get_window():
            self.window.get_window().focus(Gtk.get_current_event_time())
            return False  # Don't repeat
        return False

    def on_scroll_event(self, widget, event):
        """Handle mouse wheel scrolling"""
        if not self.scroll_window:
            return False

        try:
            # Get current layout dimensions from flow box
            ncols = self.flow_box.get_max_children_per_line()
            window_count = len(self.window_buttons)
            nrows = max(1, (window_count + ncols - 1) // ncols)

            # Determine scroll direction based on calculated layout
            # If single row with multiple columns, scroll horizontally
            # Otherwise, scroll vertically
            if nrows == 1 and ncols > 1:
                # Horizontal scrolling for single row layout
                adjustment = self.scroll_window.get_hadjustment()
                if not adjustment:
                    return False

                current_value = adjustment.get_value()
                step_size = 100  # Larger step for horizontal scrolling

                if event.direction == Gdk.ScrollDirection.UP:
                    # Scroll left
                    new_value = max(adjustment.get_lower(), current_value - step_size)
                    adjustment.set_value(new_value)
                    return True
                elif event.direction == Gdk.ScrollDirection.DOWN:
                    # Scroll right
                    max_value = adjustment.get_upper() - adjustment.get_page_size()
                    new_value = min(max_value, current_value + step_size)
                    adjustment.set_value(new_value)
                    return True
                elif event.direction == Gdk.ScrollDirection.SMOOTH:
                    # Handle smooth scrolling (touchpad)
                    if hasattr(event, 'delta_y'):
                        delta = event.delta_y * 50  # Scale factor for horizontal scrolling
                        new_value = current_value + delta
                        new_value = max(adjustment.get_lower(),
                                      min(adjustment.get_upper() - adjustment.get_page_size(),
                                          new_value))
                        adjustment.set_value(new_value)
                        return True
            else:
                # Vertical scrolling for multi-row layout
                adjustment = self.scroll_window.get_vadjustment()
                if not adjustment:
                    return False

                current_value = adjustment.get_value()
                step_size = 50  # Scroll step size

                if event.direction == Gdk.ScrollDirection.UP:
                    new_value = max(adjustment.get_lower(), current_value - step_size)
                    adjustment.set_value(new_value)
                    return True
                elif event.direction == Gdk.ScrollDirection.DOWN:
                    max_value = adjustment.get_upper() - adjustment.get_page_size()
                    new_value = min(max_value, current_value + step_size)
                    adjustment.set_value(new_value)
                    return True
                elif event.direction == Gdk.ScrollDirection.SMOOTH:
                    # Handle smooth scrolling (touchpad)
                    if hasattr(event, 'delta_y'):
                        delta = event.delta_y * 30  # Scale factor for smooth scrolling
                        new_value = current_value + delta
                        new_value = max(adjustment.get_lower(),
                                      min(adjustment.get_upper() - adjustment.get_page_size(),
                                          new_value))
                        adjustment.set_value(new_value)
                        return True

        except Exception as e:
            logger.error(f"Error in scroll event: {e}")

        return False  # Event not handled

    def on_leave_notify(self, widget, event):
        """Handle mouse leaving the window"""
        # Only hide if mouse actually left the window area
        if event.detail != Gdk.NotifyType.INFERIOR:
            # If in middle-click mode, exit it and hide when mouse leaves
            if self._middle_click_mode:
                logger.debug("Mouse leaving during middle-click mode, exiting middle-click mode")
                self._middle_click_mode = False
                # Hide after leaving hotbox
                delay = max(300, self.config['hide_delay'])
                GLib.timeout_add(delay, self.delayed_hide)
            elif self.window_clicked:
                # Window was clicked - use the configured delay
                if self.config['hide_delay'] > 0:
                    GLib.timeout_add(self.config['hide_delay'], self._do_hide)
                else:
                    # No delay configured - hide immediately
                    self._do_hide()
                self.window_clicked = False  # Reset the flag
            else:
                # Normal mouse leave - use minimum delay to prevent flickering
                delay = max(300, self.config['hide_delay'])  # At least 300ms to prevent flickering
                GLib.timeout_add(delay, self.delayed_hide)
        return False

    def on_enter_notify(self, widget, event):
        """Handle mouse entering the window"""
        # Cancel any pending hide operation by clearing the timeout
        # The mouse is now inside the window, so we should stay visible
        # Also reset the clicked flag if mouse re-enters
        self.window_clicked = False
        return False

    def _redisplay_otter_after_workspace_switch(self):
        """Redisplay otter window after a workspace switch from middle-click"""
        try:
            if self.is_visible and self.window:
                # If otter is still visible, ensure it's on top
                self.window.present()
                logger.debug("Otter redisplayed after workspace switch")
            elif not self.is_visible and self.window:
                # If otter became hidden during workspace switch, show it again
                self.show_window()
                logger.info("Otter restored to visible after workspace switch")
        except Exception as e:
            logger.error(f"Error redisplaying otter after workspace switch: {e}")
        return False  # Don't repeat

    def delayed_hide(self):
        """Hide window after a delay if mouse is not over it"""
        # Check HIDE_STATE semaphore first
        if not self.HIDE_STATE:
            logger.debug("delayed_hide: HIDE_STATE is False, not hiding")
            return False

        if self.is_visible and self.window:
            try:
                # Check if mouse is still over the window
                display = Gdk.Display.get_default()
                seat = display.get_default_seat()
                pointer = seat.get_pointer()
                screen, x, y = pointer.get_position()

                if self.window.get_window():
                    window_x, window_y = self.window.get_position()
                    window_width = self.window.get_allocated_width()
                    window_height = self.window.get_allocated_height()

                    # Add a small buffer zone around the window to prevent premature hiding
                    buffer = 10

                    # Check if mouse is outside window bounds (with buffer)
                    if (x < window_x - buffer or x > window_x + window_width + buffer or
                        y < window_y - buffer or y > window_y + window_height + buffer):
                        self.hide_window()
            except Exception as e:
                logger.error(f"Error in delayed_hide: {e}")

        return False  # Don't repeat

    def on_window_changed(self, screen, window=None):
        """Handle window open/close events"""
        if self.is_visible:
            # Refresh the window list if switcher is visible
            # Use idle_add to avoid reentrancy issues with Wnck callbacks
            GLib.idle_add(self.populate_windows)

    def on_destroy(self, widget):
        """Handle window destruction"""
        self.cleanup()
        Gtk.main_quit()

    def on_button_press_event(self, button, event, window):
        """Handle button press events for context menu and middle-click"""
        if event.type == Gdk.EventType.BUTTON_PRESS:
            if event.button == 2:  # Middle-click
                # Enable middle-click mode to keep otter visible
                self._middle_click_mode = True
                self.window_clicked = False  # Prevents normal hide behavior on click
                self.on_switch_to_app_workspace(None, window)
                # Schedule otter to reappear if workspace switched
                # This ensures otter is visible on the new workspace
                GLib.timeout_add(200, self._redisplay_otter_after_workspace_switch)
                return True
            elif event.button == 3:  # Right-click
                self.show_context_menu(button, window)
                return True
        return False

    def show_context_menu(self, widget, window):
        """Show context menu for window operations"""
        menu = Gtk.Menu()

        # Set HIDE_STATE semaphore to False to prevent window from hiding while menu is open
        self.HIDE_STATE = False
        logger.debug("Context menu opened, HIDE_STATE set to False")

        # Connect to menu hide/destroy events to restore HIDE_STATE
        menu.connect("hide", self.on_context_menu_closed)
        menu.connect("destroy", self.on_context_menu_closed)

        # Create menu items
        move_to_display_item = Gtk.MenuItem(label="Move app to current display")
        resize_to_display_item = Gtk.MenuItem(label="Resize app to current display")
        minimize_item = Gtk.MenuItem(label="Minimize app")
        maximize_item = Gtk.MenuItem(label="Maximize app")
        switch_to_item = Gtk.MenuItem(label="Switch to app")
        switch_to_workspace_item = Gtk.MenuItem(label="Go to app's workspace")
        move_to_workspace_item = Gtk.MenuItem(label="Move to workspace")

        # Create submenu for workspaces
        workspace_submenu = Gtk.Menu()

        # Get available workspaces
        workspaces = self.screen_wnck.get_workspaces()
        for i, workspace in enumerate(workspaces):
            workspace_item = Gtk.MenuItem(label=f"Workspace {i + 1}")
            workspace_item.connect("activate", self.on_move_to_workspace, window, workspace)
            workspace_submenu.append(workspace_item)

        move_to_workspace_item.set_submenu(workspace_submenu)

        # Connect menu item signals
        move_to_display_item.connect("activate", self.on_move_to_display, window)
        resize_to_display_item.connect("activate", self.on_resize_to_display, window)
        minimize_item.connect("activate", self.on_minimize_app, window)
        maximize_item.connect("activate", self.on_maximize_app, window)
        switch_to_item.connect("activate", self.on_switch_to_app, window)
        switch_to_workspace_item.connect("activate", self.on_switch_to_app_workspace, window)

        # drag application
        drag_app_item = Gtk.MenuItem(label="Drag app")
        drag_app_item.connect("activate", self.on_drag_app, window)
        
        # Add menu items to menu
        menu.append(move_to_display_item)
        menu.append(resize_to_display_item)
        menu.append(minimize_item)
        menu.append(maximize_item)
        menu.append(switch_to_item)
        menu.append(switch_to_workspace_item)
        menu.append(move_to_workspace_item)
        menu.append(drag_app_item)

        # Show the menu
        menu.show_all()
        menu.popup_at_pointer(None)  # Show the menu at the current pointer position

    def on_context_menu_closed(self, menu):
        """Called when context menu is closed"""
        # Restore HIDE_STATE semaphore to True when menu closes
        self.HIDE_STATE = True
        logger.debug("Context menu closed, HIDE_STATE set to True")

    # Replace the on_move_to_display method:
    def on_move_to_display(self, menu_item, window):
        """Move app to current display and workspace."""
        try:
            # Get current workspace
            active_workspace = self.screen_wnck.get_active_workspace()
            
            # Move window to current workspace
            if active_workspace:
                window.move_to_workspace(active_workspace)

            # Get current display geometry
            display = Gdk.Display.get_default()
            seat = display.get_default_seat()
            pointer = seat.get_pointer()
            screen, x, y = pointer.get_position()
            monitor = display.get_monitor_at_point(x, y)
            geometry = monitor.get_geometry()

            # Use set_geometry instead of move()
            current_geom = window.get_geometry()
            window.set_geometry(
                Wnck.WindowGravity.CURRENT,
                Wnck.WindowMoveResizeMask.X | Wnck.WindowMoveResizeMask.Y,
                geometry.x + 50, geometry.y + 50,  # Offset from edge
                current_geom.width, current_geom.height
            )

        except Exception as e:
            logger.error(f"Error moving app to current display: {e}")
            

    # Fix 2: Fix WindowMoveResizeMask attribute error
    # Replace the on_resize_to_display method:
    def on_resize_to_display(self, menu_item, window):
        """Resize app to current display."""
        try:
            # Get current display geometry
            display = Gdk.Display.get_default()
            seat = display.get_default_seat()
            pointer = seat.get_pointer()
            screen, x, y = pointer.get_position()
            monitor = display.get_monitor_at_point(x, y)
            geometry = monitor.get_geometry()

            # Use proper Wnck constants
            window.set_geometry(
                Wnck.WindowGravity.CURRENT,
                Wnck.WindowMoveResizeMask.X | Wnck.WindowMoveResizeMask.Y | 
                Wnck.WindowMoveResizeMask.WIDTH | Wnck.WindowMoveResizeMask.HEIGHT,
                geometry.x, geometry.y,
                geometry.width, geometry.height
            )

        except Exception as e:
            logger.error(f"Error resizing app to current display: {e}")

    def on_minimize_app(self, menu_item, window):
        """Minimize the application"""
        try:
            window.minimize()
        except Exception as e:
            logger.error(f"Error minimizing app: {e}")

    def on_maximize_app(self, menu_item, window):
        """Maximize the application"""
        try:
            if window.is_maximized():
                window.unmaximize()
            else:
                window.maximize()
        except Exception as e:
            logger.error(f"Error maximizing app: {e}")

    def on_switch_to_app(self, menu_item, window):
        """Switch to the application's workspace and display"""
        try:
            # Activate the window's workspace
            try:
                workspace = window.get_workspace()
                if workspace:
                    workspace.activate(Gtk.get_current_event_time())
            except Exception as workspace_error:
                logger.error(f"SEGFAULT RISK: get_workspace()/activate() failed: {workspace_error}")

            # Activate the window
            try:
                window.activate(Gtk.get_current_event_time())
            except Exception as activate_error:
                logger.error(f"SEGFAULT RISK: window.activate() in on_switch_to_app failed: {activate_error}")
                raise

            # Record MRU timestamp if --recent flag is enabled
            if self.config.get('recent', False):
                try:
                    xid = window.get_xid()
                    self.mru_timestamps[xid] = time.time()
                    logger.debug(f"Updated MRU timestamp for window XID {xid}")
                except Exception as e:
                    logger.debug(f"Error recording MRU timestamp: {e}")

        except Exception as e:
            logger.error(f"Error switching to app: {e}")

    def on_switch_to_app_workspace(self, menu_item, window):
        """Middle-click handler: if app is in current workspace, activate it; otherwise switch workspaces"""
        try:
            # Validate window still exists
            if not self.window_is_valid(window):
                logger.warning("Window is no longer valid, cannot process middle-click")
                return

            # Get the window's workspace
            try:
                window_workspace = window.get_workspace()
                if not window_workspace:
                    logger.warning("Window has no workspace")
                    return
            except Exception as workspace_error:
                logger.error(f"Failed to get window workspace: {workspace_error}")
                return

            # Get the current active workspace
            try:
                current_workspace = self.screen_wnck.get_active_workspace()
            except Exception as e:
                logger.error(f"Could not get active workspace: {e}")
                current_workspace = None

            try:
                window_name = window.get_name()
            except Exception as e:
                logger.debug(f"Could not get window name: {e}")
                window_name = "Unknown"

            # Check if the window is already in the current workspace
            if current_workspace and window_workspace == current_workspace:
                # Window is already on current workspace - just activate it
                try:
                    window.activate(Gtk.get_current_event_time())
                    logger.info(f"Window '{window_name}' is already on current workspace - brought to front")
                except Exception as activate_error:
                    logger.error(f"Failed to activate window: {activate_error}")
            else:
                # Window is on a different workspace - switch to that workspace
                try:
                    window_workspace.activate(Gtk.get_current_event_time())
                    logger.info(f"Switched to workspace containing '{window_name}'")
                except Exception as workspace_activate_error:
                    logger.error(f"Failed to activate workspace: {workspace_activate_error}")

            # Record MRU timestamp if --recent flag is enabled
            if self.config.get('recent', False):
                try:
                    xid = window.get_xid()
                    if xid:
                        self.mru_timestamps[xid] = time.time()
                        logger.debug(f"Updated MRU timestamp for window XID {xid} (workspace switch)")
                except Exception as e:
                    logger.debug(f"Could not update MRU timestamp: {e}")

        except Exception as e:
            logger.error(f"Error in middle-click handler: {e}")

    def on_move_to_workspace(self, menu_item, window, workspace):
        """Move the application to the specified workspace"""
        try:
            window.move_to_workspace(workspace)
        except Exception as e:
            logger.error(f"SEGFAULT RISK: move_to_workspace() failed: {e}")
            if "Wnck" in str(e) or "ClassGroup" in str(e):
                logger.error("CRITICAL: Possible Wnck corruption during move_to_workspace")
                self.wnck_last_recreation = 0


    def on_drag_app(self, menu_item, window):
        """Start drag mode - warp cursor to title bar and initiate move"""
        try:
            # Get window geometry (returns tuple: x, y, width, height)
            x, y, width, height = window.get_geometry()

            # Calculate title bar center position (top center of window)
            title_bar_x = x + width // 2
            title_bar_y = y + 15  # Approximate title bar height

            logger.info(f"Starting drag mode for window '{window.get_name()}'")
            logger.info(f"Warping cursor to title bar at ({title_bar_x}, {title_bar_y})")

            # Get Gdk display and device
            gdk_display = Gdk.Display.get_default()
            seat = gdk_display.get_default_seat()
            pointer = seat.get_pointer()

            # Warp pointer using Gdk (proven to work reliably)
            screen = gdk_display.get_default_screen()
            pointer.warp(screen, title_bar_x, title_bar_y)

            logger.info(f"Cursor warped to ({title_bar_x}, {title_bar_y})")

            # Activate window first
            window.activate(Gtk.get_current_event_time())
            logger.info("Window activated")

            # Initiate interactive move mode using Wnck keyboard_move
            try:
                window.keyboard_move()
                logger.info("Window move mode activated - move mouse to reposition, click or press Enter to place")
            except Exception as e:
                logger.warning(f"keyboard_move() failed: {e}")
                logger.info("Fallback: Window is active. Try Alt+F7 to move, or use your window manager's move hotkey")

        except Exception as e:
            logger.error(f"Error in drag mode: {e}")



    def cleanup(self):
        """Clean up resources thoroughly."""
        logger.info("Cleaning up resources...")

        # Remove all GLib timeout handlers
        if self.monitor_id:
            try:
                GLib.source_remove(self.monitor_id)
            except Exception as e:
                logger.debug(f"Error removing monitor: {e}")
            self.monitor_id = None

        if self.screenshot_monitor_id:
            try:
                GLib.source_remove(self.screenshot_monitor_id)
            except Exception as e:
                logger.debug(f"Error removing screenshot monitor: {e}")
            self.screenshot_monitor_id = None

        if self.delayed_hide_id:
            try:
                GLib.source_remove(self.delayed_hide_id)
            except Exception as e:
                logger.debug(f"Error removing delayed hide: {e}")
            self.delayed_hide_id = None

        # Disconnect all signals
        if self.drag_signal_id and self.window:
            try:
                self.window.disconnect(self.drag_signal_id)
            except Exception as e:
                logger.debug(f"Error disconnecting drag signal: {e}")
            self.drag_signal_id = None

        # Clear window references
        self.drag_active = False
        self.drag_window = None

        # Clear caches and release Pixbuf references
        try:
            self.screenshot_cache.clear()
        except Exception as e:
            logger.debug(f"Error clearing screenshot cache: {e}")

        try:
            if hasattr(self, 'last_valid_screenshots'):
                self.last_valid_screenshots.clear()
        except Exception as e:
            logger.debug(f"Error clearing valid screenshots: {e}")

        try:
            if hasattr(self, 'window_buttons'):
                self.window_buttons.clear()
        except Exception as e:
            logger.debug(f"Error clearing window buttons: {e}")

        logger.info("Cleanup complete")

    def run(self):
        """Run the application"""
        try:
            Gtk.main()
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down...")
            self.cleanup()
            sys.exit(0)
        


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Otter Window Switcher - A mouse-activated window switcher for Ubuntu Cinnamon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
%(prog)s                           # Use default settings (4 columns, auto rows)
%(prog)s --ncols 5                 # 5 columns, auto rows
%(prog)s --nrows 2                 # 2 rows, auto columns
%(prog)s --xsize 200               # Larger thumbnails (200px width)
%(prog)s --ncols 6 --xsize 120     # 6 columns, smaller thumbnails
        """)

    # Create mutually exclusive group for rows/columns
    layout_group = parser.add_mutually_exclusive_group()
    layout_group.add_argument('--nrows', type=int, metavar='NUM',
                            help='Number of rows of application thumbnails (auto-calculates columns)')
    layout_group.add_argument('--ncols', type=int, default=4, metavar='NUM',
                            help='Number of columns of application thumbnails (auto-calculates rows, default: 4)')

    parser.add_argument('--xsize', type=int, default=160, metavar='PIXELS',
                        help='Width in pixels for application thumbnails (height auto-calculated, default: 160)')

    parser.add_argument('--notitle', action='store_true',
                        help='Disable the fancy title bar to save screen space')

    parser.add_argument('--delay', type=int, default=0, metavar='MILLISECONDS',
                        help='Delay in milliseconds before hiding the window (default: 0)')

    parser.add_argument('--recent', action='store_true',
                        help='Order thumbnails by most recently used (MRU), with recently selected windows appearing first')

    parser.add_argument('--main-character', action='store_true',
                        help='Disable edge trigger when a fullscreen app is active (prevents interrupting games/videos)')

    # Add mutually exclusive group for screen edges
    edge_group = parser.add_mutually_exclusive_group()
    edge_group.add_argument('--north', action='store_true',
                        help='Trigger window switcher at the north edge of the screen (default)')
    edge_group.add_argument('--south', action='store_true',
                        help='Trigger window switcher at the south edge of the screen')
    edge_group.add_argument('--east', action='store_true',
                        help='Trigger window switcher at the east edge of the screen')
    edge_group.add_argument('--west', action='store_true',
                        help='Trigger window switcher at the west edge of the screen')

    args = parser.parse_args()

    # Set default to north if no edge is specified
    if not any([args.north, args.south, args.east, args.west]):
        args.north = True

    # Validate arguments
    if args.nrows is not None and args.nrows < 1:
        parser.error("--nrows must be at least 1")
    if args.ncols < 1:
        parser.error("--ncols must be at least 1")
    if args.xsize < 50:
        parser.error("--xsize must be at least 50 pixels")
    if args.xsize > 500:
        parser.error("--xsize should not exceed 500 pixels for usability")

    if args.delay < 0:
        parser.error("--delay must be non-negative")
    if args.delay > 10000:
        parser.error("--delay should not exceed 10000 milliseconds (10 seconds)")

    return args



def main():
    """Main entry point"""
    # Parse command line arguments
    args = parse_arguments()

    logger.info("Starting Otter Window Switcher...")

    # Show configuration based on what was specified
    if args.nrows is not None:
        logger.info(f"Configuration: {args.nrows} rows (auto-calculated columns), {args.xsize}px width")
    else:
        logger.info(f"Configuration: {args.ncols} columns (auto-calculated rows), {args.xsize}px width")

    if args.notitle:
        logger.info("Title bar: Disabled (--notitle)")
    else:
        logger.info("Title bar: Enabled")

    if args.delay > 0:
        logger.info(f"Hide delay: {args.delay}ms")
    else:
        logger.info("Hide delay: Immediate (0ms)")

    logger.info(f"Edge trigger: {'North' if args.north else 'South' if args.south else 'East' if args.east else 'West'}")

    # Handle signals for clean shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        Gtk.main_quit()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create and run the application with configuration
    try:
        app = OtterWindowSwitcher(args)
        app.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
