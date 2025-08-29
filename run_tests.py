#!/usr/bin/env python3
"""
Test runner script for promabbix project.
"""

import sys
import subprocess
import os
from pathlib import Path

def main():
    """Run tests with pytest."""
    project_root = Path(__file__).parent
    
    # Set PYTHONPATH to include src directory
    env = os.environ.copy()
    src_path = str(project_root / "src")
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{src_path}:{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = src_path
    
    # Install test dependencies if needed
    try:
        import pytest
    except ImportError:
        print("Installing test dependencies...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", 
            str(project_root / "requirements-dev.txt")
        ])
    
    # Run tests
    test_args = [
        "-m", "pytest",
        str(project_root / "tests"),
        "-v",
        "--tb=short"
    ]
    
    # Add coverage if available
    try:
        import pytest_cov
        test_args.extend(["--cov=src/promabbix", "--cov-report=term-missing"])
    except ImportError:
        pass
    
    # Add any command line arguments
    if len(sys.argv) > 1:
        test_args.extend(sys.argv[1:])
    
    return subprocess.call([sys.executable] + test_args, env=env)

if __name__ == "__main__":
    sys.exit(main())