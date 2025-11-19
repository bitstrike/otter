"""Window management and Wnck operations"""

import logging
import time
import threading
from typing import List, Dict, Optional
import gi

gi.require_version("Wnck", "3.0")
from gi.repository import Wnck

from .constants import SYSTEM_APPS, WNCK_RECREATION_INTERVAL, WNCK_MAX_CALLS, WNCK_GRACE_PERIOD

logger = logging.getLogger(__name__)


class WindowManager:
    """Manages Wnck screen and window operations"""
    
    def __init__(self, config: Dict, on_window_changed_callback=None):
        """Initialize window manager
        
        Args:
            config: Configuration dictionary
            on_window_changed_callback: Optional callback for window events
        """
        self.config = config
        self.on_window_changed = on_window_changed_callback
        
        # Wnck screen management
        self.screen_wnck = None
        self.wnck_lock = threading.RLock()
        self.wnck_recreating = False
        self.wnck_last_recreation = 0
        self.wnck_call_count = 0
        
        # MRU tracking
        self.mru_timestamps = {}
        
        # Initialize Wnck
        self._initialize_wnck()
    
    def _get_app_name(self, window, window_name: str) -> str:
        """Extract clean application name from window
        
        Args:
            window: Wnck window object
            window_name: Full window title
            
        Returns:
            Clean application name
        """
        try:
            # Try to get class group name (safer than get_application())
            class_group_name = window.get_class_group_name()
            if class_group_name and class_group_name.strip():
                return class_group_name
        except Exception as e:
            logger.debug(f"Could not get class group name: {e}")
        
        try:
            # Try to get class instance name
            class_instance = window.get_class_instance_name()
            if class_instance and class_instance.strip():
                # Capitalize first letter for nicer display
                return class_instance.capitalize()
        except Exception as e:
            logger.debug(f"Could not get class instance name: {e}")
        
        # Fallback: extract app name from window title
        # Common patterns: "Title - AppName", "Title | AppName", "AppName: Title"
        if " - " in window_name:
            # Try last part after " - " (e.g., "Page Title - Mozilla Firefox")
            parts = window_name.split(" - ")
            return parts[-1].strip()
        elif " | " in window_name:
            # Try last part after " | "
            parts = window_name.split(" | ")
            return parts[-1].strip()
        elif ": " in window_name:
            # Try first part before ": " (e.g., "Firefox: Page Title")
            parts = window_name.split(": ")
            return parts[0].strip()
        
        # Last resort: use full window name
        return window_name
    
    def _initialize_wnck(self):
        """Initialize Wnck screen"""
        try:
            Wnck.set_client_type(Wnck.ClientType.PAGER)
            self.screen_wnck = Wnck.Screen.get_default()
            
            if self.screen_wnck and self.on_window_changed:
                self.screen_wnck.connect("window-opened", self.on_window_changed)
                self.screen_wnck.connect("window-closed", self.on_window_changed)
            
            self.wnck_last_recreation = time.time()
            logger.info("Wnck screen initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Wnck: {e}")
            self.screen_wnck = None
    
    def window_is_valid(self, window) -> bool:
        """Check if window object is still valid
        
        Args:
            window: Wnck window object
            
        Returns:
            True if valid
        """
        if not window:
            return False
        
        try:
            name = window.get_name()
            return name is not None
        except Exception:
            return False
    
    def get_window_by_xid(self, xid: int) -> Optional:
        """Look up window by XID
        
        Args:
            xid: X11 window ID
            
        Returns:
            Window object or None
        """
        if not xid or not self.screen_wnck:
            return None
        
        try:
            with self.wnck_lock:
                if not self.screen_wnck:
                    return None
                
                window_list = self.screen_wnck.get_windows()
                for window in window_list:
                    if self.window_is_valid(window):
                        try:
                            if window.get_xid() == xid:
                                return window
                        except Exception:
                            continue
        except Exception as e:
            logger.debug(f"Error looking up window by XID {xid}: {e}")
        
        return None
    
    def get_window_id(self, window) -> int:
        """Get unique identifier for window
        
        Args:
            window: Wnck window object
            
        Returns:
            XID or 0 on error
        """
        try:
            return window.get_xid()
        except Exception:
            return 0
    
    def should_recreate_wnck(self) -> bool:
        """Check if Wnck screen should be recreated
        
        Returns:
            True if recreation needed
        """
        # Recreate after time interval
        if time.time() - self.wnck_last_recreation > WNCK_RECREATION_INTERVAL:
            logger.info(f"Wnck screen is {WNCK_RECREATION_INTERVAL}s old, recreating...")
            return True
        
        # Recreate after many calls
        if self.wnck_call_count > WNCK_MAX_CALLS:
            logger.info(f"Wnck called {self.wnck_call_count} times, recreating...")
            return True
        
        return False
    
    def recreate_wnck_screen(self) -> bool:
        """Recreate Wnck screen to prevent corruption
        
        Returns:
            True if successful
        """
        try:
            self.wnck_recreating = True
            logger.info(f"Recreating Wnck screen (calls: {self.wnck_call_count})")
            
            time.sleep(0.2)  # Let old screen settle
            
            self.screen_wnck = Wnck.Screen.get_default()
            
            if self.screen_wnck and self.on_window_changed:
                self.screen_wnck.connect("window-opened", self.on_window_changed)
                self.screen_wnck.connect("window-closed", self.on_window_changed)
            
            self.wnck_last_recreation = time.time()
            self.wnck_call_count = 0
            
            time.sleep(0.2)  # Let new screen settle
            
            self.wnck_recreating = False
            logger.info("Wnck screen recreated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to recreate Wnck screen: {e}")
            self.wnck_recreating = False
            return False
    
    def get_user_windows(self, force_update: bool = False) -> List[Dict]:
        """Get list of user windows
        
        Args:
            force_update: If True, force Wnck update regardless of grace period
        
        Returns:
            List of window info dictionaries
        """
        windows = []
        
        if not self.screen_wnck:
            return windows
        
        with self.wnck_lock:
            if self.wnck_recreating:
                return windows
            
            if self.should_recreate_wnck():
                self.recreate_wnck_screen()
            
            self.wnck_call_count += 1
            
            try:
                # Force update if past grace period OR if explicitly requested
                time_since_recreation = time.time() - self.wnck_last_recreation
                if force_update or time_since_recreation >= WNCK_GRACE_PERIOD:
                    try:
                        self.screen_wnck.force_update()
                    except Exception as e:
                        logger.error(f"force_update() failed: {e}")
                        if self.recreate_wnck_screen():
                            try:
                                self.screen_wnck.force_update()
                            except Exception:
                                return windows
                        else:
                            return windows
                
                # Get windows
                window_list = self.screen_wnck.get_windows()
                if not window_list:
                    return windows
                
                for window in window_list:
                    try:
                        if not self.window_is_valid(window):
                            continue
                        
                        # Check window type
                        window_type = window.get_window_type()
                        if window_type != Wnck.WindowType.NORMAL:
                            continue
                        
                        # Get window info
                        window_name = window.get_name() or "Unknown"
                        
                        # Try to get clean application name
                        app_name = self._get_app_name(window, window_name)
                        
                        # Check ignore list
                        is_ignored = any(
                            window_name.lower() == ignored.lower()
                            for ignored in self.config.get('ignore_list', [])
                        )
                        
                        # Filter system apps and ignored windows
                        if (app_name.lower() in [app.lower() for app in SYSTEM_APPS] or
                            is_ignored or
                            window_name == "Otter Window Switcher" or
                            not window_name.strip()):
                            continue
                        
                        # Get window properties
                        try:
                            is_minimized = window.is_minimized()
                        except Exception:
                            is_minimized = False
                        
                        try:
                            icon = window.get_icon()
                        except Exception:
                            icon = None
                        
                        try:
                            xid = window.get_xid()
                        except Exception:
                            xid = None
                        
                        # Get workspace info
                        workspace_index = None
                        workspace_name = "Unknown"
                        try:
                            workspace = window.get_workspace()
                            if workspace:
                                all_workspaces = self.screen_wnck.get_workspaces()
                                for idx, ws in enumerate(all_workspaces):
                                    if ws == workspace:
                                        workspace_index = idx + 1
                                        workspace_name = ws.get_name()
                                        break
                        except Exception:
                            pass
                        
                        # Store window info (never store Wnck object!)
                        windows.append({
                            'window': None,  # Never store Wnck object
                            'name': window_name,
                            'app_name': app_name,
                            'icon': icon,
                            'is_minimized': is_minimized,
                            'xid': xid,
                            'workspace_index': workspace_index,
                            'workspace_name': workspace_name,
                            'window_type': str(window_type),
                        })
                        
                    except Exception as e:
                        logger.debug(f"Error processing window: {e}")
                        continue
                
            except Exception as e:
                logger.error(f"Error getting user windows: {e}")
                return []
        
        # Apply MRU ordering if enabled
        if self.config.get('recent', False):
            windows.sort(key=lambda w: w['app_name'].lower())
            
            try:
                def get_timestamp(w):
                    xid = w.get('xid')
                    return self.mru_timestamps.get(xid, 0) if xid else 0
                
                windows.sort(key=get_timestamp, reverse=True)
            except Exception as e:
                logger.debug(f"Error applying MRU sort: {e}")
        
        return windows
    
    def update_mru_timestamp(self, xid: int):
        """Update MRU timestamp for window
        
        Args:
            xid: Window XID
        """
        if xid:
            self.mru_timestamps[xid] = time.time()
    
    def is_active_window_fullscreen(self) -> bool:
        """Check if active window is fullscreen
        
        Returns:
            True if fullscreen
        """
        if not self.screen_wnck:
            return False
        
        try:
            active_window = self.screen_wnck.get_active_window()
            if not active_window:
                return False
            return active_window.is_fullscreen()
        except Exception:
            return False
