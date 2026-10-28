"""Module checks remain conservative and the full check remains the acceptance gate."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("repository_check", ROOT / "scripts/check.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def test_module_scopes_cover_all_test_files():
    paths = set()
    for scope in ("data", "modeling", "recommendation"):
        sources, tests = check.module_paths(scope)
        assert "tests/test_architecture.py" in tests
        assert all((ROOT / path).exists() for path in sources + tests)
        paths.update(tests)
    assert paths == {p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").glob("test_*.py")}


def test_model_scope_contains_all_model_suites():
    _, tests = check.module_paths("modeling")
    assert set("tests/" + name for name in check.MODEL_TESTS) <= set(tests)
    assert "tests/test_purchase_collection.py" not in tests
