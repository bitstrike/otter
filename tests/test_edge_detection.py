#!/usr/bin/env python3
"""
Unit tests for edge detection and mouse position logic
"""

import unittest
from unittest.mock import Mock, MagicMock


class TestEdgeDetection(unittest.TestCase):
    """Test edge trigger detection"""

    def setUp(self):
        """Set up test monitor configuration"""
        self.monitor = {
            'x': 0,
            'y': 0,
            'width': 1920,
            'height': 1080
        }
        self.edge_trigger = 'north'  # default
        self.trigger_threshold = 5

    def check_edge_trigger(self, x, y):
        """Mock edge trigger detection logic"""
        mon_x = self.monitor['x']
        mon_y = self.monitor['y']
        mon_width = self.monitor['width']
        mon_height = self.monitor['height']

        if self.edge_trigger == 'north':
            return y <= mon_y + self.trigger_threshold
        elif self.edge_trigger == 'south':
            return y >= (mon_y + mon_height - self.trigger_threshold)
        elif self.edge_trigger == 'east':
            return x >= (mon_x + mon_width - self.trigger_threshold)
        elif self.edge_trigger == 'west':
            return x <= mon_x + self.trigger_threshold
        return False

    def test_north_edge_detection(self):
        """Test north edge trigger"""
        self.edge_trigger = 'north'
        self.assertTrue(self.check_edge_trigger(960, 0))
        self.assertTrue(self.check_edge_trigger(960, 5))
        self.assertFalse(self.check_edge_trigger(960, 6))
        self.assertFalse(self.check_edge_trigger(960, 100))

    def test_south_edge_detection(self):
        """Test south edge trigger"""
        self.edge_trigger = 'south'
        self.assertTrue(self.check_edge_trigger(960, 1080))
        self.assertTrue(self.check_edge_trigger(960, 1075))
        self.assertFalse(self.check_edge_trigger(960, 1074))
        self.assertFalse(self.check_edge_trigger(960, 500))

    def test_east_edge_detection(self):
        """Test east edge trigger"""
        self.edge_trigger = 'east'
        self.assertTrue(self.check_edge_trigger(1920, 540))
        self.assertTrue(self.check_edge_trigger(1915, 540))
        self.assertFalse(self.check_edge_trigger(1914, 540))
        self.assertFalse(self.check_edge_trigger(1000, 540))

    def test_west_edge_detection(self):
        """Test west edge trigger"""
        self.edge_trigger = 'west'
        self.assertTrue(self.check_edge_trigger(0, 540))
        self.assertTrue(self.check_edge_trigger(5, 540))
        self.assertFalse(self.check_edge_trigger(6, 540))
        self.assertFalse(self.check_edge_trigger(100, 540))

    def test_no_trigger_in_center(self):
        """Test no trigger in center of screen"""
        for edge in ['north', 'south', 'east', 'west']:
            self.edge_trigger = edge
            # Center of screen should never trigger
            self.assertFalse(self.check_edge_trigger(960, 540))


class TestMultiMonitorDetection(unittest.TestCase):
    """Test multi-monitor cursor detection"""

    def setUp(self):
        """Set up multi-monitor configuration"""
        self.monitors = [
            {'x': 0, 'y': 0, 'width': 1920, 'height': 1080},      # Left monitor
            {'x': 1920, 'y': 0, 'width': 1920, 'height': 1080},   # Right monitor
        ]

    def get_monitor_at_position(self, x, y):
        """Determine which monitor contains the cursor"""
        for monitor in self.monitors:
            mon_x = monitor['x']
            mon_y = monitor['y']
            mon_width = monitor['width']
            mon_height = monitor['height']

            if (mon_x <= x < mon_x + mon_width and
                mon_y <= y < mon_y + mon_height):
                return monitor
        return None

    def test_cursor_on_left_monitor(self):
        """Test cursor detection on left monitor"""
        monitor = self.get_monitor_at_position(960, 540)
        self.assertIsNotNone(monitor)
        self.assertEqual(monitor['x'], 0)

    def test_cursor_on_right_monitor(self):
        """Test cursor detection on right monitor"""
        monitor = self.get_monitor_at_position(2880, 540)
        self.assertIsNotNone(monitor)
        self.assertEqual(monitor['x'], 1920)

    def test_cursor_at_monitor_boundary(self):
        """Test cursor at exact monitor boundary"""
        # At x=1920, should be on right monitor (left edge)
        monitor = self.get_monitor_at_position(1920, 540)
        self.assertIsNotNone(monitor)
        self.assertEqual(monitor['x'], 1920)

    def test_cursor_outside_all_monitors(self):
        """Test cursor position outside all monitors"""
        monitor = self.get_monitor_at_position(-100, 540)
        self.assertIsNone(monitor)

        monitor = self.get_monitor_at_position(5000, 540)
        self.assertIsNone(monitor)


