#!/usr/bin/env python3
import sys
import subprocess
import os

# Force UTF-8 encoding for standard output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Set terminal color codes
GREEN = "\033[92m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Disable color codes if output is not a terminal
if not sys.stdout.isatty():
    GREEN = RED = BOLD = RESET = ""

def print_section(title: str):
    print(f"\n{BOLD}=== {title} ==={RESET}")

def run_command(args: list[str], cwd: str) -> bool:
    """Runs a command and returns True if successful, False if it failed."""
    print(f"Running: {' '.join(args)}")
    try:
        result = subprocess.run(args, cwd=cwd)
        return result.returncode == 0
    except FileNotFoundError:
        print(f"{RED}Error: Executable not found at {args[0]}. Make sure the virtual environment (.venv) is set up.{RESET}")
        return False

def main():
    # Set current working directory to the backend directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(script_dir)
    os.chdir(backend_dir)

    print(f"{BOLD}Starting Python CI Quality Check...{RESET}")
    print(f"Working Directory: {backend_dir}")

    # Resolve paths to the virtual environment bin/Scripts directory
    is_windows = os.name == "nt"
    venv_dir = os.path.join(backend_dir, ".venv")
    
    if is_windows:
        ruff_bin = os.path.join(venv_dir, "Scripts", "ruff.exe")
        mypy_bin = os.path.join(venv_dir, "Scripts", "mypy.exe")
        python_bin = os.path.join(venv_dir, "Scripts", "python.exe")
    else:
        ruff_bin = os.path.join(venv_dir, "bin", "ruff")
        mypy_bin = os.path.join(venv_dir, "bin", "mypy")
        python_bin = os.path.join(venv_dir, "bin", "python")

    checks = [
        ("Ruff Linter", [ruff_bin, "check", "app"]),
        ("Mypy Static Type Analyzer", [mypy_bin, "app"]),
        ("Pytest Unit Tests", [python_bin, "-m", "pytest"]),
    ]

    failed = False
    for name, args in checks:
        print_section(name)
        success = run_command(args, backend_dir)
        if not success:
            print(f"{RED}✗ {name} failed.{RESET}")
            failed = True
        else:
            print(f"{GREEN}✓ {name} passed.{RESET}")

    print_section("CI Summary")
    if failed:
        print(f"{RED}{BOLD}CI run failed! Please fix the errors listed above before pushing.{RESET}")
        sys.exit(1)
    else:
        print(f"{GREEN}{BOLD}CI run succeeded! The codebase is clean and ready.{RESET}")
        sys.exit(0)

if __name__ == "__main__":
    main()
