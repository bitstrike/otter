"""System tray icon for Otter"""

import os
import logging
from typing import Callable, Optional
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf

logger = logging.getLogger(__name__)

# Version info
OTTER_VERSION = "2.0.0"
OTTER_AUTHOR = "Built with Claude"
OTTER_DESCRIPTION = """Otter Window Switcher

A mouse-activated, edge-triggered app switcher for GTK-based Linux desktop environments.

"""


class OtterTrayIcon:
    """System tray icon for Otter application"""
    
    def __init__(self, app, on_show: Callable, on_quit: Callable):
        """Initialize tray icon
        
        Args:
            app: Main application instance
            on_show: Callback to show otter window
            on_quit: Callback to quit application
        """
        self.app = app
        self.on_show = on_show
        self.on_quit = on_quit
        self.paused = False
        
        # Create status icon
        self.status_icon = Gtk.StatusIcon()
        self.status_icon.set_title("Otter Window Switcher")
        self.status_icon.set_tooltip_text("Otter Window Switcher")
        
        # Load icon
        self._load_icon()
        
        # Connect signals
        self.status_icon.connect("activate", self._on_left_click)
        self.status_icon.connect("popup-menu", self._on_right_click)
        
        # Make visible
        self.status_icon.set_visible(True)
        
        logger.info("System tray icon created")
    
    def _load_icon(self, paused: bool = False):
        """Load application icon
        
        Args:
            paused: If True, load grayscale version to indicate paused state
        """
        try:
            # Try to load from images directory
            icon_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'images',
                'app_icon.png'
            )
            
            if os.path.exists(icon_path):
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    icon_path, 22, 22, True
                )
                
                # Convert to grayscale if paused
                if paused:
                    pixbuf = self._make_grayscale(pixbuf)
                
                self.status_icon.set_from_pixbuf(pixbuf)
                logger.debug(f"Loaded tray icon from {icon_path} (paused: {paused})")
            else:
                # Fallback to stock icon
                icon_name = "media-playback-pause" if paused else "preferences-system-windows"
                self.status_icon.set_from_icon_name(icon_name)
                logger.debug(f"Using fallback stock icon: {icon_name}")
        
        except Exception as e:
            logger.error(f"Error loading tray icon: {e}")
            # Fallback to stock icon
            icon_name = "media-playback-pause" if paused else "preferences-system-windows"
            self.status_icon.set_from_icon_name(icon_name)
    
    def _make_grayscale(self, pixbuf: GdkPixbuf.Pixbuf) -> GdkPixbuf.Pixbuf:
        """Convert pixbuf to grayscale
        
        Args:
            pixbuf: Original pixbuf
            
        Returns:
            Grayscale pixbuf
        """
        try:
            # Use GdkPixbuf's built-in saturate_and_pixelate method
            # saturation=0.0 makes it grayscale, pixelate=False keeps it sharp
            gray_pixbuf = pixbuf.copy()
            gray_pixbuf.saturate_and_pixelate(gray_pixbuf, 0.0, False)
            return gray_pixbuf
        
        except Exception as e:
            logger.debug(f"Error making grayscale: {e}")
            # Return original on error
            return pixbuf
    
    def _on_left_click(self, status_icon):
        """Handle left-click on tray icon
        
        Args:
            status_icon: StatusIcon widget
        """
        logger.debug("Tray icon left-clicked")
        
        # Don't show if paused
        if self.paused:
            logger.debug("Otter is paused, not showing window")
            return
        
        # Show otter window
        try:
            self.on_show()
        except Exception as e:
            logger.error(f"Error showing window from tray: {e}")
    
    def _on_right_click(self, status_icon, button, activate_time):
        """Handle right-click on tray icon
        
        Args:
            status_icon: StatusIcon widget
            button: Mouse button
            activate_time: Activation timestamp
        """
        logger.debug("Tray icon right-clicked")
        
        # Create context menu
        menu = Gtk.Menu()
        
        # Pause/Resume item
        pause_item = Gtk.MenuItem(
            label="Resume" if self.paused else "Pause"
        )
        pause_item.connect("activate", self._on_toggle_pause)
        menu.append(pause_item)
        
        menu.append(Gtk.SeparatorMenuItem())
        
        # About item
        about_item = Gtk.MenuItem(label="About")
        about_item.connect("activate", self._on_about)
        menu.append(about_item)
        
        menu.append(Gtk.SeparatorMenuItem())
        
        # Quit item
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self._on_quit_clicked)
        menu.append(quit_item)
        
        # Show menu
        menu.show_all()
        menu.popup(None, None, None, None, button, activate_time)
    
    def _on_toggle_pause(self, menu_item):
        """Toggle pause/resume state
        
        Args:
            menu_item: Menu item that triggered this
        """
        self.paused = not self.paused
        
        if self.paused:
            logger.info("Otter paused - edge detection disabled")
            self.status_icon.set_tooltip_text("Otter Window Switcher (Paused)")
            
            # Update icon to grayscale
            self._load_icon(paused=True)
            
            # Stop edge detector
            if hasattr(self.app, 'edge_detector'):
                self.app.edge_detector.stop()
            
            # Hide window if visible
            if hasattr(self.app, 'otter_state'):
                from .main import OtterState
                if self.app.otter_state == OtterState.VISIBLE:
                    self.app.hide_window()
        else:
            logger.info("Otter resumed - edge detection enabled")
            self.status_icon.set_tooltip_text("Otter Window Switcher")
            
            # Update icon to color
            self._load_icon(paused=False)
            
            # Restart edge detector
            if hasattr(self.app, 'edge_detector'):
                self.app.edge_detector.start()
    
    def _on_about(self, menu_item):
        """Show about dialog
        
        Args:
            menu_item: Menu item that triggered this
        """
        logger.debug("Showing about dialog")
        
        # Create about dialog
        about = Gtk.AboutDialog()
        about.set_program_name("Otter Window Switcher")
        about.set_version(OTTER_VERSION)
        about.set_comments(OTTER_DESCRIPTION)
        about.set_authors([OTTER_AUTHOR])
        about.set_website("https://github.com/yourusername/otter2")
        about.set_website_label("GitHub Repository")
        about.set_license_type(Gtk.License.GPL_3_0)
        
        # Load icon for about dialog
        try:
            icon_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'images',
                'app_icon.png'
            )
            if os.path.exists(icon_path):
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    icon_path, 64, 64, True
                )
                about.set_logo(pixbuf)
        except Exception as e:
            logger.debug(f"Could not load icon for about dialog: {e}")
        
        # Show dialog
        about.run()
        about.destroy()
    
    def _on_quit_clicked(self, menu_item):
        """Handle quit menu item
        
        Args:
            menu_item: Menu item that triggered this
        """
        logger.info("Quit selected from tray menu")
        
        # Call quit callback
        try:
            self.on_quit()
        except Exception as e:
            logger.error(f"Error quitting from tray: {e}")
    
    def update_for_state(self, state):
        """Update tray icon appearance based on application state
        
        Args:
            state: OtterState enum value
        """
        try:
            from .main import OtterState
            
            # Show grayscale when DISABLED (shift-hide) or paused
            is_disabled = (state == OtterState.DISABLED) or self.paused
            
            # Update icon
            self._load_icon(paused=is_disabled)
            
            # Update tooltip
            if state == OtterState.DISABLED:
                self.status_icon.set_tooltip_text("Otter Window Switcher (Temporarily Disabled)")
            elif self.paused:
                self.status_icon.set_tooltip_text("Otter Window Switcher (Paused)")
            else:
                self.status_icon.set_tooltip_text("Otter Window Switcher")
            
            logger.debug(f"Tray icon updated for state: {state}, paused: {self.paused}")
        
        except Exception as e:
            logger.debug(f"Error updating tray icon for state: {e}")
    
    def destroy(self):
        """Clean up tray icon"""
        try:
            if self.status_icon:
                self.status_icon.set_visible(False)
                logger.debug("Tray icon destroyed")
        except Exception as e:
            logger.debug(f"Error destroying tray icon: {e}")
