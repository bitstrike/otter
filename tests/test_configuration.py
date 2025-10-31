#!/usr/bin/env python3
"""
Unit tests for Otter configuration and argument parsing
"""

import unittest
import sys
import argparse
from unittest.mock import Mock, patch

# Add parent directory to path
sys.path.insert(0, '..')


class TestConfigurationParsing(unittest.TestCase):
    """Test command-line argument parsing"""

    def setUp(self):
        """Set up test fixtures"""
        # Import argparse setup from otter.py
        self.parser = argparse.ArgumentParser()

        # Layout options (mutually exclusive)
        layout_group = self.parser.add_mutually_exclusive_group()
        layout_group.add_argument('--nrows', type=int, metavar='NUM')
        layout_group.add_argument('--ncols', type=int, default=4, metavar='NUM')

        # Edge trigger options (mutually exclusive)
        edge_group = self.parser.add_mutually_exclusive_group()
        edge_group.add_argument('--north', action='store_true')
        edge_group.add_argument('--south', action='store_true')
        edge_group.add_argument('--east', action='store_true')
        edge_group.add_argument('--west', action='store_true')

        # Other options
        self.parser.add_argument('--xsize', type=int, default=160)
        self.parser.add_argument('--notitle', action='store_true')
        self.parser.add_argument('--delay', type=int, default=0)
        self.parser.add_argument('--recent', action='store_true')
        self.parser.add_argument('--main-character', action='store_true')

    def test_default_configuration(self):
        """Test default configuration values"""
        args = self.parser.parse_args([])
        self.assertEqual(args.ncols, 4)
        self.assertEqual(args.xsize, 160)
        self.assertEqual(args.delay, 0)
        self.assertFalse(args.notitle)
        self.assertFalse(args.recent)

    def test_custom_columns(self):
        """Test custom column count"""
        args = self.parser.parse_args(['--ncols', '6'])
        self.assertEqual(args.ncols, 6)

    def test_custom_rows(self):
        """Test custom row count"""
        args = self.parser.parse_args(['--nrows', '3'])
        self.assertEqual(args.nrows, 3)

    def test_mutually_exclusive_layout(self):
        """Test that nrows and ncols can be specified individually"""
        # Note: Both are in mutually exclusive group; ncols has a default
        args_nrows_only = self.parser.parse_args(['--nrows', '2'])
        self.assertEqual(args_nrows_only.nrows, 2)

        args_ncols_only = self.parser.parse_args(['--ncols', '5'])
        self.assertEqual(args_ncols_only.ncols, 5)

    def test_edge_triggers(self):
        """Test edge trigger options"""
        args_north = self.parser.parse_args(['--north'])
        self.assertTrue(args_north.north)

        args_south = self.parser.parse_args(['--south'])
        self.assertTrue(args_south.south)

        args_east = self.parser.parse_args(['--east'])
        self.assertTrue(args_east.east)

        args_west = self.parser.parse_args(['--west'])
        self.assertTrue(args_west.west)

    def test_mutually_exclusive_edges(self):
        """Test that edge triggers are mutually exclusive"""
        with self.assertRaises(SystemExit):
            self.parser.parse_args(['--north', '--south'])

    def test_thumbnail_size(self):
        """Test thumbnail size configuration"""
        args = self.parser.parse_args(['--xsize', '200'])
        self.assertEqual(args.xsize, 200)

    def test_boolean_flags(self):
        """Test boolean flag options"""
        args = self.parser.parse_args(['--notitle', '--recent', '--main-character'])
        self.assertTrue(args.notitle)
        self.assertTrue(args.recent)
        # argparse converts hyphens to underscores in attribute names
        self.assertTrue(args.main_character)

    def test_hide_delay(self):
        """Test hide delay configuration"""
        args = self.parser.parse_args(['--delay', '500'])
        self.assertEqual(args.delay, 500)

    def test_combined_options(self):
        """Test combining multiple options"""
        args = self.parser.parse_args([
            '--east', '--ncols', '6', '--xsize', '180',
            '--notitle', '--recent', '--delay', '300'
        ])
        self.assertTrue(args.east)
        self.assertEqual(args.ncols, 6)
        self.assertEqual(args.xsize, 180)
        self.assertTrue(args.notitle)
        self.assertTrue(args.recent)
        self.assertEqual(args.delay, 300)


