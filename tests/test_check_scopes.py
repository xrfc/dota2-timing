"""Module checks remain conservative and the full check remains the acceptance gate."""

import importlib.util
from pathlib import Path

from test_architecture import imports

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


def test_direct_model_and_experiment_consumers_are_in_model_scope():
    # Check the actual test imports independently of the manually curated list.
    _, selected = check.module_paths("modeling")
    for path in (ROOT / "tests").glob("test_*.py"):
        names = imports(path.read_text(encoding="utf-8"), "tests")
        if any(
            name == prefix or name.startswith(prefix + ".")
            for name in names
            for prefix in ("dota_items.modeling", "dota_items.experiments")
        ):
            assert path.relative_to(ROOT).as_posix() in selected, path.name


def test_mixed_model_suites_keep_data_coverage():
    for scope in ("modeling", "data"):
        _, selected = check.module_paths(scope)
        assert {"tests/" + name for name in check.DATA_MODEL_TESTS} <= set(selected)


def test_module_checks_include_script_static_analysis():
    for scope in ("data", "modeling", "recommendation"):
        paths = check.module_check_paths(scope)
        sources, tests = check.module_paths(scope)
        assert set(sources + tests) <= set(paths)
        assert "scripts" in paths
        assert all((ROOT / path).exists() for path in paths)
