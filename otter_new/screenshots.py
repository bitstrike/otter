"""Screenshot capture and caching"""

import logging
import time
from typing import Optional, Dict
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

from .constants import MAX_CACHE_SIZE

logger = logging.getLogger(__name__)

# Check for GdkX11 availability
try:
    from gi.repository import GdkX11
    GDKX11_AVAILABLE = True
except ImportError:
    GdkX11 = None
    GDKX11_AVAILABLE = False


class ScreenshotManager:
    """Manages screenshot capture and caching"""
    
    def __init__(self, window_manager, thumbnail_width: int = 160):
        """Initialize screenshot manager
        
        Args:
            window_manager: WindowManager instance
            thumbnail_width: Width for thumbnails
        """
        self.window_manager = window_manager
        self.thumbnail_width = thumbnail_width
        
        # Caches
        self.screenshot_cache: Dict[int, GdkPixbuf.Pixbuf] = {}
        self.last_valid_screenshots: Dict[int, GdkPixbuf.Pixbuf] = {}
        
        # Startup preprocessing
        self.startup_splash = None
        self.startup_preprocessing_active = False
    
    def scale_pixbuf(self, pixbuf: GdkPixbuf.Pixbuf) -> Optional[GdkPixbuf.Pixbuf]:
        """Scale pixbuf to thumbnail size
        
        Args:
            pixbuf: Source pixbuf
            
        Returns:
            Scaled pixbuf or None
        """
        if not pixbuf:
            return None
        
        try:
            width = pixbuf.get_width()
            height = pixbuf.get_height()
            
            if width == 0 or height == 0:
                return None
            
            # Calculate scaled dimensions
            aspect_ratio = height / width
            new_width = self.thumbnail_width
            new_height = int(new_width * aspect_ratio)
            
            # Scale with high quality
            scaled = pixbuf.scale_simple(
                new_width,
                new_height,
                GdkPixbuf.InterpType.BILINEAR
            )
            
            return scaled
        except Exception as e:
            logger.debug(f"Error scaling pixbuf: {e}")
            return None
    
    def capture_window(self, window) -> Optional[GdkPixbuf.Pixbuf]:
        """Capture window screenshot
        
        Args:
            window: Wnck window object
            
        Returns:
            Pixbuf or None
        """
        if not GDKX11_AVAILABLE:
            return None
        
        try:
            xid = window.get_xid()
            if not xid:
                return None
            
            display = Gdk.Display.get_default()
            if not display:
                return None
            
            gdk_window = GdkX11.X11Window.foreign_new_for_display(display, xid)
            if not gdk_window:
                return None
            
            if gdk_window.is_viewable():
                width = gdk_window.get_width()
                height = gdk_window.get_height()
                
                if width > 0 and height > 0:
                    pixbuf = Gdk.pixbuf_get_from_window(gdk_window, 0, 0, width, height)
                    return pixbuf
        
        except Exception as e:
            logger.debug(f"Error capturing window: {e}")
        
        return None
    
    def get_screenshot(self, window) -> Optional[GdkPixbuf.Pixbuf]:
        """Get screenshot for window (with caching)
        
        Args:
            window: Wnck window object
            
        Returns:
            Scaled pixbuf or None
        """
        try:
            if not self.window_manager.window_is_valid(window):
                return None
            
            window_id = self.window_manager.get_window_id(window)
            
            # Check if minimized
            try:
                is_minimized = window.is_minimized()
            except Exception:
                is_minimized = True
            
            # Return cached screenshot for minimized windows
            if is_minimized:
                return self.last_valid_screenshots.get(window_id)
            
            # Try to capture
            if self.window_manager.window_is_valid(window):
                pixbuf = self.capture_window(window)
                if pixbuf:
                    scaled = self.scale_pixbuf(pixbuf)
                    if scaled:
                        self.last_valid_screenshots[window_id] = scaled
                        return scaled
            
            # Return cached if available
            return self.last_valid_screenshots.get(window_id)
        
        except Exception as e:
            logger.debug(f"Error getting screenshot: {e}")
            return None
    
    def update_cache(self, current_windows: list):
        """Update screenshot cache
        
        Args:
            current_windows: List of window info dicts
        """
        try:
            # Get existing XIDs
            existing_xids = {w['xid'] for w in current_windows if w.get('xid')}
            cached_xids = set(self.screenshot_cache.keys())
            
            # Clean up old entries
            for xid in cached_xids - existing_xids:
                try:
                    del self.screenshot_cache[xid]
                    if xid in self.last_valid_screenshots:
                        del self.last_valid_screenshots[xid]
                except (KeyError, AttributeError):
                    pass
            
            # Enforce cache size limit
            if len(self.screenshot_cache) > MAX_CACHE_SIZE:
                excess = len(self.screenshot_cache) - MAX_CACHE_SIZE
                keys_to_remove = list(self.screenshot_cache.keys())[:excess]
                for key in keys_to_remove:
                    try:
                        del self.screenshot_cache[key]
                        if key in self.last_valid_screenshots:
                            del self.last_valid_screenshots[key]
                    except (KeyError, AttributeError):
                        pass
            
            # Update screenshots
            for window_info in current_windows:
                try:
                    xid = window_info.get('xid')
                    if not xid:
                        continue
                    
                    window = self.window_manager.get_window_by_xid(xid)
                    if not window:
                        continue
                    
                    if not self.window_manager.window_is_valid(window):
                        continue
                    
                    screenshot = self.get_screenshot(window)
                    if screenshot:
                        self.screenshot_cache[xid] = screenshot
                
                except Exception as e:
                    logger.debug(f"Error updating screenshot: {e}")
        
        except Exception as e:
            logger.error(f"Error updating cache: {e}")
    
    def create_startup_splash(self):
        """Create startup splash screen"""
        splash = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        splash.set_position(Gtk.WindowPosition.CENTER)
        splash.set_decorated(False)
        splash.set_keep_above(True)
        splash.set_skip_taskbar_hint(True)
        splash.set_skip_pager_hint(True)
        splash.set_modal(False)
        splash.set_default_size(400, 200)
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        vbox.set_margin_top(30)
        vbox.set_margin_bottom(30)
        vbox.set_margin_start(30)
        vbox.set_margin_end(30)
        
        # Try to load app icon
        try:
            import os
            icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'images', 'app_icon.png')
            if os.path.exists(icon_path):
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_path, 64, 64, True)
                icon = Gtk.Image.new_from_pixbuf(pixbuf)
                vbox.pack_start(icon, False, False, 0)
        except Exception as e:
            logger.debug(f"Could not load app icon: {e}")
        
        title = Gtk.Label()
        title.set_markup("<span size='large' weight='bold'>Otter Window Switcher</span>")
        vbox.pack_start(title, False, False, 0)
        
        status = Gtk.Label()
        status.set_text("Preparing window thumbnails...")
        vbox.pack_start(status, False, False, 0)
        
        progress = Gtk.ProgressBar()
        progress.set_show_text(True)
        vbox.pack_start(progress, False, False, 0)
        
        splash.add(vbox)
        splash.show_all()
        
        self.startup_splash = {
            'window': splash,
            'progress': progress,
            'status': status
        }
        
        return splash
    
    def update_startup_progress(self, current: int, total: int):
        """Update startup progress
        
        Args:
            current: Current window number
            total: Total windows
        """
        if not self.startup_splash:
            return
        
        try:
            progress = self.startup_splash['progress']
            status = self.startup_splash['status']
            
            if total > 0:
                fraction = current / total
                progress.set_fraction(fraction)
                progress.set_text(f"{current}/{total}")
                status.set_text(f"Processing window {current} of {total}...")
            
            while Gtk.events_pending():
                Gtk.main_iteration()
        
        except Exception as e:
            logger.debug(f"Error updating progress: {e}")
    
    def preprocess_startup_thumbnails(self):
        """Preprocess thumbnails on startup"""
        self.startup_preprocessing_active = True
        logger.info("Starting startup preprocessing...")
        
        try:
            self.create_startup_splash()
            
            # Let splash render
            for _ in range(10):
                GLib.usleep(10000)
            
            # Force update to get current windows (bypass grace period)
            current_windows = self.window_manager.get_user_windows(force_update=True)
            total = len(current_windows)
            logger.info(f"Preprocessing {total} windows")
            
            for i, window_info in enumerate(current_windows):
                try:
                    if not self.startup_preprocessing_active:
                        break
                    
                    self.update_startup_progress(i + 1, total)
                    
                    xid = window_info.get('xid')
                    if not xid:
                        continue
                    
                    window = self.window_manager.get_window_by_xid(xid)
                    if not window:
                        continue
                    
                    screenshot = self.get_screenshot(window)
                    if screenshot:
                        self.screenshot_cache[xid] = screenshot
                    
                    GLib.usleep(50000)
                
                except Exception as e:
                    logger.debug(f"Error preprocessing window {i + 1}: {e}")
            
            logger.info("Startup preprocessing complete")
        
        except Exception as e:
            logger.error(f"Error during preprocessing: {e}")
        finally:
            self.startup_preprocessing_active = False
            
            if self.startup_splash:
                try:
                    self.startup_splash['window'].destroy()
                except Exception:
                    pass
                self.startup_splash = None
