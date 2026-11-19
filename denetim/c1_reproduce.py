"""C1: run the project's exact regression and backtest commands."""

import subprocess
import sys


def run(*args: str) -> int:
    print("$", sys.executable, *args, flush=True)
    return subprocess.run([sys.executable, *args], check=False).returncode


pytest_rc = run("-m", "pytest", "-q")
backtest_rc = run("-m", "kripto_sinyal", "geritest")
print(f"C1_RETURN_CODES pytest={pytest_rc} geritest={backtest_rc}")
