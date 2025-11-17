"""Input handling: edge detection, events, shift monitoring"""

import logging
from typing import Callable, Optional
from gi.repository import Gtk, Gdk, GLib

from .geometry import get_pointer_position, get_monitor_at_point, get_monitor_geometry, check_edge_trigger
from .constants import EDGE_TRIGGER_THRESHOLD, MOUSE_POLL_INTERVAL

logger = logging.getLogger(__name__)


class EdgeDetector:
    """Detects mouse at screen edges"""
    
    def __init__(self, edge: str, on_trigger: Callable, on_leave: Callable, main_character: bool = False):
        """Initialize edge detector
        
        Args:
            edge: Edge to monitor ('north', 'south', 'east', 'west')
            on_trigger: Callback when edge is triggered
            on_leave: Callback when mouse leaves edge
            main_character: If True, disable during fullscreen
        """
        self.edge = edge
        self.on_trigger = on_trigger
        self.on_leave = on_leave
        self.main_character = main_character
        self.window_manager = None  # Set externally
        self.switcher_window = None  # Set externally to check if mouse is over window
        self.app = None  # Set externally to check state machine
        
        self.monitor_id = None
    
    def start(self):
        """Start monitoring mouse position"""
        if self.monitor_id is None:
            self.monitor_id = GLib.timeout_add(MOUSE_POLL_INTERVAL, self._check_position)
            logger.info(f"Edge detector started (edge: {self.edge})")
    
    def stop(self):
        """Stop monitoring"""
        if self.monitor_id is not None:
            GLib.source_remove(self.monitor_id)
            self.monitor_id = None
            logger.info("Edge detector stopped")
    
    def _mouse_in_window(self, x: int, y: int) -> bool:
        """Check if mouse is within window bounds
        
        Args:
            x: Mouse X coordinate
            y: Mouse Y coordinate
            
        Returns:
            True if mouse is in window
        """
        if not self.switcher_window or not self.switcher_window.window:
            return False
        
        try:
            window = self.switcher_window.window
            if not window.get_visible():
                return False
            
            # Get window position and size
            win_x, win_y = window.get_position()
            allocation = window.get_allocation()
            win_width = allocation.width
            win_height = allocation.height
            
            # Check if mouse is within window bounds
            return (win_x <= x <= win_x + win_width and 
                    win_y <= y <= win_y + win_height)
        except Exception as e:
            logger.debug(f"Error checking mouse in window: {e}")
            return False
    
    def _check_position(self) -> bool:
        """Check mouse position (GLib callback)
        
        Returns:
            True to continue monitoring
        """
        try:
            # Get pointer position
            x, y = get_pointer_position()
            
            # Get monitor at pointer
            monitor = get_monitor_at_point(x, y)
            if not monitor:
                return True
            
            monitor_geom = get_monitor_geometry(monitor)
            
            # Check if at edge (5px threshold)
            at_edge = check_edge_trigger(x, y, self.edge, monitor_geom, EDGE_TRIGGER_THRESHOLD)
            
            # Get current state from app
            from .main import OtterState
            current_state = self.app.otter_state if self.app else OtterState.HIDDEN
            
            # Debug logging
            if at_edge:
                logger.debug(f"At edge: state={current_state}")
            
            # CRITICAL: During DISABLED state, ignore ALL triggers
            if current_state == OtterState.DISABLED:
                return True
            
            # HIDDEN state: check for edge trigger to show window
            if current_state == OtterState.HIDDEN:
                # Check fullscreen mode if main_character enabled
                if self.main_character and self.window_manager:
                    if self.window_manager.is_active_window_fullscreen():
                        return True
                
                # Check if mouse is at edge
                if at_edge:
                    logger.debug("Calling on_trigger (show)")
                    self.on_trigger()
            
            # VISIBLE state: check for hide conditions
            elif current_state == OtterState.VISIBLE:
                # Grace period: Don't hide for 300ms after showing (prevents flicker)
                import time
                if hasattr(self.app, 'last_show_time'):
                    time_since_show = time.time() - self.app.last_show_time
                    if time_since_show < 0.3:  # 300ms grace period
                        return True
                
                # CRITICAL: If mouse is at edge, don't hide (prevents show/hide loop)
                # The edge area is part of the safe zone when window is visible
                if at_edge:
                    return True
                
                # Check if mouse is in window first
                mouse_in_window = self._mouse_in_window(x, y)
                if mouse_in_window:
                    # Mouse is in window, don't hide
                    return True
                
                # Check if mouse is in hotbox (window bounds + 10px buffer)
                if self.switcher_window and self.switcher_window.window:
                    try:
                        window = self.switcher_window.window
                        if window.get_visible():
                            win_x, win_y = window.get_position()
                            allocation = window.get_allocation()
                            win_width = allocation.width
                            win_height = allocation.height
                            
                            # Hotbox = window bounds + 10px buffer
                            buffer = 10
                            in_hotbox = (
                                win_x - buffer <= x <= win_x + win_width + buffer and
                                win_y - buffer <= y <= win_y + win_height + buffer
                            )
                            
                            # If in hotbox, don't hide
                            if in_hotbox:
                                return True
                            
                            # Mouse left hotbox AND edge - hide
                            logger.debug("Mouse left hotbox - calling on_leave (hide)")
                            self.on_leave()
                    except Exception as e:
                        logger.debug(f"Error checking hotbox: {e}")
        
        except Exception as e:
            logger.debug(f"Error checking position: {e}")
        
        return True  # Continue monitoring