class TestMouseInWindow(unittest.TestCase):
    """Test mouse-in-window detection"""

    def setUp(self):
        """Set up window bounds"""
        self.window_x = 100
        self.window_y = 100
        self.window_width = 800
        self.window_height = 600
        self.buffer = 10

    def mouse_in_window(self, x, y):
        """Check if mouse is within window bounds (with buffer)"""
        return (self.window_x - self.buffer <= x <= self.window_x + self.window_width + self.buffer and
                self.window_y - self.buffer <= y <= self.window_y + self.window_height + self.buffer)

    def test_mouse_inside_window(self):
        """Test mouse clearly inside window"""
        self.assertTrue(self.mouse_in_window(450, 400))

    def test_mouse_outside_window(self):
        """Test mouse clearly outside window"""
        self.assertFalse(self.mouse_in_window(50, 50))
        self.assertFalse(self.mouse_in_window(1000, 800))

    def test_mouse_in_buffer_zone(self):
        """Test mouse in buffer zone (still considered inside)"""
        # Just outside window but within buffer
        self.assertTrue(self.mouse_in_window(95, 400))  # 5px left of window
        self.assertTrue(self.mouse_in_window(905, 400))  # 5px right of window

    def test_mouse_outside_buffer_zone(self):
        """Test mouse outside buffer zone"""
        self.assertFalse(self.mouse_in_window(89, 400))  # 11px left (outside buffer)
        self.assertFalse(self.mouse_in_window(911, 400))  # 11px right (outside buffer)


class TestWindowPositioning(unittest.TestCase):
    """Test smart window positioning logic"""

    def setUp(self):
        """Set up monitor and window dimensions"""
        self.monitor = {
            'x': 0,
            'y': 0,
            'width': 1920,
            'height': 1080
        }
        self.window_width = 800
        self.window_height = 600
        self.cursor_x = 960
        self.cursor_y = 100

    def calculate_position(self):
        """Calculate smart window position near cursor"""
        # Start with cursor position
        x = self.cursor_x - (self.window_width // 2)
        y = self.cursor_y

        # Edge-aware adjustment
        mon_x = self.monitor['x']
        mon_y = self.monitor['y']
        mon_width = self.monitor['width']
        mon_height = self.monitor['height']

        # Keep within monitor bounds
        if x < mon_x:
            x = mon_x
        if x + self.window_width > mon_x + mon_width:
            x = mon_x + mon_width - self.window_width

        if y < mon_y:
            y = mon_y
        if y + self.window_height > mon_y + mon_height:
            y = mon_y + mon_height - self.window_height

        return x, y

    def test_position_near_cursor(self):
        """Test positioning near cursor in center of screen"""
        x, y = self.calculate_position()
        # Should be centered horizontally around cursor
        self.assertEqual(x, 960 - 400)  # cursor - half window width
        self.assertEqual(y, 100)

    def test_position_at_left_edge(self):
        """Test positioning when cursor near left edge"""
        self.cursor_x = 50
        x, y = self.calculate_position()
        # Should be clamped to monitor edge
        self.assertEqual(x, 0)

    def test_position_at_right_edge(self):
        """Test positioning when cursor near right edge"""
        self.cursor_x = 1900
        x, y = self.calculate_position()
        # Should be adjusted to fit within monitor
        self.assertEqual(x, 1920 - 800)

    def test_position_at_bottom_edge(self):
        """Test positioning when cursor near bottom"""
        self.cursor_y = 1050
        x, y = self.calculate_position()
        # Should be adjusted to fit within monitor
        self.assertEqual(y, 1080 - 600)


if __name__ == '__main__':
    unittest.main()
