"""Shared window move/resize helper used by ContextMenu and click handlers

Provides robust helpers to resize and move windows to the current display
and workspace. Designed to be defensive (validate window is still valid,
handle maximized state) and to avoid resizing when the window is already
appropriately sized on the current display (in which case we only raise it).
"""

import logging
from gi.repository import GLib, Wnck

logger = logging.getLogger(__name__)


class WindowOperator:
    @staticmethod
    def _is_on_monitor(window_geom, monitor_geom):
        x, y, w, h = window_geom
        return (x >= monitor_geom['x'] and x < monitor_geom['x'] + monitor_geom['width'] and
                y >= monitor_geom['y'] and y < monitor_geom['y'] + monitor_geom['height'])

    @staticmethod
    def _is_size_close(curr_w, curr_h, target_w, target_h, tol=0.10):
        if target_w <= 0 or target_h <= 0:
            return False
        return (abs(curr_w - target_w) / max(target_w, 1) <= tol and
                abs(curr_h - target_h) / max(target_h, 1) <= tol)

    @staticmethod
    def resize_to_display(window, monitor_geom):
        """Resize window to 80% of monitor size. Returns True on success."""
        try:
            new_width = int(monitor_geom['width'] * 0.8)
            new_height = int(monitor_geom['height'] * 0.8)

            # Check current size and avoid forcing geometry if already close
            try:
                current_geom = window.get_geometry()
                curr_w = current_geom[2]
                curr_h = current_geom[3]
                if WindowOperator._is_size_close(curr_w, curr_h, new_width, new_height, tol=0.05):
                    logger.debug(f"WindowOperator: size already close ({curr_w}x{curr_h}), skipping resize")
                    return True
            except Exception:
                # If we can't get current geometry, proceed with resize
                pass

            logger.debug(f"WindowOperator: resizing to {new_width}x{new_height}")

            window.set_geometry(
                Wnck.WindowGravity.CURRENT,
                Wnck.WindowMoveResizeMask.WIDTH | Wnck.WindowMoveResizeMask.HEIGHT,
                -1, -1,
                new_width, new_height
            )

            return True
        except Exception as e:
            logger.debug(f"WindowOperator.resize_to_display failed: {e}")
            return False

    @staticmethod
    def move_to_display_center(window, monitor_geom):
        """Center the window on monitor (position-only)."""
        try:
            try:
                current_geom = window.get_geometry()
                curr_w = current_geom[2]
                curr_h = current_geom[3]
            except Exception:
                curr_w = int(monitor_geom['width'] * 0.8)
                curr_h = int(monitor_geom['height'] * 0.8)

            new_x = monitor_geom['x'] + (monitor_geom['width'] - curr_w) // 2
            new_y = monitor_geom['y'] + (monitor_geom['height'] - curr_h) // 2

            logger.debug(f"WindowOperator: moving to center ({new_x},{new_y})")

            window.set_geometry(
                Wnck.WindowGravity.CURRENT,
                Wnck.WindowMoveResizeMask.X | Wnck.WindowMoveResizeMask.Y,
                new_x, new_y,
                -1, -1
            )

            return True
        except Exception as e:
            logger.debug(f"WindowOperator.move_to_display_center failed: {e}")
            return False

    @staticmethod
    def resize_and_move_to_display(window, monitor_geom, app=None, window_manager=None, hide_callback=None):
        """High-level sequence: move window to current workspace (if provided),
        unmaximize if needed, resize to monitor, move to center, activate and then
        optionally call hide_callback (e.g., to hide Otter).

        This method performs timeouts similar to other code paths so the WM
        and compositor can process requests.
        """
        try:
            # Validate window
            if window_manager and not window_manager.window_is_valid(window):
                logger.debug("WindowOperator: window no longer valid")
                return False

            # Move to current workspace if window_manager available
            try:
                if window_manager and window_manager.screen_wnck:
                    active_ws = window_manager.screen_wnck.get_active_workspace()
                    if active_ws:
                        try:
                            current_ws = window.get_workspace()
                            if current_ws != active_ws:
                                window.move_to_workspace(active_ws)
                                logger.debug("WindowOperator: moved window to active workspace")
                        except Exception as e:
                            logger.debug(f"Could not move window to workspace: {e}")
            except Exception as e:
                logger.debug(f"Workspace move check failed: {e}")

            # If maximized, unmaximize first
            try:
                if hasattr(window, 'is_maximized') and window.is_maximized():
                    window.unmaximize()
                    logger.debug("WindowOperator: unmaximized window")
            except Exception:
                pass

            # Resize
            success = WindowOperator.resize_to_display(window, monitor_geom)
            if not success:
                logger.debug("WindowOperator: resize failed, aborting sequence")
                return False

            # After a short delay, move to center (one-shot)
            def _move_once():
                try:
                    WindowOperator.move_to_display_center(window, monitor_geom)
                except Exception as e:
                    logger.debug(f"WindowOperator._move_once error: {e}")
                return False

            GLib.timeout_add(150, _move_once)

            # After another delay, activate and optionally hide Otter
            def _activate_and_hide():
                try:
                    import time as _t
                    if window_manager and not window_manager.window_is_valid(window):
                        return False

                    timestamp = int(_t.time() * 1000) & 0xFFFFFFFF
                    try:
                        window.activate(timestamp)
                        logger.debug("WindowOperator: activated window after resize/move")
                    except Exception as e:
                        logger.debug(f"WindowOperator: activation failed: {e}")

                    if hide_callback:
                        try:
                            hide_callback()
                        except Exception:
                            pass
                except Exception as e:
                    logger.debug(f"WindowOperator._activate_and_hide error: {e}")
                return False

            GLib.timeout_add(300, _activate_and_hide)

            return True

        except Exception as e:
            logger.debug(f"WindowOperator.resize_and_move_to_display error: {e}")
            return False
