"""Run the repository checks using the checkout's virtual environment when available."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


MODEL_TESTS = {
    "test_model_foundation.py",
    "test_model_foundation_validation.py",
    "test_purchase_baseline.py",
    "test_purchase_diagnostics.py",
    "test_purchase_sensitivity.py",
    "test_modular_maintenance.py",
}


def module_paths(scope):
    """Explicit ownership for existing suites; unknown suites conservatively join data."""
    all_tests = sorted(path.name for path in (ROOT / "tests").glob("test_*.py"))
    recommendation = {name for name in all_tests if name.startswith("test_recommendation_")}
    model_tests = MODEL_TESTS | {name for name in all_tests if name.startswith("test_model_")}
    shared = {"test_architecture.py", "test_check_scopes.py"}
    selected = {
        "modeling": model_tests | shared,
        "recommendation": recommendation | shared,
        "data": (set(all_tests) - model_tests - recommendation) | shared,
    }[scope]
    source = {
        "modeling": ["src/dota_items/modeling", "src/dota_items/contracts"],
        "data": [
            "src/dota_items/data",
            "src/dota_items/sources",
            "src/dota_items/handoff",
            "src/dota_items/contracts",
            "src/dota_items/workflow",
        ],
        "recommendation": ["src/dota_items/recommendation"],
    }[scope]
    tests = ["tests/" + name for name in sorted(selected)]
    return source, tests


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scope",
        choices=("all", "engineering", "learning", "data", "modeling", "recommendation"),
        default="all",
    )
    args = parser.parse_args()
    environment = ROOT / ".venv"
    installed = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    python = str(installed) if installed.is_file() else sys.executable
    commands = []
    if args.scope in ("all", "engineering"):
        commands.extend(
            [
                [python, "-m", "ruff", "check", "--output-format", "full", "."],
                [python, "-m", "ruff", "format", "--check", "--diff", "."],
                [python, "-m", "pytest", "-q"],
            ]
        )
    if args.scope in ("data", "modeling", "recommendation"):
        source, tests = module_paths(args.scope)
        paths = [*source, *tests, "scripts/check.py"]
        commands.extend(
            [
                [python, "-m", "ruff", "check", "--output-format", "full", *paths],
                [python, "-m", "ruff", "format", "--check", "--diff", *paths],
                [python, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests],
            ]
        )
    if args.scope in ("all", "learning"):
        commands.append([python, "-m", "unittest", "discover", "-s", "learning/tests", "-q"])
        commands.append(
            [python, "-m", "unittest", "discover", "-s", "knowledge/hero-capabilities", "-q"]
        )
        node = shutil.which("node")
        if node:
            commands.extend(
                [
                    [node, "--check", "learning/assets/learning.js"],
                    [node, "learning/tests/test_labs.cjs"],
                ]
            )
        else:
            print(
                "Node.js unavailable: JavaScript checks skipped; CI runs them with Node 22.",
                flush=True,
            )
    # A moved checkout may retain an editable install pointing to its old path.
    # Test this checkout, including subprocesses, without reinstalling shared deps.
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "src"), env.get("PYTHONPATH")]))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    exit_code = 0
    for command in commands:
        print("Running: " + " ".join(command), flush=True)
        result = subprocess.run(command, cwd=ROOT, env=env, check=False)
        exit_code = max(exit_code, result.returncode)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