class ShiftMonitor:
    """Monitors shift key for temporary hide"""
    
    def __init__(self, hide_duration: float, on_shift_pressed: Callable):
        """Initialize shift monitor
        
        Args:
            hide_duration: Duration to hide in seconds
            on_shift_pressed: Callback when shift is pressed (receives keyname)
        """
        self.hide_duration = hide_duration
        self.on_shift_pressed = on_shift_pressed
        self.enabled = hide_duration > 0
    
    def setup(self, window):
        """Setup shift key monitoring on window
        
        Args:
            window: GTK window to monitor
        """
        if not self.enabled:
            return
        
        window.connect("key-press-event", self._on_key_press)
        logger.info(f"Shift monitor enabled (hide for {self.hide_duration}s)")
    
    def _on_key_press(self, widget, event) -> bool:
        """Handle key press events
        
        Args:
            widget: GTK widget
            event: Key event
            
        Returns:
            False to propagate event
        """
        keyval = event.keyval
        keyname = Gdk.keyval_name(keyval)
        
        # Check if it's a shift key
        if keyname in ['Shift_L', 'Shift_R']:
            logger.debug(f"Shift key detected: {keyname}")
            self.on_shift_pressed(keyname)
        
        return False  # Propagate event


class EventHandler:
    """Handles GTK events for switcher window"""
    
    def __init__(self, app):
        """Initialize event handler
        
        Args:
            app: Main application instance
        """
        self.app = app
    
    def on_window_clicked(self, button, xid: int):
        """Handle window thumbnail click
        
        Args:
            button: GTK button
            xid: Window XID
        """
        try:
            window = self.app.window_manager.get_window_by_xid(xid)
            if not window:
                logger.warning(f"Window {xid} no longer exists")
                return
            
            # Update MRU
            self.app.window_manager.update_mru_timestamp(xid)
            
            # Activate window
            timestamp = Gtk.get_current_event_time()
            window.activate(timestamp)
            logger.debug(f"Activated window {xid}")
            
            # Hide switcher
            self.app.hide_window()
        
        except Exception as e:
            logger.error(f"Error activating window: {e}")
    
    def on_button_press(self, button, event, xid: int) -> bool:
        """Handle button press for context menu and middle-click
        
        Args:
            button: GTK button
            event: Button event
            xid: Window XID
            
        Returns:
            True if handled
        """
        try:
            # Right-click: context menu
            if event.button == 3:
                self.app.show_context_menu(xid)
                return True
            
            # Middle-click: switch to workspace
            elif event.button == 2:
                self.on_middle_click(xid)
                return True
        
        except Exception as e:
            logger.error(f"Error handling button press: {e}")
        
        return False
    
    def on_middle_click(self, xid: int):
        """Handle middle-click (switch to workspace without activating)
        
        Args:
            xid: Window XID
        """
        try:
            window = self.app.window_manager.get_window_by_xid(xid)
            if not window:
                return
            
            workspace = window.get_workspace()
            if not workspace:
                return
            
            screen = self.app.window_manager.screen_wnck
            if not screen:
                return
            
            current_workspace = screen.get_active_workspace()
            
            # Update MRU timestamp (middle-click counts as interaction)
            self.app.window_manager.update_mru_timestamp(xid)
            
            # If already on current workspace, activate window
            if workspace == current_workspace:
                timestamp = Gtk.get_current_event_time()
                window.activate(timestamp)
                self.app.hide_window()
            else:
                # Switch to workspace without activating
                timestamp = Gtk.get_current_event_time()
                workspace.activate(timestamp)
                logger.debug(f"Switched to workspace {workspace.get_name()}")
                
                # Schedule redisplay on new workspace after 200ms
                # This ensures otter appears on the new workspace
                GLib.timeout_add(200, self._redisplay_after_workspace_switch)
        
        except Exception as e:
            logger.error(f"Error handling middle-click: {e}")
    
    def _redisplay_after_workspace_switch(self) -> bool:
        """Redisplay otter window after workspace switch from middle-click
        
        Returns:
            False (don't repeat)
        """
        try:
            from .main import OtterState
            
            # If in VISIBLE state, ensure window is on top
            if self.app.otter_state == OtterState.VISIBLE:
                if self.app.switcher_window and self.app.switcher_window.window:
                    self.app.switcher_window.window.present()
                    logger.debug("Otter redisplayed after workspace switch")
            # If window became hidden during switch, show it again
            elif self.app.otter_state == OtterState.HIDDEN:
                self.app.show_window()
                logger.info("Otter restored to visible after workspace switch")
        except Exception as e:
            logger.error(f"Error redisplaying otter after workspace switch: {e}")
        
        return False  # Don't repeat
    
    def on_scroll(self, widget, event) -> bool:
        """Handle mouse wheel scrolling
        
        Args:
            widget: GTK widget
            event: Scroll event
            
        Returns:
            True if handled
        """
        try:
            if not hasattr(self.app, 'scroll_window'):
                return False
            
            scroll_window = self.app.scroll_window
            if not scroll_window:
                return False
            
            adjustment = scroll_window.get_vadjustment()
            if not adjustment:
                return False
            
            # Get scroll direction
            if event.direction == Gdk.ScrollDirection.UP:
                delta = -50
            elif event.direction == Gdk.ScrollDirection.DOWN:
                delta = 50
            else:
                return False
            
            # Scroll
            current = adjustment.get_value()
            new_value = max(0, min(current + delta, adjustment.get_upper() - adjustment.get_page_size()))
            adjustment.set_value(new_value)
            
            return True
        
        except Exception as e:
            logger.debug(f"Error handling scroll: {e}")
            return False
    
    def on_enter_notify(self, widget, event) -> bool:
        """Handle mouse entering window
        
        Args:
            widget: GTK widget
            event: Crossing event
            
        Returns:
            False
        """
        # Cancel any pending hide
        if hasattr(self.app, 'delayed_hide_id') and self.app.delayed_hide_id:
            GLib.source_remove(self.app.delayed_hide_id)
            self.app.delayed_hide_id = None
        
        return False
    
    def on_leave_notify(self, widget, event) -> bool:
        """Handle mouse leaving window
        
        Args:
            widget: GTK widget
            event: Crossing event
            
        Returns:
            False
        """
        # Don't hide on leave-notify - let edge detector handle it
        # This prevents flickering when mouse moves within the window area
        return False
    
    def on_destroy(self, widget):
        """Handle window destruction
        
        Args:
            widget: GTK widget
        """
        self.app.cleanup()
