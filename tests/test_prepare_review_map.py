import hashlib
import importlib.util
import io
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_map_knowledge.py"
spec = importlib.util.spec_from_file_location("build_map_knowledge", SCRIPT)
maps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maps)


@pytest.fixture
def files(monkeypatch):
    originals = {"coordinates/a.json": b"one", "gem/background.jpg": b"two"}
    monkeypatch.setattr(
        maps,
        "REVIEW_MAP_FILES",
        {
            name: (
                f"https://example.invalid/{name}",
                len(content),
                hashlib.sha256(content).hexdigest(),
            )
            for name, content in originals.items()
        },
    )
    return originals


def test_preflight_is_offline_and_rejects_existing_wrong_files(tmp_path, files, monkeypatch):
    monkeypatch.setattr(maps, "urlopen", lambda *a, **k: pytest.fail("unexpected network request"))
    with pytest.raises(FileNotFoundError, match="coordinates/a.json"):
        maps.prepare_741_map(tmp_path)
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir()
        path.write_bytes(content)
    assert maps.prepare_741_map(tmp_path) == {
        name: hashlib.sha256(content).hexdigest() for name, content in files.items()
    }
    wrong = tmp_path / "coordinates/a.json"
    wrong.write_bytes(b"bad")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        maps.prepare_741_map(tmp_path, fetch=True)
    assert wrong.read_bytes() == b"bad"


def test_retry_fetches_only_missing_and_never_publishes_bad_bytes(tmp_path, files, monkeypatch):
    requested = []
    replies = iter([b"one", b"x", b"two"])

    def open_source(url, *, timeout):
        requested.append(url)
        return io.BytesIO(next(replies))

    monkeypatch.setattr(maps, "urlopen", open_source)
    with pytest.raises(ValueError, match="differs"):
        maps.prepare_741_map(tmp_path, fetch=True)
    assert (tmp_path / "coordinates/a.json").read_bytes() == b"one"
    assert not (tmp_path / "gem/background.jpg").exists()
    maps.prepare_741_map(tmp_path, fetch=True)
    maps.prepare_741_map(tmp_path, fetch=True)
    assert requested == [
        "https://example.invalid/coordinates/a.json",
        "https://example.invalid/gem/background.jpg",
        "https://example.invalid/gem/background.jpg",
    ]


def test_concurrent_existing_file_is_verified_without_overwrite(tmp_path, files, monkeypatch):
    def race(url, *, timeout):
        target = tmp_path / "coordinates/a.json"
        target.parent.mkdir()
        target.write_bytes(b"bad")
        return io.BytesIO(b"one")

    monkeypatch.setattr(maps, "urlopen", race)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        maps.prepare_741_map(tmp_path, fetch=True)
    assert (tmp_path / "coordinates/a.json").read_bytes() == b"bad"
