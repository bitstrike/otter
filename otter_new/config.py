"""Configuration and command-line argument parsing"""

import argparse
import logging
import sys
from typing import Dict, List
import gi

from .constants import DEFAULT_CONFIG

logger = logging.getLogger(__name__)

# Try to import Wnck for validation
try:
    gi.require_version("Gtk", "3.0")
    gi.require_version("Wnck", "3.0")
    from gi.repository import Gtk, Wnck
    WNCK_AVAILABLE = True
except (ValueError, ImportError):
    WNCK_AVAILABLE = False
    Gtk = None
    Wnck = None


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Otter Window Switcher - A mouse-activated window switcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Default: north edge, 4 columns
  %(prog)s --ncols 5                 # 5 columns, auto rows
  %(prog)s --nrows 2                 # 2 rows, auto columns
  %(prog)s --xsize 200               # Larger thumbnails
  %(prog)s --south --recent          # Bottom edge, MRU ordering
  %(prog)s --east --main-character   # Right edge, respect fullscreen
        """)

    # Layout options (mutually exclusive)
    layout_group = parser.add_mutually_exclusive_group()
    layout_group.add_argument(
        '--nrows', type=int, metavar='NUM',
        help='Number of rows (auto-calculates columns)')
    layout_group.add_argument(
        '--ncols', type=int, default=4, metavar='NUM',
        help='Number of columns (auto-calculates rows, default: 4)')

    # Appearance
    parser.add_argument(
        '--xsize', type=int, default=160, metavar='PIXELS',
        help='Thumbnail width in pixels (default: 160)')
    parser.add_argument(
        '--notitle', action='store_true',
        help='Disable title bar')

    # Behavior
    parser.add_argument(
        '--delay', type=int, default=0, metavar='MS',
        help='Delay before hiding in milliseconds (default: 0)')
    parser.add_argument(
        '--hide', type=float, default=0, metavar='SECONDS',
        help='Hide duration when shift pressed (default: 0 = disabled)')
    parser.add_argument(
        '--recent', action='store_true',
        help='Order by most recently used (MRU)')
    parser.add_argument(
        '--main-character', action='store_true',
        help='Disable trigger during fullscreen apps')

    # Edge trigger (mutually exclusive)
    edge_group = parser.add_mutually_exclusive_group()
    edge_group.add_argument(
        '--north', action='store_true',
        help='Trigger at top edge (default)')
    edge_group.add_argument(
        '--south', action='store_true',
        help='Trigger at bottom edge')
    edge_group.add_argument(
        '--east', action='store_true',
        help='Trigger at right edge')
    edge_group.add_argument(
        '--west', action='store_true',
        help='Trigger at left edge')

    # Utilities
    parser.add_argument(
        '--list', action='store_true',
        help='List all windows and exit')
    parser.add_argument(
        '--ignore', type=str, metavar='NAMES',
        help='Comma-separated window names to ignore')

    # Logging
    parser.add_argument(
        '--debug', action='store_true',
        help='Enable debug logging')
    parser.add_argument(
        '--verbose', action='store_true',
        help='Enable verbose logging')

    args = parser.parse_args()

    # Set default edge if none specified
    if not any([args.north, args.south, args.east, args.west]):
        args.north = True

    # Validate arguments
    if args.nrows is not None and args.nrows < 1:
        parser.error("--nrows must be at least 1")
    if args.ncols < 1:
        parser.error("--ncols must be at least 1")
    if args.xsize < 50:
        parser.error("--xsize must be at least 50 pixels")
    if args.xsize > 500:
        parser.error("--xsize should not exceed 500 pixels")
    if args.delay < 0:
        parser.error("--delay must be non-negative")
    if args.delay > 10000:
        parser.error("--delay should not exceed 10000 ms")
    if args.hide < 0:
        parser.error("--hide must be non-negative")
    if args.hide > 60:
        parser.error("--hide should not exceed 60 seconds")

    return args


def validate_ignore_list(ignore_str: str) -> List[str]:
    """Validate ignore list against current windows
    
    Args:
        ignore_str: Comma-separated window names
        
    Returns:
        List of validated window names
        
    Raises:
        SystemExit: If validation fails
    """
    if not ignore_str or not ignore_str.strip():
        return []

    ignore_list = [name.strip() for name in ignore_str.split(',') if name.strip()]
    if not ignore_list:
        return []

    if not WNCK_AVAILABLE:
        logger.warning("Wnck not available - cannot validate ignore list")
        return ignore_list

    try:
        Gtk.init_check([])
        Wnck.set_client_type(Wnck.ClientType.PAGER)
        screen = Wnck.Screen.get_default()

        if not screen:
            logger.warning("Could not get Wnck screen - skipping validation")
            return ignore_list

        screen.force_update()
        windows = screen.get_windows() or []
        available_windows = set()

        for window in windows:
            try:
                name = window.get_name()
                if name:
                    available_windows.add(name)
            except Exception:
                pass

        # Check for missing windows
        not_found = []
        for item in ignore_list:
            found = any(item.lower() == win.lower() for win in available_windows)
            if not found:
                not_found.append(item)

        if not_found:
            available_list = "\n  ".join(sorted(available_windows)) if available_windows else "No windows found"
            error_msg = (
                f"Error: Window names not found in --ignore:\n"
                f"  {chr(10).join('  ' + item for item in not_found)}\n"
                f"\nAvailable windows:\n"
                f"  {available_list}\n"
            )
            logger.error(error_msg)
            sys.exit(1)

        return ignore_list

    except Exception as e:
        logger.warning(f"Could not validate ignore list: {e}")
        return ignore_list


def args_to_config(args: argparse.Namespace) -> Dict:
    """Convert parsed arguments to configuration dictionary
    
    Args:
        args: Parsed command-line arguments
        
    Returns:
        Configuration dictionary
    """
    ignore_list = []
    if hasattr(args, 'ignore') and args.ignore:
        ignore_list = [name.strip() for name in args.ignore.split(',')]

    return {
        'nrows': args.nrows,
        'ncols': args.ncols,
        'xsize': args.xsize,
        'show_title': not args.notitle,
        'hide_delay': args.delay,
        'hide_duration': args.hide,
        'north': args.north,
        'south': args.south,
        'east': args.east,
        'west': args.west,
        'recent': args.recent,
        'main_character': args.main_character,
        'ignore_list': ignore_list,
    }
