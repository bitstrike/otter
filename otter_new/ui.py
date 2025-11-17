"""UI components: window, thumbnails, context menu, splash, styles"""

import logging
from typing import Dict, List, Optional
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

from .constants import WORKSPACE_COLORS
from .geometry import get_pointer_position, get_monitor_at_point, get_monitor_geometry, position_window_at_edge, calculate_layout_dimensions

logger = logging.getLogger(__name__)


def get_css_styles() -> str:
    """Get CSS styles for the application
    
    Returns:
        CSS string
    """
    return """
    window {
        background-color: @theme_bg_color;
        border: 1px solid @borders;
        border-radius: 8px;
    }
    
    .window-button {
        background-color: @theme_bg_color;
        border: 2px solid @borders;
        border-radius: 6px;
        padding: 8px;
        margin: 4px;
    }
    
    .window-button:hover {
        background-color: @theme_selected_bg_color;
        border-color: @theme_selected_bg_color;
    }
    
    .minimized-window-button {
        opacity: 0.6;
    }
    
    .title-bar {
        background-color: @theme_bg_color;
        border-bottom: 1px solid @borders;
        padding: 10px;
    }
    
    .workspace-badge {
        border-radius: 4px;
        padding: 2px 6px;
        font-size: 10px;
        font-weight: bold;
        color: white;
    }
    """


