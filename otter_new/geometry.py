"""Screen and monitor geometry utilities"""

import logging
from typing import Dict, List, Tuple, Optional
from gi.repository import Gdk

logger = logging.getLogger(__name__)


def get_monitor_at_point(x: int, y: int) -> Optional[Gdk.Monitor]:
    """Get the monitor containing the given point
    
    Args:
        x: X coordinate
        y: Y coordinate
        
    Returns:
        Monitor object or None
    """
    try:
        display = Gdk.Display.get_default()
        if not display:
            return None
        return display.get_monitor_at_point(x, y)
    except Exception as e:
        logger.debug(f"Error getting monitor at point: {e}")
        return None


def get_monitor_geometry(monitor: Gdk.Monitor) -> Dict[str, int]:
    """Get monitor geometry as dictionary
    
    Args:
        monitor: Monitor object
        
    Returns:
        Dictionary with x, y, width, height
    """
    try:
        geometry = monitor.get_geometry()
        return {
            'x': geometry.x,
            'y': geometry.y,
            'width': geometry.width,
            'height': geometry.height,
        }
    except Exception as e:
        logger.error(f"Error getting monitor geometry: {e}")
        return {'x': 0, 'y': 0, 'width': 1920, 'height': 1080}


def get_all_monitors() -> List[Dict[str, int]]:
    """Get geometry for all monitors
    
    Returns:
        List of monitor geometry dictionaries
    """
    monitors = []
    try:
        display = Gdk.Display.get_default()
        if not display:
            return [{'x': 0, 'y': 0, 'width': 1920, 'height': 1080}]
        
        n_monitors = display.get_n_monitors()
        for i in range(n_monitors):
            monitor = display.get_monitor(i)
            if monitor:
                monitors.append(get_monitor_geometry(monitor))
    except Exception as e:
        logger.error(f"Error getting monitors: {e}")
        return [{'x': 0, 'y': 0, 'width': 1920, 'height': 1080}]
    
    return monitors if monitors else [{'x': 0, 'y': 0, 'width': 1920, 'height': 1080}]


def get_pointer_position() -> Tuple[int, int]:
    """Get current mouse pointer position
    
    Returns:
        Tuple of (x, y) coordinates
    """
    try:
        display = Gdk.Display.get_default()
        if not display:
            return (0, 0)
        
        seat = display.get_default_seat()
        if not seat:
            return (0, 0)
        
        pointer = seat.get_pointer()
        if not pointer:
            return (0, 0)
        
        screen, x, y = pointer.get_position()
        return (int(x), int(y))
    except Exception as e:
        logger.debug(f"Error getting pointer position: {e}")
        return (0, 0)


def calculate_layout_dimensions(window_count: int, nrows: Optional[int], ncols: int) -> Tuple[int, int]:
    """Calculate grid layout dimensions
    
    Args:
        window_count: Number of windows to display
        nrows: Fixed number of rows (None for auto)
        ncols: Fixed number of columns
        
    Returns:
        Tuple of (rows, cols)
    """
    if window_count == 0:
        return (1, 1)
    
    if nrows is not None:
        # User specified rows, calculate columns
        cols = max(1, (window_count + nrows - 1) // nrows)
        return (nrows, cols)
    else:
        # User specified columns, calculate rows
        rows = max(1, (window_count + ncols - 1) // ncols)
        return (rows, ncols)


def position_window_at_edge(
    window_width: int,
    window_height: int,
    edge: str,
    monitor: Dict[str, int]
) -> Tuple[int, int]:
    """Calculate window position for given edge
    
    Args:
        window_width: Width of window to position
        window_height: Height of window to position
        edge: Edge name ('north', 'south', 'east', 'west')
        monitor: Monitor geometry dictionary
        
    Returns:
        Tuple of (x, y) position
    """
    mon_x = monitor['x']
    mon_y = monitor['y']
    mon_width = monitor['width']
    mon_height = monitor['height']
    
    if edge == 'north':
        x = mon_x + (mon_width - window_width) // 2
        y = mon_y
    elif edge == 'south':
        x = mon_x + (mon_width - window_width) // 2
        y = mon_y + mon_height - window_height
    elif edge == 'east':
        x = mon_x + mon_width - window_width
        y = mon_y + (mon_height - window_height) // 2
    elif edge == 'west':
        x = mon_x
        y = mon_y + (mon_height - window_height) // 2
    else:
        # Default to north
        x = mon_x + (mon_width - window_width) // 2
        y = mon_y
    
    return (x, y)


def check_edge_trigger(x: int, y: int, edge: str, monitor: Dict[str, int], threshold: int = 5) -> bool:
    """Check if pointer is at the specified edge
    
    Args:
        x: Pointer X coordinate
        y: Pointer Y coordinate
        edge: Edge to check ('north', 'south', 'east', 'west')
        monitor: Monitor geometry dictionary
        threshold: Distance from edge in pixels
        
    Returns:
        True if pointer is at edge
    """
    mon_x = monitor['x']
    mon_y = monitor['y']
    mon_width = monitor['width']
    mon_height = monitor['height']
    
    # Check if pointer is within monitor bounds
    if not (mon_x <= x < mon_x + mon_width and mon_y <= y < mon_y + mon_height):
        return False
    
    if edge == 'north':
        return y <= mon_y + threshold
    elif edge == 'south':
        return y >= mon_y + mon_height - threshold
    elif edge == 'east':
        return x >= mon_x + mon_width - threshold
    elif edge == 'west':
        return x <= mon_x + threshold
    
    return False