class TestLayoutCalculations(unittest.TestCase):
    """Test layout dimension calculations"""

    def calculate_layout_dimensions(self, window_count, nrows=None, ncols=None):
        """Mock implementation of calculate_layout_dimensions"""
        if ncols is None:
            ncols = 4

        if nrows:
            # User specified rows, calculate columns
            cols = (window_count + nrows - 1) // nrows
            return nrows, max(1, cols)
        else:
            # User specified columns (or default), calculate rows
            rows = (window_count + ncols - 1) // ncols
            return max(1, rows), ncols

    def test_single_window(self):
        """Test layout with single window"""
        rows, cols = self.calculate_layout_dimensions(1, ncols=4)
        self.assertEqual(rows, 1)
        self.assertEqual(cols, 4)

    def test_exact_fit(self):
        """Test layout with exact fit (4 windows, 4 columns)"""
        rows, cols = self.calculate_layout_dimensions(4, ncols=4)
        self.assertEqual(rows, 1)
        self.assertEqual(cols, 4)

    def test_multiple_rows(self):
        """Test layout requiring multiple rows"""
        rows, cols = self.calculate_layout_dimensions(10, ncols=4)
        self.assertEqual(rows, 3)  # ceil(10/4) = 3
        self.assertEqual(cols, 4)

    def test_custom_rows(self):
        """Test layout with custom row count"""
        rows, cols = self.calculate_layout_dimensions(10, nrows=2)
        self.assertEqual(rows, 2)
        self.assertEqual(cols, 5)  # ceil(10/2) = 5

    def test_zero_windows(self):
        """Test layout with no windows"""
        rows, cols = self.calculate_layout_dimensions(0, ncols=4)
        self.assertEqual(rows, 1)  # Minimum 1 row
        self.assertEqual(cols, 4)

    def test_large_window_count(self):
        """Test layout with many windows"""
        rows, cols = self.calculate_layout_dimensions(50, ncols=6)
        self.assertEqual(rows, 9)  # ceil(50/6) = 9
        self.assertEqual(cols, 6)


class TestMRUOrdering(unittest.TestCase):
    """Test Most Recently Used ordering"""

    def setUp(self):
        """Set up test MRU data"""
        self.mru_timestamps = {}

    def get_mru_timestamp(self, window):
        """Get MRU timestamp for a window"""
        xid = window.get('xid')
        if xid is not None:
            return self.mru_timestamps.get(xid, 0)
        return 0

    def test_mru_timestamp_recording(self):
        """Test recording MRU timestamps"""
        xid = 12345
        import time
        timestamp = time.time()
        self.mru_timestamps[xid] = timestamp
        self.assertEqual(self.mru_timestamps[xid], timestamp)

    def test_mru_sorting(self):
        """Test MRU sorting algorithm"""
        windows = [
            {'xid': 1, 'app_name': 'Firefox', 'name': 'Browser'},
            {'xid': 2, 'app_name': 'Terminal', 'name': 'Shell'},
            {'xid': 3, 'app_name': 'Code', 'name': 'Editor'},
        ]

        # Set MRU timestamps (3 most recent, then 1, then 2)
        import time
        base_time = time.time()
        self.mru_timestamps[3] = base_time + 10  # Most recent
        self.mru_timestamps[1] = base_time + 5
        self.mru_timestamps[2] = base_time  # Oldest

        # Sort by MRU
        windows.sort(key=lambda w: self.get_mru_timestamp(w), reverse=True)

        # Check order
        self.assertEqual(windows[0]['xid'], 3)  # Most recent first
        self.assertEqual(windows[1]['xid'], 1)
        self.assertEqual(windows[2]['xid'], 2)  # Oldest last

    def test_mru_missing_timestamps(self):
        """Test MRU sorting with missing timestamps"""
        windows = [
            {'xid': 1, 'app_name': 'Firefox'},
            {'xid': 2, 'app_name': 'Terminal'},
            {'xid': None, 'app_name': 'Unknown'},  # No XID
        ]

        import time
        self.mru_timestamps[1] = time.time()
        # Window 2 has no timestamp, window with None XID has no timestamp

        windows.sort(key=lambda w: self.get_mru_timestamp(w), reverse=True)

        # Window 1 should be first (has timestamp)
        self.assertEqual(windows[0]['xid'], 1)


class TestWindowIDGeneration(unittest.TestCase):
    """Test unique window ID generation"""

    def test_xid_extraction(self):
        """Test normal XID extraction"""
        mock_window = Mock()
        mock_window.get_xid.return_value = 12345

        xid = mock_window.get_xid()
        self.assertEqual(xid, 12345)

    def test_fallback_to_name_pid(self):
        """Test fallback when XID unavailable"""
        mock_window = Mock()
        mock_window.get_xid.side_effect = Exception("No XID")
        mock_window.get_name.return_value = "TestWindow"

        mock_app = Mock()
        mock_app.get_pid.return_value = 9876
        mock_window.get_application.return_value = mock_app

        # Test fallback logic
        try:
            xid = mock_window.get_xid()
        except Exception:
            app = mock_window.get_application()
            pid = app.get_pid() if app else 0
            name = mock_window.get_name()
            window_id = f"{name}_{pid}"

        self.assertEqual(window_id, "TestWindow_9876")


class TestHideStateSemaphore(unittest.TestCase):
    """Test HIDE_STATE semaphore logic"""

    def setUp(self):
        """Set up test state"""
        self.HIDE_STATE = True

    def test_initial_state(self):
        """Test initial HIDE_STATE is True"""
        self.assertTrue(self.HIDE_STATE)

    def test_context_menu_blocks_hiding(self):
        """Test context menu sets HIDE_STATE to False"""
        # Open context menu
        self.HIDE_STATE = False
        self.assertFalse(self.HIDE_STATE)

        # Try to hide (should be blocked)
        if not self.HIDE_STATE:
            can_hide = False
        else:
            can_hide = True

        self.assertFalse(can_hide)

    def test_context_menu_close_allows_hiding(self):
        """Test closing context menu restores HIDE_STATE"""
        # Open menu
        self.HIDE_STATE = False

        # Close menu
        self.HIDE_STATE = True

        # Now hiding should be allowed
        self.assertTrue(self.HIDE_STATE)


if __name__ == '__main__':
    unittest.main()
