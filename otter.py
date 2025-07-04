#!/usr/bin/python3
#!/usr/bin/env python3
"""
Otter - X11 Window Switcher for Ubuntu Cinnamon Desktop
A background application that shows active windows when mouse cursor is moved to y=0
"""

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Wnck", "3.0")

from gi.repository import Gtk, Gdk, Wnck, GLib
try:
    from gi.repository import GdkX11
except ImportError:
    GdkX11 = None
import subprocess
import os
import signal
import sys
import argparse
from typing import List, Dict, Optional

class OtterWindowSwitcher:
    def __init__(self, args=None):
        """Initialize the window switcher"""
        # Parse arguments and set up configuration
        if args:
            self.config = {
                'nrows': args.nrows,
                'ncols': args.ncols,
                'xsize': args.xsize,
                'show_title': not args.notitle,
                'hide_delay': args.delay
            }
        else:
            self.config = self.get_default_config()
        
        # Initialize GTK and Wnck
        Gtk.init()
        self.screen_wnck = Wnck.Screen.get_default()
        self.screen_wnck.force_update()
        
        # Window state
        self.window = None
        self.is_visible = False
        self.window_clicked = False
        
        # Screenshot cache
        self.screenshot_cache = {}
        self.window_buttons = []
        
        # Monitoring IDs
        self.monitor_id = None
        self.screenshot_monitor_id = None
        
        # Cache update interval
        self.cache_update_interval = 2000  # 2 seconds
        
        # Set up the window
        self.create_window()
        
        # Set up monitoring
        self.setup_mouse_monitoring()
        self.setup_screenshot_caching()
        
        # Connect to window changes
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
        }
        
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
        """Check if mouse cursor is at y=0 and show/hide window accordingly"""
        try:
            # Get current mouse position
            display = Gdk.Display.get_default()
            seat = display.get_default_seat()
            pointer = seat.get_pointer()
            screen, x, y = pointer.get_position()
            
            # Only check for y=0 trigger when window is NOT visible
            if not self.is_visible:
                # Check if mouse is at top of screen (y=0)
                if y <= 5:  # Small tolerance for easier triggering
                    self.show_window()
            else:
                # Window is visible - only check for hide conditions
                if y > 100 and not self.mouse_in_window():  # Hide when mouse moves away from top AND not in window
                    self.hide_window()
                
        except Exception as e:
            print(f"Error checking mouse position: {e}")
            
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
            print(f"Error checking mouse in window: {e}")
            return False
        
    def update_screenshot_cache(self):
        """Update screenshot cache for all visible windows"""
        try:
            current_windows = self.get_user_windows()
            
            # Clean up cache for windows that no longer exist
            existing_window_ids = {self.get_window_id(w['window']) for w in current_windows}
            cached_window_ids = set(self.screenshot_cache.keys())
            
            for window_id in cached_window_ids - existing_window_ids:
                del self.screenshot_cache[window_id]
            
            # Update screenshots for current windows
            for window_info in current_windows:
                window = window_info['window']
                window_id = self.get_window_id(window)
                
                # Capture screenshot
                screenshot = self.capture_high_quality_screenshot(window)
                if screenshot:
                    self.screenshot_cache[window_id] = screenshot
                    
        except Exception as e:
            print(f"Error updating screenshot cache: {e}")
            
        return True  # Continue periodic updates
    
    def get_window_id(self, window):
        """Get a unique identifier for a window"""
        try:
            return window.get_xid()
        except:
            # Fallback to window name + pid if XID not available
            app = window.get_application()
            pid = app.get_pid() if app else 0
            return f"{window.get_name()}_{pid}"
    
    def capture_high_quality_screenshot(self, window):
        """Capture a high-quality screenshot of a window"""
        try:
            # Method 1: Try to get the window's own GDK window for isolated capture
            isolated_pixbuf = self.capture_isolated_window(window)
            if isolated_pixbuf:
                return self.scale_pixbuf_high_quality(isolated_pixbuf)
            
            # Method 2: Try to temporarily raise the window and capture it
            raised_pixbuf = self.capture_with_temporary_raise(window)
            if raised_pixbuf:
                return self.scale_pixbuf_high_quality(raised_pixbuf)
            
            # Method 3: Fallback to regular screen capture (with overlaps)
            return self.capture_screen_area(window)
            
        except Exception as e:
            print(f"Error capturing high-quality screenshot: {e}")
            return None
    
    def capture_isolated_window(self, window):
        """Try to capture the window content directly without overlaps"""
        try:
            # Check if GdkX11 is available
            if not GdkX11:
                return None
                
            # Get the X11 window ID
            xid = window.get_xid()
            if not xid:
                return None
            
            # Get the GDK window from XID
            display = Gdk.Display.get_default()
            gdk_window = GdkX11.X11Window.foreign_new_for_display(display, xid)
            
            if gdk_window and gdk_window.is_viewable():
                # Get window dimensions
                width = gdk_window.get_width()
                height = gdk_window.get_height()
                
                if width > 0 and height > 0:
                    # Capture directly from the window
                    pixbuf = Gdk.pixbuf_get_from_window(gdk_window, 0, 0, width, height)
                    return pixbuf
                    
        except Exception as e:
            print(f"Error in isolated capture: {e}")
            
        return None
    
    def capture_with_temporary_raise(self, window):
        """Temporarily raise window to top, capture it, then restore"""
        try:
            # Check if window is minimized
            if window.is_minimized():
                return None
            
            # Store current active window
            active_window = self.screen_wnck.get_active_window()
            
            # Temporarily activate the target window
            timestamp = Gtk.get_current_event_time()
            window.activate(timestamp)
            
            # Small delay to ensure window is raised
            import time
            time.sleep(0.1)
            
            # Capture the window area
            geometry = window.get_geometry()
            x, y, width, height = geometry
            
            if width > 0 and height > 0:
                root_window = Gdk.get_default_root_window()
                pixbuf = Gdk.pixbuf_get_from_window(root_window, x, y, width, height)
                
                # Restore the previously active window
                if active_window and active_window != window:
                    active_window.activate(timestamp + 1)
                
                return pixbuf
                
        except Exception as e:
            print(f"Error in temporary raise capture: {e}")
            
        return None
    
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
            print(f"Error in screen area capture: {e}")
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
                
                # Use high-quality scaling
                scaled_pixbuf = pixbuf.scale_simple(new_width, new_height, 3)  # GdkPixbuf.InterpType.HYPER
                return scaled_pixbuf
                
        except Exception as e:
            print(f"Error scaling pixbuf: {e}")
            
        return None
        
    def create_window(self):
        """Create the main application window"""
        self.window = Gtk.Window()
        self.window.set_title("🦦 Otter App Switcher")
        self.window.set_decorated(False)  # No window decorations
        self.window.set_keep_above(True)  # Keep window on top
        self.window.set_skip_taskbar_hint(True)  # Don't show in taskbar
        self.window.set_skip_pager_hint(True)  # Don't show in pager
        
        # Set window type hint for proper behavior
        self.window.set_type_hint(Gdk.WindowTypeHint.DOCK)
        
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
        
        # Style the window with dark theme
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
        window {
            background-color: rgba(46, 52, 64, 0.95);
            border-radius: 10px;
            border: 2px solid rgba(129, 161, 193, 0.8);
        }
        .title-bar {
            background: linear-gradient(135deg, rgba(129, 161, 193, 0.3), rgba(88, 166, 255, 0.2));
            border-radius: 8px;
            padding: 8px;
            margin-bottom: 10px;
            border: 1px solid rgba(129, 161, 193, 0.5);
        }
        .window-button {
            background-color: rgba(67, 76, 94, 0.8);
            border-radius: 8px;
            border: 1px solid rgba(129, 161, 193, 0.5);
            padding: 8px;
            margin: 4px;
        }
        .window-button:hover {
            background-color: rgba(129, 161, 193, 0.3);
            border: 1px solid rgba(129, 161, 193, 0.8);
        }
        label {
            color: #eceff4;
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
            # Remove fixed width constraint for single row to allow proper horizontal scrolling
        else:
            # Multi-row layout: enable vertical scrolling, disable horizontal
            self.scroll_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            self.scroll_window.set_min_content_height(200)
            self.scroll_window.set_max_content_height(400)
            # Remove fixed width constraint to allow proper column display
        
        # Create flow box for window thumbnails
        self.flow_box = Gtk.FlowBox()
        self.flow_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flow_box.set_homogeneous(False)
        # Note: min/max children per line will be set dynamically in populate_windows()
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
        """Get list of user windows, filtering out system applications"""
        windows = []
        
        # Get all windows from Wnck
        for window in self.screen_wnck.get_windows():
            # Only include normal windows that are not minimized
            if (window.get_window_type() == Wnck.WindowType.NORMAL and
                not window.is_minimized() and
                window.is_visible_on_workspace(self.screen_wnck.get_active_workspace())):
                
                # Additional filtering for system applications
                app_name = window.get_application().get_name() if window.get_application() else ""
                window_name = window.get_name()
                
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
                    
                    windows.append({
                        'window': window,
                        'name': window_name,
                        'app_name': app_name,
                        'icon': window.get_icon() if window.get_icon() else None
                    })
        
        return windows
        
    def create_window_thumbnail(self, window_info: Dict) -> Gtk.Widget:
        """Create a thumbnail button for a window"""
        window = window_info['window']
        name = window_info['name']
        app_name = window_info['app_name']
        icon = window_info['icon']
        
        # Create main button
        button = Gtk.Button()
        button.get_style_context().add_class("window-button")
        button.set_relief(Gtk.ReliefStyle.NONE)
        
        # Create vertical box for content
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        
        # Try to get window screenshot/thumbnail
        thumbnail = self.get_window_thumbnail(window)
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
            print(f"Error creating thumbnail: {e}")
            return self.create_fallback_thumbnail(window)
    
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
            print(f"Error capturing window screenshot: {e}")
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
        # Clear existing buttons
        for child in self.flow_box.get_children():
            self.flow_box.remove(child)
        
        self.window_buttons.clear()
        
        # Get user windows
        self.windows_list = self.get_user_windows()
        
        if not self.windows_list:
            # Show message if no windows found
            label = Gtk.Label()
            label.set_markup("<span size='large'>No active windows found</span>")
            label.set_halign(Gtk.Align.CENTER)
            self.flow_box.add(label)
        else:
            # Calculate dynamic dimensions based on window count
            window_count = len(self.windows_list)
            nrows, ncols = self.calculate_layout_dimensions(window_count)
            
            # Update flow box configuration with calculated dimensions
            self.flow_box.set_min_children_per_line(ncols)
            self.flow_box.set_max_children_per_line(ncols)
            
            # Update scroll window configuration based on layout
            if nrows == 1 and ncols > 1:
                # Single row layout: enable horizontal scrolling, disable vertical
                self.scroll_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
                
                # Calculate required width for all columns
                thumbnail_width = self.config['xsize']
                spacing = 10  # column spacing
                margin = 30   # window margins
                required_width = ncols * thumbnail_width + (ncols - 1) * spacing + margin
                
                # Set minimum width to ensure all columns are visible
                self.scroll_window.set_min_content_width(required_width)
                
                # Also set the main window to be wide enough
                self.window.set_default_size(required_width + 100, -1)  # +100 for window decorations
            else:
                # Multi-row layout: enable vertical scrolling, disable horizontal
                self.scroll_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            
            # Create thumbnail buttons for each window
            for window_info in self.windows_list:
                thumbnail = self.create_window_thumbnail(window_info)
                self.window_buttons.append(thumbnail)
                self.flow_box.add(thumbnail)
        
        self.flow_box.show_all()
        
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
        
        # Calculate X position near mouse cursor, ensuring full visibility on current monitor
        # Try to center window under cursor, but adjust if too close to monitor edges
        preferred_x = mouse_x - window_width // 2
        
        # Ensure window stays fully on the current monitor
        monitor_left = monitor_x
        monitor_right = monitor_x + monitor_width
        
        if preferred_x < monitor_left:
            # Too close to left edge of monitor, align to left
            x = monitor_left
        elif preferred_x + window_width > monitor_right:
            # Too close to right edge of monitor, align to right
            x = monitor_right - window_width
        else:
            # Centered position works within monitor bounds
            x = preferred_x
        
        # Y position: appear flush with the top edge of the current monitor
        monitor_top = monitor_y
        monitor_bottom = monitor_y + monitor_height
        y = monitor_top  # Position flush with top edge
        
        # Move window to calculated position
        self.window.move(x, y)
        
        return False  # Don't repeat
        
    def hide_window(self):
        """Hide the window switcher with configurable delay"""
        if self.is_visible and self.window:
            if self.config['hide_delay'] > 0:
                # Use configurable delay
                GLib.timeout_add(self.config['hide_delay'], self._do_hide)
            else:
                # Hide immediately
                self._do_hide()
    
    def _do_hide(self):
        """Actually hide the window (called after delay if configured)"""
        if self.window:
            self.window.hide()
            self.is_visible = False
        return False  # Don't repeat
        
    def on_window_clicked(self, button, window):
        """Handle window selection"""
        try:
            # Activate the selected window
            timestamp = Gtk.get_current_event_time()
            window.activate(timestamp)
            
            # Mark that a window was clicked - don't hide immediately
            # The window will be hidden when mouse leaves (respecting --delay)
            self.window_clicked = True
        except Exception as e:
            print(f"Error activating window: {e}")
            
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
            print(f"Error in scroll event: {e}")
            
        return False  # Event not handled
        
    def on_leave_notify(self, widget, event):
        """Handle mouse leaving the window"""
        # Only hide if mouse actually left the window area
        if event.detail != Gdk.NotifyType.INFERIOR:
            if self.window_clicked:
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
        
    def delayed_hide(self):
        """Hide window after a delay if mouse is not over it"""
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
                print(f"Error in delayed_hide: {e}")
        
        return False  # Don't repeat
        
    def on_window_changed(self, screen, window=None):
        """Handle window open/close events"""
        if self.is_visible:
            # Refresh the window list if switcher is visible
            self.populate_windows()
            
    def on_destroy(self, widget):
        """Handle window destruction"""
        self.cleanup()
        Gtk.main_quit()
        
    def cleanup(self):
        """Clean up resources"""
        if self.monitor_id:
            GLib.source_remove(self.monitor_id)
            self.monitor_id = None
            
        if self.screenshot_monitor_id:
            GLib.source_remove(self.screenshot_monitor_id)
            self.screenshot_monitor_id = None
            
        # Clear screenshot cache
        self.screenshot_cache.clear()
            
    def run(self):
        """Run the application"""
        try:
            Gtk.main()
        except KeyboardInterrupt:
            print("\nReceived interrupt signal, shutting down...")
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
    
    args = parser.parse_args()
    
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
    
    print(f"Starting Otter Window Switcher...")
    
    # Show configuration based on what was specified
    if args.nrows is not None:
        print(f"Configuration: {args.nrows} rows (auto-calculated columns), {args.xsize}px width")
    else:
        print(f"Configuration: {args.ncols} columns (auto-calculated rows), {args.xsize}px width")
    
    if args.notitle:
        print("Title bar: Disabled (--notitle)")
    else:
        print("Title bar: Enabled (fancy title bar with otter emoji)")
    
    if args.delay > 0:
        print(f"Hide delay: {args.delay}ms")
    else:
        print("Hide delay: Immediate (0ms)")
    
    # Handle signals for clean shutdown
    def signal_handler(signum, frame):
        print(f"\nReceived signal {signum}, shutting down...")
        Gtk.main_quit()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and run the application with configuration
    app = OtterWindowSwitcher(args)
    app.run()

if __name__ == "__main__":
    main() 