"""
Test runner script. Runs all pytest suites safely against isolated test databases.
"""
import sys
import pytest

if __name__ == "__main__":
    print("\nRunning Finance Hub automated test suite with isolated databases...\n")
    exit_code = pytest.main(["-v", "tests"])
    sys.exit(exit_code)