class SwitcherWindow:
    """Main switcher window"""
    
    def __init__(self, config: Dict, window_manager, screenshot_manager, event_handler):
        """Initialize switcher window
        
        Args:
            config: Configuration dictionary
            window_manager: WindowManager instance
            screenshot_manager: ScreenshotManager instance
            event_handler: EventHandler instance
        """
        self.config = config
        self.window_manager = window_manager
        self.screenshot_manager = screenshot_manager
        self.event_handler = event_handler
        
        self.window = None
        self.scroll_window = None
        self.grid = None
        self.window_buttons = []
        
        self._create_window()
        self._apply_styles()
    
    def _create_window(self):
        """Create the main window"""
        self.window = Gtk.Window()
        self.window.set_title("Otter Window Switcher")
        self.window.set_decorated(False)
        self.window.set_keep_above(True)
        self.window.set_skip_taskbar_hint(True)
        self.window.set_skip_pager_hint(True)
        # Use UTILITY instead of DOCK to allow keyboard focus
        self.window.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.window.set_accept_focus(True)
        self.window.set_can_focus(True)
        
        # Main container
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        # Title bar (optional)
        if self.config.get('show_title', True):
            title_bar = self._create_title_bar()
            main_vbox.pack_start(title_bar, False, False, 0)
        
        # Scrolled window for thumbnails
        self.scroll_window = Gtk.ScrolledWindow()
        self.scroll_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll_window.set_min_content_height(200)
        self.scroll_window.set_max_content_height(800)
        
        # Grid for thumbnails
        self.grid = Gtk.Grid()
        self.grid.set_row_spacing(8)
        self.grid.set_column_spacing(8)
        self.grid.set_margin_top(10)
        self.grid.set_margin_bottom(10)
        self.grid.set_margin_start(10)
        self.grid.set_margin_end(10)
        
        self.scroll_window.add(self.grid)
        main_vbox.pack_start(self.scroll_window, True, True, 0)
        
        self.window.add(main_vbox)
        
        # Connect events
        self.window.connect("destroy", self.event_handler.on_destroy)
        self.window.connect("enter-notify-event", self.event_handler.on_enter_notify)
        self.window.connect("leave-notify-event", self.event_handler.on_leave_notify)
        self.scroll_window.connect("scroll-event", self.event_handler.on_scroll)
    
    def _create_title_bar(self) -> Gtk.Widget:
        """Create title bar
        
        Returns:
            Title bar widget
        """
        title_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        title_bar.get_style_context().add_class("title-bar")
        title_bar.set_margin_top(10)
        title_bar.set_margin_bottom(10)
        title_bar.set_margin_start(10)
        title_bar.set_margin_end(10)
        
        # Icon (if available)
        try:
            icon = Gtk.Image.new_from_icon_name("preferences-system-windows", Gtk.IconSize.LARGE_TOOLBAR)
            title_bar.pack_start(icon, False, False, 0)
        except Exception:
            pass
        
        # Title
        title_label = Gtk.Label()
        title_label.set_markup("<b>Window Switcher</b>")
        title_bar.pack_start(title_label, False, False, 0)
        
        return title_bar
    
    def _apply_styles(self):
        """Apply CSS styles"""
        try:
            css_provider = Gtk.CssProvider()
            css_provider.load_from_data(get_css_styles().encode())
            
            screen = Gdk.Screen.get_default()
            style_context = Gtk.StyleContext()
            style_context.add_provider_for_screen(
                screen,
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        except Exception as e:
            logger.error(f"Error applying styles: {e}")
    
    def populate(self, windows: List[Dict]):
        """Populate window with thumbnails
        
        Args:
            windows: List of window info dictionaries
        """
        # Clear existing buttons
        for button in self.window_buttons:
            button.destroy()
        self.window_buttons.clear()
        
        if not windows:
            logger.debug("No windows to display")
            return
        
        # Calculate layout
        rows, cols = calculate_layout_dimensions(
            len(windows),
            self.config.get('nrows'),
            self.config.get('ncols', 4)
        )
        
        # Create thumbnails
        for idx, window_info in enumerate(windows):
            row = idx // cols
            col = idx % cols
            
            button = self._create_thumbnail_button(window_info)
            if button:
                self.grid.attach(button, col, row, 1, 1)
                self.window_buttons.append(button)
        
        # Show all new widgets
        self.grid.show_all()
    
    def _create_thumbnail_button(self, window_info: Dict) -> Optional[Gtk.Widget]:
        """Create thumbnail button for window
        
        Args:
            window_info: Window information dictionary
            
        Returns:
            Button widget or None
        """
        try:
            xid = window_info.get('xid')
            if not xid:
                return None
            
            name = window_info.get('name', 'Unknown')
            is_minimized = window_info.get('is_minimized', False)
            workspace_index = window_info.get('workspace_index')
            
            # Create button
            button = Gtk.Button()
            button.get_style_context().add_class("window-button")
            if is_minimized:
                button.get_style_context().add_class("minimized-window-button")
            button.set_relief(Gtk.ReliefStyle.NONE)
            
            # Create content box
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            
            # Get thumbnail
            thumbnail = self._create_thumbnail(window_info)
            if thumbnail:
                # Overlay for workspace badge
                overlay = Gtk.Overlay()
                overlay.add(thumbnail)
                
                # Add workspace badge if available
                if workspace_index:
                    badge = self._create_workspace_badge(workspace_index)
                    if badge:
                        overlay.add_overlay(badge)
                        overlay.set_overlay_pass_through(badge, True)
                
                vbox.pack_start(overlay, False, False, 0)
            
            # Window name label
            label = Gtk.Label()
            label.set_text(name)
            label.set_max_width_chars(20)
            label.set_ellipsize(3)  # ELLIPSIZE_END
            vbox.pack_start(label, False, False, 0)
            
            button.add(vbox)
            
            # Connect events
            button.connect("clicked", self.event_handler.on_window_clicked, xid)
            button.connect("button-press-event", self.event_handler.on_button_press, xid)
            
            return button
        
        except Exception as e:
            logger.error(f"Error creating thumbnail button: {e}")
            return None
    
    def _create_thumbnail(self, window_info: Dict) -> Optional[Gtk.Widget]:
        """Create thumbnail image
        
        Args:
            window_info: Window information dictionary
            
        Returns:
            Image widget or None
        """
        try:
            xid = window_info.get('xid')
            if not xid:
                return None
            
            # Try to get screenshot from cache
            screenshot = self.screenshot_manager.screenshot_cache.get(xid)
            
            if screenshot:
                image = Gtk.Image.new_from_pixbuf(screenshot)
                return image
            
            # Fallback to icon
            icon = window_info.get('icon')
            if icon:
                # Scale icon to thumbnail size
                width = self.config.get('xsize', 160)
                height = int(width * 0.75)
                
                scaled_icon = icon.scale_simple(
                    min(width, icon.get_width()),
                    min(height, icon.get_height()),
                    GdkPixbuf.InterpType.BILINEAR
                )
                
                image = Gtk.Image.new_from_pixbuf(scaled_icon)
                return image
            
            # Final fallback: generic icon
            image = Gtk.Image.new_from_icon_name(
                "application-x-executable",
                Gtk.IconSize.DIALOG
            )
            return image
        
        except Exception as e:
            logger.debug(f"Error creating thumbnail: {e}")
            return None
    
    def _create_workspace_badge(self, workspace_index: int) -> Optional[Gtk.Widget]:
        """Create workspace badge
        
        Args:
            workspace_index: Workspace number (1-indexed)
            
        Returns:
            Badge widget or None
        """
        try:
            # Get color for workspace
            color_index = (workspace_index - 1) % len(WORKSPACE_COLORS)
            color = WORKSPACE_COLORS[color_index]
            
            # Create label
            label = Gtk.Label()
            label.set_text(str(workspace_index))
            label.get_style_context().add_class("workspace-badge")
            label.set_halign(Gtk.Align.END)
            label.set_valign(Gtk.Align.START)
            label.set_margin_top(5)
            label.set_margin_end(5)
            
            # Apply color
            css = f"""
            .workspace-badge {{
                background-color: {color};
                color: white;
            }}
            """
            
            css_provider = Gtk.CssProvider()
            css_provider.load_from_data(css.encode())
            label.get_style_context().add_provider(
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            
            return label
        
        except Exception as e:
            logger.debug(f"Error creating badge: {e}")
            return None
    
    def position_at_edge(self):
        """Position window at configured edge"""
        try:
            # Get pointer position and monitor
            x, y = get_pointer_position()
            monitor = get_monitor_at_point(x, y)
            if not monitor:
                return
            
            monitor_geom = get_monitor_geometry(monitor)
            
            # Get window size
            self.window.show_all()
            width = self.window.get_allocated_width()
            height = self.window.get_allocated_height()
            
            # Determine edge
            edge = 'north'
            if self.config.get('south'):
                edge = 'south'
            elif self.config.get('east'):
                edge = 'east'
            elif self.config.get('west'):
                edge = 'west'
            
            # Calculate position
            pos_x, pos_y = position_window_at_edge(width, height, edge, monitor_geom)
            
            # Move window
            self.window.move(pos_x, pos_y)
        
        except Exception as e:
            logger.error(f"Error positioning window: {e}")
    
    def show(self):
        """Show the window"""
        self.window.show_all()
        self.position_at_edge()
    
    def hide(self):
        """Hide the window"""
        self.window.hide()


class ContextMenu:
    """Context menu for window operations"""
    
    def __init__(self, window_manager, switcher_window, on_menu_closed: callable):
        """Initialize context menu
        
        Args:
            window_manager: WindowManager instance
            switcher_window: SwitcherWindow instance (for position detection)
            on_menu_closed: Callback when menu closes
        """
        self.window_manager = window_manager
        self.switcher_window = switcher_window
        self.on_menu_closed = on_menu_closed
    
    def show(self, xid: int):
        """Show context menu for window
        
        Args:
            xid: Window XID
        """
        try:
            window = self.window_manager.get_window_by_xid(xid)
            if not window:
                logger.warning(f"Window {xid} not found")
                return
            
            menu = Gtk.Menu()
            
            # Move to current display
            item = Gtk.MenuItem(label="Move app to current display")
            item.connect("activate", self._on_move_to_display, xid)
            menu.append(item)
            
            # Resize to current display
            item = Gtk.MenuItem(label="Resize app to current display")
            item.connect("activate", self._on_resize_to_display, xid)
            menu.append(item)
            
            menu.append(Gtk.SeparatorMenuItem())
            
            # Minimize
            item = Gtk.MenuItem(label="Minimize app")
            item.connect("activate", self._on_minimize, xid)
            menu.append(item)
            
            # Maximize
            item = Gtk.MenuItem(label="Maximize app")
            item.connect("activate", self._on_maximize, xid)
            menu.append(item)
            
            menu.append(Gtk.SeparatorMenuItem())
            
            # Switch to app (activate window)
            item = Gtk.MenuItem(label="Switch to app")
            item.connect("activate", self._on_switch_to_app, xid)
            menu.append(item)
            
            # Go to app's workspace (without activating)
            item = Gtk.MenuItem(label="Go to app's workspace")
            item.connect("activate", self._on_go_to_workspace, xid)
            menu.append(item)
            
            # Move to workspace submenu
            workspaces_item = Gtk.MenuItem(label="Move to Workspace")
            workspaces_menu = Gtk.Menu()
            
            try:
                screen = self.window_manager.screen_wnck
                if screen:
                    workspaces = screen.get_workspaces()
                    for ws in workspaces:
                        ws_name = ws.get_name()
                        ws_num = ws.get_number()
                        item = Gtk.MenuItem(label=ws_name)
                        item.connect("activate", self._on_move_to_workspace, xid, ws_num)
                        workspaces_menu.append(item)
            except Exception as e:
                logger.debug(f"Error creating workspace menu: {e}")
            
            workspaces_item.set_submenu(workspaces_menu)
            menu.append(workspaces_item)
            
            menu.append(Gtk.SeparatorMenuItem())
            
            # Drag mode
            item = Gtk.MenuItem(label="Drag App")
            item.connect("activate", self._on_drag_app, xid)
            menu.append(item)
            
            # Connect close handler
            menu.connect("deactivate", lambda m: self.on_menu_closed())
            
            menu.show_all()
            menu.popup_at_pointer(None)
        
        except Exception as e:
            logger.error(f"Error showing context menu: {e}")
    
    def _on_move_to_display(self, menu_item, xid: int):
        """Move window to current display and workspace"""
        try:
            window = self.window_manager.get_window_by_xid(xid)
            if not window:
                return
            
            # Move to current workspace first
            screen = self.window_manager.screen_wnck
            if screen:
                active_workspace = screen.get_active_workspace()
                if active_workspace:
                    try:
                        window.move_to_workspace(active_workspace)
                    except Exception as e:
                        logger.debug(f"Could not move to workspace: {e}")
            
            # Get monitor where Otter window is displayed (not mouse position)
            monitor = None
            try:
                from gi.repository import Gdk as GdkModule
                display = GdkModule.Display.get_default()
                
                # Use switcher window position
                if self.switcher_window and self.switcher_window.window:
                    otter_x, otter_y = self.switcher_window.window.get_position()
                    monitor = display.get_monitor_at_point(otter_x, otter_y)
            except Exception as e:
                logger.debug(f"Could not get Otter window position: {e}")
            
            if not monitor:
                # Fallback to mouse position
                x, y = get_pointer_position()
                monitor = get_monitor_at_point(x, y)
            
            if not monitor:
                return
            
            geom = get_monitor_geometry(monitor)
            
            # Get current window geometry to preserve size
            try:
                current_geom = window.get_geometry()
                current_width = current_geom[2]
                current_height = current_geom[3]
            except Exception:
                current_width = -1
                current_height = -1
            
            # Move window with offset from edge, preserving size
            window.set_geometry(
                Wnck.WindowGravity.CURRENT,
                Wnck.WindowMoveResizeMask.X | Wnck.WindowMoveResizeMask.Y,
                geom['x'] + 50,
                geom['y'] + 50,
                current_width,
                current_height
            )
        
        except Exception as e:
            logger.error(f"Error moving to display: {e}")
    
    def _on_resize_to_display(self, menu_item, xid: int):
        """Resize window to current display"""
        try:
            window = self.window_manager.get_window_by_xid(xid)
            if not window:
                return
            
            x, y = get_pointer_position()
            monitor = get_monitor_at_point(x, y)
            if not monitor:
                return
            
            geom = get_monitor_geometry(monitor)
            
            # Resize to 80% of monitor
            new_width = int(geom['width'] * 0.8)
            new_height = int(geom['height'] * 0.8)
            
            window.set_geometry(
                Wnck.WindowGravity.CURRENT,
                Wnck.WindowMoveResizeMask.WIDTH | Wnck.WindowMoveResizeMask.HEIGHT,
                -1, -1,
                new_width, new_height
            )
        
        except Exception as e:
            logger.error(f"Error resizing: {e}")
    
    def _on_minimize(self, menu_item, xid: int):
        """Minimize window"""
        try:
            window = self.window_manager.get_window_by_xid(xid)
            if window:
                window.minimize()
        except Exception as e:
            logger.error(f"Error minimizing: {e}")
    
    def _on_maximize(self, menu_item, xid: int):
        """Maximize window"""
        try:
            window = self.window_manager.get_window_by_xid(xid)
            if window:
                window.maximize()
        except Exception as e:
            logger.error(f"Error maximizing: {e}")
    
    def _on_switch_to_app(self, menu_item, xid: int):
        """Switch to app (activate window and its workspace)"""
        try:
            window = self.window_manager.get_window_by_xid(xid)
            if not window:
                return
            
            # Activate workspace first
            try:
                workspace = window.get_workspace()
                if workspace:
                    timestamp = Gtk.get_current_event_time()
                    workspace.activate(timestamp)
            except Exception as e:
                logger.debug(f"Could not activate workspace: {e}")
            
            # Then activate window
            try:
                timestamp = Gtk.get_current_event_time()
                window.activate(timestamp)
            except Exception as e:
                logger.error(f"Could not activate window: {e}")
            
            # Update MRU timestamp
            self.window_manager.update_mru_timestamp(xid)
        
        except Exception as e:
            logger.error(f"Error switching to app: {e}")
    
    def _on_go_to_workspace(self, menu_item, xid: int):
        """Go to window's workspace (without activating window)"""
        try:
            window = self.window_manager.get_window_by_xid(xid)
            if not window:
                return
            
            workspace = window.get_workspace()
            if workspace:
                timestamp = Gtk.get_current_event_time()
                workspace.activate(timestamp)
        
        except Exception as e:
            logger.error(f"Error going to workspace: {e}")
    
    def _on_move_to_workspace(self, menu_item, xid: int, workspace_num: int):
        """Move window to workspace"""
        try:
            window = self.window_manager.get_window_by_xid(xid)
            if not window:
                return
            
            screen = self.window_manager.screen_wnck
            if not screen:
                return
            
            workspaces = screen.get_workspaces()
            if workspace_num < len(workspaces):
                workspace = workspaces[workspace_num]
                window.move_to_workspace(workspace)
        
        except Exception as e:
            logger.error(f"Error moving to workspace: {e}")
    
    def _on_drag_app(self, menu_item, xid: int):
        """Start drag mode"""
        try:
            window = self.window_manager.get_window_by_xid(xid)
            if not window:
                return
            
            # Get window geometry
            geom = window.get_geometry()
            x, y, width, height = geom
            
            # Calculate title bar center
            title_bar_height = 30
            center_x = x + width // 2
            center_y = y + title_bar_height // 2
            
            # Warp cursor
            display = Gdk.Display.get_default()
            if display:
                seat = display.get_default_seat()
                if seat:
                    pointer = seat.get_pointer()
                    if pointer:
                        screen = Gdk.Screen.get_default()
                        pointer.warp(screen, center_x, center_y)
            
            # Activate window
            timestamp = Gtk.get_current_event_time()
            window.activate(timestamp)
            
            # Start keyboard move
            GLib.timeout_add(100, lambda: window.keyboard_move())
        
        except Exception as e:
            logger.error(f"Error starting drag: {e}")
