# Otter Window Switcher - Unit Tests

Comprehensive unit test suite to ensure code changes maintain functionality.

## Test Coverage

### `test_configuration.py`
Tests for configuration and command-line argument parsing:
- Default configuration values
- Custom layout options (--nrows, --ncols)
- Edge trigger options (--north, --south, --east, --west)
- Mutually exclusive argument groups
- Boolean flags (--notitle, --recent, --main-character)
- Hide delay configuration
- Thumbnail size settings
- Combined option scenarios
- Layout dimension calculations
- MRU (Most Recently Used) ordering algorithm
- Window ID generation and fallback logic
- HIDE_STATE semaphore behavior

### `test_edge_detection.py`
Tests for mouse position and edge detection logic:
- North/South/East/West edge trigger detection
- Trigger threshold (5 pixel boundary)
- Multi-monitor cursor detection
- Monitor boundary handling
- Mouse-in-window detection with buffer zones
- Smart window positioning near cursor
- Edge-aware position adjustments

### `test_wnck_management.py`
Tests for Wnck state management and stability:
- Time-based Wnck recreation (every 120 seconds)
- Count-based recreation (after 10,000 calls)
- Recreation lock mechanism
- Skip force_update after recreation flag
- Wnck corruption detection (WnckClassGroup, hash_table errors)
- Exception handling for Wnck calls (force_update, get_windows, get_application)
- Window activation error handling
- Fullscreen detection logic (--main-character mode)
- System window filtering

## Running Tests

### Run All Tests
```bash
cd tests
./run_tests.py
```

Or:
```bash
python3 -m unittest discover tests
```

### Run Specific Test Module
```bash
./run_tests.py test_configuration
./run_tests.py test_edge_detection
./run_tests.py test_wnck_management
```

### Run Individual Test Class
```bash
python3 -m unittest tests.test_configuration.TestConfigurationParsing
python3 -m unittest tests.test_edge_detection.TestEdgeDetection
python3 -m unittest tests.test_wnck_management.TestWnckRecreation
```

### Run Individual Test Method
```bash
python3 -m unittest tests.test_configuration.TestConfigurationParsing.test_default_configuration
```

## Test Output

Successful run:
```
======================================================================
Otter Window Switcher - Unit Test Suite
======================================================================

Running all unit tests...

test_combined_options (test_configuration.TestConfigurationParsing) ... ok
test_default_configuration (test_configuration.TestConfigurationParsing) ... ok
...
----------------------------------------------------------------------
Ran 45 tests in 0.023s

OK

======================================================================
✓ ALL TESTS PASSED
======================================================================
```

## Adding New Tests

When adding new features to otter.py:

1. **Create test methods** following the naming convention `test_<feature_name>`
2. **Use descriptive docstrings** to explain what each test validates
3. **Test edge cases** including invalid inputs, boundary conditions, and error scenarios
4. **Mock external dependencies** (GTK, Wnck) to keep tests fast and isolated
5. **Run tests** before committing changes

Example test structure:
```python
def test_new_feature(self):
    """Test description of what this validates"""
    # Arrange - set up test data
    expected_value = 42

    # Act - call the function being tested
    result = my_function()

    # Assert - verify the result
    self.assertEqual(result, expected_value)
```

## Continuous Integration

These tests are designed to be run:
- Before committing code changes
- In CI/CD pipelines
- After merging branches
- Before releases

## Test Philosophy

These unit tests:
- **Mock GTK/Wnck dependencies** - Don't require X11 or display server
- **Test logic only** - Focus on algorithms and state management
- **Run quickly** - Complete suite runs in under 1 second
- **Isolate functionality** - Each test is independent
- **Validate correctness** - Ensure changes don't break existing features

## Coverage Goals

Current coverage areas:
- ✓ Configuration parsing
- ✓ Layout calculations
- ✓ Edge detection
- ✓ Multi-monitor support
- ✓ MRU ordering
- ✓ Window positioning
- ✓ Wnck state management
- ✓ Error handling
- ✓ Fullscreen detection
- ✓ System filtering

Future coverage:
- Screenshot caching logic
- Context menu operations
- Workspace switching
- Drag mode functionality
- Thumbnail generation

## Dependencies

Tests use only Python standard library:
- `unittest` - Test framework
- `unittest.mock` - Mocking framework

No GTK or Wnck required for unit tests!

## Troubleshooting

**Import errors:**
```bash
# Make sure you're in the tests directory
cd /home/src/otter/tests
python3 run_tests.py
```

**Module not found:**
```bash
# Run from project root
cd /home/src/otter
python3 -m unittest discover tests
```

**Permission denied:**
```bash
chmod +x tests/run_tests.py
```
