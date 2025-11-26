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
    
    def __init__(self, hide_duration: float, on_shift_pressed: Callable, custom_keyval: Optional[int] = None):
        """Initialize shift monitor
        
        Args:
            hide_duration: Duration to hide in seconds
            on_shift_pressed: Callback when shift is pressed (receives keyname)
            custom_keyval: Optional custom key value (from --hidekey)
        """
        self.hide_duration = hide_duration
        self.on_shift_pressed = on_shift_pressed
        self.custom_keyval = custom_keyval
        self.enabled = hide_duration > 0
    
    def setup(self, window):
        """Setup shift key monitoring on window
        
        Args:
            window: GTK window to monitor
        """
        if not self.enabled:
            return
        
        window.connect("key-press-event", self._on_key_press)
        
        if self.custom_keyval:
            logger.info(f"Hide key monitor enabled (keyval: 0x{self.custom_keyval:x}, hide for {self.hide_duration}s)")
        else:
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
        
        # Debug: Log all key presses when verbose
        logger.debug(f"Key press detected: {keyname} (keyval: 0x{keyval:x})")
        
        # Check for custom hide key first
        if self.custom_keyval and keyval == self.custom_keyval:
            logger.info(f"Custom hide key detected: {keyname} (keyval: 0x{keyval:x})")
            self.on_shift_pressed(keyname)
            return False
        
        # Check if it's a shift key (including ISO variants for international keyboards)
        shift_keys = ['Shift_L', 'Shift_R', 'ISO_Left_Shift', 'ISO_Right_Shift']
        if keyname in shift_keys:
            logger.info(f"Shift key detected: {keyname}")
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
            
            # Validate window is still valid before activation
            if not self.app.window_manager.window_is_valid(window):
                logger.warning(f"Window {xid} is no longer valid")
                return
            
            # Update MRU
            self.app.window_manager.update_mru_timestamp(xid)
            
            # Activate window with error handling
            try:
                timestamp = Gtk.get_current_event_time()
                window.activate(timestamp)
                logger.debug(f"Activated window {xid}")
            except Exception as e:
                logger.error(f"Error activating window {xid}: {e}")
                return
            
            # Defer hide to let activation complete and avoid BadDrawable
            GLib.idle_add(self.app.hide_window)
        
        except Exception as e:
            logger.error(f"Error in window click handler: {e}")
    
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
                # Switch to workspace and activate window
                timestamp = Gtk.get_current_event_time()
                workspace.activate(timestamp)
                logger.debug(f"[STATE] Switched to workspace {workspace.get_name()}, current state: {self.app.otter_state}")

                # Keep otter visible during workspace switch
                # Don't hide the window - it should stay visible
                logger.debug(f"[STATE] Keeping otter visible during workspace switch")

                # Store the window XID to bring it to front after otter redisplay
                self._pending_window_xid_for_stacking = xid

                # Activate window after workspace switch (with delay)
                GLib.timeout_add(100, lambda: self._activate_window_after_switch(xid))

                # Schedule redisplay on new workspace after 200ms
                # This ensures otter appears on the new workspace with updated tint
                GLib.timeout_add(200, self._redisplay_after_workspace_switch)
        
        except Exception as e:
            logger.error(f"Error handling middle-click: {e}")
    
    def _activate_window_after_switch(self, xid: int) -> bool:
        """Activate window after workspace switch
        
        Args:
            xid: Window XID
            
        Returns:
            False (don't repeat)
        """
        try:
            window = self.app.window_manager.get_window_by_xid(xid)
            if not window:
                logger.debug(f"Window {xid} no longer exists after workspace switch")
                return False
            
            # Validate window is still valid
            if not self.app.window_manager.window_is_valid(window):
                logger.debug(f"Window {xid} is no longer valid after workspace switch")
                return False
            
            # Use current time instead of event time (which is 0 in timeout)
            import time
            timestamp = int(time.time() * 1000) & 0xFFFFFFFF  # Convert to X11 timestamp
            
            try:
                window.activate(timestamp)
                logger.debug(f"Activated window {xid} after workspace switch (timestamp: {timestamp})")
            except Exception as e:
                logger.error(f"Error activating window {xid} after workspace switch: {e}")
        except Exception as e:
            logger.error(f"Error in _activate_window_after_switch: {e}")
        
        return False
        
        return False  # Don't repeat
    
    def _redisplay_after_workspace_switch(self) -> bool:
        """Redisplay otter window after workspace switch from middle-click

        Returns:
            False (don't repeat)
        """
        try:
            from .main import OtterState

            logger.debug(f"[STATE] _redisplay_after_workspace_switch called, current state: {self.app.otter_state}")

            # Always ensure window is visible after workspace switch
            if self.app.switcher_window and self.app.switcher_window.window:
                window = self.app.switcher_window.window
                was_visible = window.get_visible()
                logger.debug(f"[STATE] Window visible before redisplay: {was_visible}")

                # Reapply workspace tint for new workspace
                self.app.switcher_window._apply_workspace_tint()

                # Always show window after workspace switch
                window.show_all()
                logger.debug(f"[STATE] Called show_all() on window")

                # Ensure window is on top
                window.present()
                logger.debug(f"[STATE] Called present() on window")

                # Ensure state is VISIBLE
                if self.app.otter_state != OtterState.VISIBLE:
                    logger.debug(f"[STATE] Changing state from {self.app.otter_state} to VISIBLE")
                    self.app.otter_state = OtterState.VISIBLE
                    self.app.last_show_time = time.time()  # Reset grace period

                is_visible = window.get_visible()
                logger.debug(f"[STATE] Window visible after redisplay: {is_visible}")
                logger.info(f"Otter redisplayed after workspace switch (state: {self.app.otter_state}, visible: {is_visible})")

                # Bring the selected app window to front of other apps (below otter which has keep_above)
                # This ensures the app is reordered to the top of other windows on the workspace
                if hasattr(self, '_pending_window_xid_for_stacking') and self._pending_window_xid_for_stacking:
                    GLib.timeout_add(50, lambda: self._bring_window_to_front_after_otter_display(self._pending_window_xid_for_stacking))
                    self._pending_window_xid_for_stacking = None
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

    def _bring_window_to_front_after_otter_display(self, xid: int) -> bool:
        """Bring selected app window to front after otter is displayed

        This ensures the app is on top of other windows (but below otter which has keep_above).
        Called with a delay after otter is redisplayed to avoid z-order conflicts.

        Args:
            xid: Window XID

        Returns:
            False (don't repeat)
        """
        try:
            window = self.app.window_manager.get_window_by_xid(xid)
            if not window:
                logger.debug(f"Window {xid} no longer exists")
                return False

            # Validate window is still valid
            if not self.app.window_manager.window_is_valid(window):
                logger.debug(f"Window {xid} is no longer valid")
                return False

            # Use current time instead of event time
            import time
            timestamp = int(time.time() * 1000) & 0xFFFFFFFF

            try:
                window.activate(timestamp)
                logger.debug(f"Brought window {xid} to front of other apps after otter display")
            except Exception as e:
                logger.error(f"Error bringing window {xid} to front: {e}")
        except Exception as e:
            logger.error(f"Error in _bring_window_to_front_after_otter_display: {e}")

        return False

    def on_destroy(self, widget):
        """Handle window destruction
        
        Args:
            widget: GTK widget
        """
        self.app.cleanup()
