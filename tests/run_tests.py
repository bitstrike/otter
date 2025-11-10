#!/usr/bin/env python3
"""
Test runner for Otter Window Switcher unit tests
Run all tests or specific test suites
"""

import sys
import unittest
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_all_tests():
    """Discover and run all tests"""
    loader = unittest.TestLoader()
    start_dir = os.path.dirname(os.path.abspath(__file__))
    suite = loader.discover(start_dir, pattern='test_*.py')

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


def run_specific_test(test_module):
    """Run a specific test module"""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName(test_module)

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


def main():
    """Main test runner"""
    print("=" * 70)
    print("Otter Window Switcher - Unit Test Suite")
    print("=" * 70)
    print()

    if len(sys.argv) > 1:
        # Run specific test
        test_module = sys.argv[1]
        print(f"Running test module: {test_module}")
        print()
        success = run_specific_test(test_module)
    else:
        # Run all tests
        print("Running all unit tests...")
        print()
        success = run_all_tests()

    print()
    print("=" * 70)
    if success:
        print("✓ ALL TESTS PASSED")
    else:
        print("✗ SOME TESTS FAILED")
    print("=" * 70)

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
