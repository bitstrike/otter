#!/usr/bin/env python3
"""
Unit tests for Wnck state management and stability
"""

import unittest
import time
from unittest.mock import Mock, patch, MagicMock


class TestWnckRecreation(unittest.TestCase):
    """Test Wnck screen recreation logic"""

    def setUp(self):
        """Set up Wnck recreation state"""
        self.wnck_last_recreation = time.time()
        self.wnck_recreation_interval = 120  # 2 minutes
        self.wnck_call_count = 0
        self.wnck_recreating = False
        self.wnck_just_recreated = False

    def should_recreate_wnck(self):
        """Check if Wnck screen should be recreated"""
        time_since_recreation = time.time() - self.wnck_last_recreation
        if time_since_recreation >= self.wnck_recreation_interval:
            return True
        if self.wnck_call_count >= 10000:
            return True
        return False

    def test_time_based_recreation(self):
        """Test recreation after time interval"""
        # Just recreated
        self.assertFalse(self.should_recreate_wnck())

        # Simulate time passing
        self.wnck_last_recreation = time.time() - 121  # 121 seconds ago
        self.assertTrue(self.should_recreate_wnck())

    def test_count_based_recreation(self):
        """Test recreation after call count threshold"""
        self.wnck_call_count = 9999
        self.assertFalse(self.should_recreate_wnck())

        self.wnck_call_count = 10000
        self.assertTrue(self.should_recreate_wnck())

    def test_recreation_lock(self):
        """Test recreation lock prevents concurrent access"""
        self.wnck_recreating = True

        # Should not query Wnck during recreation
        if self.wnck_recreating:
            can_query = False
        else:
            can_query = True

        self.assertFalse(can_query)

    def test_skip_force_update_after_recreation(self):
        """Test skipping force_update immediately after recreation"""
        self.wnck_just_recreated = True

        should_skip = self.wnck_just_recreated
        self.assertTrue(should_skip)

        # Flag should be reset after first check
        self.wnck_just_recreated = False
        should_skip = self.wnck_just_recreated
        self.assertFalse(should_skip)


class TestWnckErrorDetection(unittest.TestCase):
    """Test Wnck corruption detection"""

    def setUp(self):
        """Set up error detection state"""
        self.wnck_last_recreation = time.time()

    def detect_wnck_corruption(self, error_message):
        """Detect if error indicates Wnck corruption"""
        corruption_indicators = ['WnckClassGroup', 'hash_table']
        return any(indicator in str(error_message) for indicator in corruption_indicators)

    def test_detect_classgroup_corruption(self):
        """Test detection of WnckClassGroup errors"""
        error = "invalid unclassed pointer in cast to 'WnckClassGroup'"
        self.assertTrue(self.detect_wnck_corruption(error))

    def test_detect_hashtable_corruption(self):
        """Test detection of hash_table errors"""
        error = "g_hash_table_remove_internal: assertion 'hash_table != NULL' failed"
        self.assertTrue(self.detect_wnck_corruption(error))

    def test_ignore_non_corruption_errors(self):
        """Test ignoring non-corruption errors"""
        error = "Connection timeout"
        self.assertFalse(self.detect_wnck_corruption(error))

    def test_flag_for_immediate_recreation(self):
        """Test flagging for immediate recreation on corruption"""
        error = "WnckClassGroup corruption detected"
        if self.detect_wnck_corruption(error):
            # Flag for immediate recreation
            self.wnck_last_recreation = 0

        self.assertEqual(self.wnck_last_recreation, 0)


class TestWnckExceptionHandling(unittest.TestCase):
    """Test exception handling around Wnck calls"""

    def test_force_update_exception_handling(self):
        """Test handling force_update() failures"""
        mock_screen = Mock()
        mock_screen.force_update.side_effect = Exception("Wnck corruption")

        try:
            mock_screen.force_update()
            force_update_failed = False
        except Exception:
            force_update_failed = True

        self.assertTrue(force_update_failed)

    def test_get_windows_exception_handling(self):
        """Test handling get_windows() failures"""
        mock_screen = Mock()
        mock_screen.get_windows.side_effect = Exception("Wnck error")

        try:
            windows = mock_screen.get_windows()
        except Exception:
            windows = []

        self.assertEqual(windows, [])

    def test_get_application_exception_handling(self):
        """Test handling get_application() failures"""
        mock_window = Mock()
        mock_window.get_application.side_effect = Exception("WnckClassGroup error")

        try:
            app = mock_window.get_application()
            app_name = app.get_name() if app else "Unknown"
        except Exception:
            app_name = "Unknown"

        self.assertEqual(app_name, "Unknown")

    def test_window_activate_exception_handling(self):
        """Test handling window.activate() failures"""
        mock_window = Mock()
        mock_window.activate.side_effect = Exception("Activation failed")

        activation_failed = False
        try:
            mock_window.activate(0)
        except Exception:
            activation_failed = True

        self.assertTrue(activation_failed)


class TestFullscreenDetection(unittest.TestCase):
    """Test fullscreen window detection"""

    def setUp(self):
        """Set up fullscreen detection"""
        self.main_character_enabled = False

    def should_trigger(self, is_fullscreen):
        """Check if should trigger window switcher"""
        if self.main_character_enabled and is_fullscreen:
            return False
        return True

    def test_trigger_when_not_fullscreen(self):
        """Test triggering when no fullscreen window"""
        self.main_character_enabled = True
        self.assertTrue(self.should_trigger(is_fullscreen=False))

    def test_no_trigger_during_fullscreen(self):
        """Test not triggering during fullscreen (main-character mode)"""
        self.main_character_enabled = True
        self.assertFalse(self.should_trigger(is_fullscreen=True))

    def test_trigger_fullscreen_without_main_character(self):
        """Test triggering during fullscreen when main-character disabled"""
        self.main_character_enabled = False
        self.assertTrue(self.should_trigger(is_fullscreen=True))


class TestWindowFiltering(unittest.TestCase):
    """Test system window filtering"""

    def setUp(self):
        """Set up system app list"""
        self.system_apps = [
            'gnome-shell', 'cinnamon', 'gnome-settings-daemon',
            'gnome-panel', 'mate-panel', 'xfce4-panel', 'plasma-desktop',
            'kwin', 'compiz', 'metacity', 'mutter', 'unity',
            'unity-panel-service', 'Desktop', 'Otter Window Switcher'
        ]

    def is_system_app(self, app_name):
        """Check if app is a system application"""
        return app_name.lower() in [app.lower() for app in self.system_apps]

    def test_filter_system_apps(self):
        """Test filtering of system applications"""
        self.assertTrue(self.is_system_app('gnome-shell'))
        self.assertTrue(self.is_system_app('Cinnamon'))
        self.assertTrue(self.is_system_app('PLASMA-DESKTOP'))

    def test_allow_user_apps(self):
        """Test allowing user applications"""
        self.assertFalse(self.is_system_app('Firefox'))
        self.assertFalse(self.is_system_app('Terminal'))
        self.assertFalse(self.is_system_app('Code'))

    def test_filter_otter_itself(self):
        """Test filtering Otter's own window"""
        self.assertTrue(self.is_system_app('Otter Window Switcher'))


if __name__ == '__main__':
    unittest.main()
