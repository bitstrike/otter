#!/usr/bin/env python3

"""Otter Window Switcher - Main application"""

import os
os.environ['NO_AT_BRIDGE'] = '1'

import logging
import sys
import signal
import time
from enum import Enum
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Wnck", "3.0")
from gi.repository import Gtk, GLib

from .config import parse_arguments, validate_ignore_list, args_to_config
from .windows import WindowManager
from .screenshots import ScreenshotManager
from .input import EdgeDetector, ShiftMonitor, EventHandler
from .ui import SwitcherWindow, ContextMenu
from .tray import OtterTrayIcon

logger = logging.getLogger(__name__)


class OtterState(Enum):
    """Otter window state machine states"""
    HIDDEN = "hidden"      # Window hidden, edge detector active
    VISIBLE = "visible"    # Window shown, edge detector active
    DISABLED = "disabled"  # Window hidden, edge detector ignores triggers


class OtterApp:
    """Main Otter application"""
    
    def __init__(self, config: dict):
        """Initialize application
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        
        # State machine
        self.otter_state = OtterState.HIDDEN
        self.next_show_time = None  # When to transition from DISABLED to VISIBLE
        self.last_show_time = 0  # Track when window was last shown (for grace period)
        self.delayed_hide_id = None
        self.toplist_reset_id = None  # Timer for toplist scroll reset
        self.can_hide = True  # Semaphore for context menu
        
        # Initialize GTK
        Gtk.init()
        
        # Initialize managers
        self.window_manager = WindowManager(config, self._on_window_changed)
        self.screenshot_manager = ScreenshotManager(self.window_manager, config['xsize'])
        
        # Initialize event handler
        self.event_handler = EventHandler(self)
        
        # Initialize UI
        self.switcher_window = SwitcherWindow(
            config,
            self.window_manager,
            self.screenshot_manager,
            self.event_handler
        )
        
        # Make scroll_window accessible to event handler
        self.scroll_window = self.switcher_window.scroll_window
        
        # Initialize context menu
        self.context_menu = ContextMenu(self.window_manager, self.switcher_window, self._on_menu_closed)
        
        # Initialize edge detector
        edge = 'north'
        if config.get('south'):
            edge = 'south'
        elif config.get('east'):
            edge = 'east'
        elif config.get('west'):
            edge = 'west'
        
        self.edge_detector = EdgeDetector(
            edge,
            self._on_edge_trigger,
            self._on_edge_leave,
            config.get('main_character', False),
            config.get('blacklist_apps', [])
        )
        self.edge_detector.window_manager = self.window_manager
        self.edge_detector.switcher_window = self.switcher_window
        self.edge_detector.app = self  # Give edge detector access to state machine
        
        # Initialize shift monitor
        self.shift_monitor = ShiftMonitor(
            config.get('hide_duration', 0),
            self._on_shift_pressed,
            config.get('hide_key')  # Custom keyval from --hidekey
        )
        self.shift_monitor.setup(self.switcher_window.window)
        
        # Start screenshot cache updates
        GLib.timeout_add(5000, self._update_screenshot_cache)
        
        # Start state machine timer (checks every 100ms for DISABLED → VISIBLE transition)
        GLib.timeout_add(100, self._check_state_timer)
        
        # Create system tray icon
        self.tray_icon = OtterTrayIcon(
            self,
            self._on_tray_show,
            self._on_tray_quit
        )
        
        logger.info("Otter application initialized")
    
    def _on_window_changed(self, screen, window=None):
        """Handle window open/close events"""
        # Queue events during DISABLED state (don't process them)
        if self.otter_state == OtterState.DISABLED:
            logger.debug("Window changed event queued (DISABLED state)")
            return
        
        if self.otter_state == OtterState.VISIBLE:
            GLib.idle_add(self._populate_windows)
    
    def _on_edge_trigger(self):
        """Handle edge trigger - transition HIDDEN → VISIBLE"""
        if self.otter_state == OtterState.HIDDEN:
            self.show_window()
    
    def _on_edge_leave(self):
        """Handle edge leave - transition VISIBLE → HIDDEN"""
        logger.debug(f"[STATE] _on_edge_leave called, current state: {self.otter_state}")
        if self.otter_state == OtterState.VISIBLE:
            self.hide_window()
    
    def _on_shift_pressed(self, keyname: str = "Shift"):
        """Handle shift key press - transition VISIBLE → DISABLED
        
        Args:
            keyname: Name of the shift key pressed (Shift_L or Shift_R)
        """
        if self.otter_state == OtterState.VISIBLE:
            hide_duration = self.config.get('hide_duration', 0)
            print(f"🔽 SHIFT PRESSED - Hiding window for {hide_duration}s")
            logger.debug(f"SHIFT PRESSED - {keyname} - Transitioning to DISABLED for {hide_duration}s")
            
            # Transition to DISABLED state
            self.otter_state = OtterState.DISABLED
            self.next_show_time = time.time() + hide_duration
            
            # Update tray icon to show disabled state
            if hasattr(self, 'tray_icon'):
                self.tray_icon.update_for_state(self.otter_state)
            
            # Hide the window
            if self.switcher_window and self.switcher_window.window:
                self.switcher_window.window.hide()
                # Force GTK to process the hide event
                while Gtk.events_pending():
                    Gtk.main_iteration()
    
    def _check_state_timer(self) -> bool:
        """Check state machine timer - handles DISABLED → HIDDEN transition
        
        Returns:
            True to continue timer
        """
        if self.otter_state == OtterState.DISABLED and self.next_show_time is not None:
            current_time = time.time()
            if current_time >= self.next_show_time:
                print("⏰ Shift hide timeout - Re-enabling edge detection")
                logger.debug("State timer: DISABLED → HIDDEN transition")
                
                # Transition to HIDDEN state (not VISIBLE!)
                # Window stays hidden until mouse reaches edge again
                self.otter_state = OtterState.HIDDEN
                self.next_show_time = None
                
                # Update tray icon to show normal state
                if hasattr(self, 'tray_icon'):
                    self.tray_icon.update_for_state(self.otter_state)
                
                # Don't show the window - let edge detector handle it
                # This allows user to work near the edge without interference
                logger.debug("Edge detection re-enabled, window remains hidden until edge trigger")
        
        return True  # Continue timer
    
    def _on_menu_closed(self):
        """Handle context menu closed"""
        self.can_hide = True
    
    def _ensure_window_focus(self) -> bool:
        """Ensure window has keyboard focus for shift key detection
        
        Returns:
            False (don't repeat)
        """
        try:
            if self.switcher_window and self.switcher_window.window:
                window = self.switcher_window.window
                
                # Try grab_focus
                window.grab_focus()
                
                # Try setting focus on the GDK window
                gdk_window = window.get_window()
                if gdk_window:
                    gdk_window.focus(Gtk.get_current_event_time())
                
                logger.debug("Window focus ensured for shift key detection")
        except Exception as e:
            logger.debug(f"Error ensuring window focus: {e}")
        
        return False  # Don't repeat
    
    def _on_tray_show(self):
        """Handle tray icon left-click - show window"""
        logger.debug("Tray icon clicked - showing window")
        if self.otter_state != OtterState.DISABLED:
            self.show_window()
    
    def _on_tray_quit(self):
        """Handle tray quit - exit application"""
        logger.info("Quitting from tray icon")
        self.cleanup()
        Gtk.main_quit()
    
    def _update_screenshot_cache(self) -> bool:
        """Update screenshot cache periodically
        
        Returns:
            True to continue
        """
        try:
            if self.otter_state != OtterState.VISIBLE:
                # Clean up old entries when not visible
                current_windows = self.window_manager.get_user_windows()
                self.screenshot_manager.update_cache(current_windows)
        except Exception as e:
            logger.debug(f"Error updating cache: {e}")
        
        return True
    
    def show_window(self):
        """Show the switcher window - transition to VISIBLE state"""
        try:
            # Don't show if we're in DISABLED state
            if self.otter_state == OtterState.DISABLED:
                logger.debug("Skipping show_window - in DISABLED state")
                return

            logger.debug("Showing window - transitioning to VISIBLE")

            # Transition to VISIBLE state
            self.otter_state = OtterState.VISIBLE
            self.last_show_time = time.time()  # Track when shown for grace period

            # Handle toplist: reset scroll to top if timeout expired
            toplist_duration = self.config.get('toplist_duration', 0)
            if toplist_duration > 0:
                if self.toplist_reset_id:
                    # Timer is still running, keep scroll position (don't reset)
                    logger.debug("Keeping scroll position (toplist timeout still active)")
                else:
                    # Timer expired or not set, reset scroll to top
                    try:
                        adjustment = self.scroll_window.get_vadjustment()
                        if adjustment:
                            adjustment.set_value(0)
                            logger.debug("Reset scroll to top (toplist timeout expired)")
                    except Exception as e:
                        logger.debug(f"Error resetting scroll: {e}")

            # Populate with windows
            self._populate_windows()

            # Show window
            self.switcher_window.show()

            # Focus window for shift key detection
            self.switcher_window.window.present()

            # Try multiple methods to ensure focus
            GLib.idle_add(self._ensure_window_focus)

        except Exception as e:
            logger.error(f"Error showing window: {e}")
    
    def hide_window(self):
        """Hide the switcher window"""
        logger.debug(f"[STATE] hide_window called, can_hide: {self.can_hide}, state: {self.otter_state}")
        if not self.can_hide:
            logger.debug(f"[STATE] hide_window blocked by can_hide flag")
            return
        
        try:
            delay = self.config.get('hide_delay', 0)
            
            if delay > 0:
                # Delayed hide
                if self.delayed_hide_id:
                    GLib.source_remove(self.delayed_hide_id)
                self.delayed_hide_id = GLib.timeout_add(delay, self._do_hide)
                logger.debug(f"[STATE] Scheduled delayed hide ({delay}ms)")
            else:
                # Immediate hide
                self._do_hide()
        
        except Exception as e:
            logger.error(f"Error hiding window: {e}")
    
    def _do_hide(self) -> bool:
        """Actually hide the window - transition to HIDDEN state

        Returns:
            False (don't repeat)
        """
        try:
            logger.debug("Hiding window - transitioning to HIDDEN")

            # Transition to HIDDEN state
            self.otter_state = OtterState.HIDDEN

            # Hide with error handling to prevent BadDrawable crashes
            try:
                self.switcher_window.hide()
            except Exception as e:
                logger.error(f"Error hiding switcher window: {e}")

            self.delayed_hide_id = None

            # Start toplist timeout if enabled
            toplist_duration = self.config.get('toplist_duration', 0)
            if toplist_duration > 0:
                # Cancel any existing timer
                if self.toplist_reset_id:
                    GLib.source_remove(self.toplist_reset_id)

                # Set timer to re-enable scroll reset after duration
                timeout_ms = int(toplist_duration * 1000)
                self.toplist_reset_id = GLib.timeout_add(timeout_ms, self._on_toplist_timeout)
                logger.debug(f"Started toplist timer ({toplist_duration}s)")

        except Exception as e:
            logger.error(f"Error in _do_hide: {e}")

        return False
    
    def _populate_windows(self):
        """Populate window with current windows"""
        try:
            logger.debug(f"_populate_windows called (state={self.otter_state})")
            windows = self.window_manager.get_user_windows()
            self.switcher_window.populate(windows)
        except Exception as e:
            logger.error(f"Error populating windows: {e}")

    def _on_toplist_timeout(self) -> bool:
        """Called when toplist timeout expires - clear the reset ID

        Returns:
            False (don't repeat)
        """
        self.toplist_reset_id = None
        logger.debug("Toplist timeout expired - scroll will reset to top on next show")
        return False

    def show_context_menu(self, xid: int):
        """Show context menu for window
        
        Args:
            xid: Window XID
        """
        self.can_hide = False
        self.context_menu.show(xid)
    
    def list_windows(self):
        """List all windows (for --list option)"""
        # Force update to get current windows
        windows = self.window_manager.get_user_windows(force_update=True)
        
        if not windows:
            print("\nNo windows found.")
            return
        
        print("\nCurrent Windows:")
        print("-" * 80)
        print(f"{'Name':<40} {'XID':<12} {'Type':<15} {'Workspace':<10}")
        print("-" * 80)
        
        for window_info in windows:
            name = window_info.get('name', 'Unknown')[:39]
            xid = window_info.get('xid', 'N/A')
            window_type = window_info.get('window_type', 'Unknown')
            workspace = window_info.get('workspace_name', 'Unknown')
            
            # Match original format - Type column is variable width
            print(f"{name:<40} {str(xid):<12} {window_type} {workspace}")
        
        print("-" * 80)
        print(f"Total: {len(windows)} window(s)")
        print("\nUsage: otter.py --ignore \"Window Name 1,Window Name 2,...\"")
        print("(Window names are case-insensitive)\n")
    
    def run(self):
        """Run the application"""
        try:
            # Preprocess screenshots
            logger.info("Starting startup preprocessing...")
            self.screenshot_manager.preprocess_startup_thumbnails()
            
            # Start edge detection
            self.edge_detector.start()
            
            # Run main loop
            logger.info("Entering main loop")
            Gtk.main()
        
        except KeyboardInterrupt:
            logger.info("Interrupted")
            self.cleanup()
            sys.exit(0)
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            raise
    
    def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up...")
        
        # Stop edge detector
        if hasattr(self, 'edge_detector'):
            self.edge_detector.stop()
        
        # Destroy tray icon
        if hasattr(self, 'tray_icon'):
            self.tray_icon.destroy()
        
        # Clear caches
        if hasattr(self, 'screenshot_manager'):
            self.screenshot_manager.screenshot_cache.clear()
            self.screenshot_manager.last_valid_screenshots.clear()
        
        logger.info("Cleanup complete")


def main():
    """Main entry point"""
    # Parse arguments
    args = parse_arguments()
    
    # Configure logging
    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    elif args.verbose:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    else:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Validate ignore list
    if hasattr(args, 'ignore') and args.ignore:
        validate_ignore_list(args.ignore)
    
    # Convert args to config
    config = args_to_config(args)
    
    # Handle --list
    if args.list:
        app = OtterApp(config)
        app.list_windows()
        sys.exit(0)
    
    # Log configuration
    logger.info("Starting Otter Window Switcher")
    if config['nrows']:
        logger.info(f"Layout: {config['nrows']} rows, {config['xsize']}px width")
    else:
        logger.info(f"Layout: {config['ncols']} columns, {config['xsize']}px width")
    
    edge = 'north'
    if config['south']:
        edge = 'south'
    elif config['east']:
        edge = 'east'
    elif config['west']:
        edge = 'west'
    logger.info(f"Edge: {edge}")
    
    # Handle signals
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        Gtk.main_quit()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and run app
    try:
        app = OtterApp(config)
        app.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
