import pytest

from scripts import new_replay_inputs as inputs


def test_patch_window_requires_entire_match_inside_known_period():
    left, right = inputs.PATCH_741F
    assert inputs.patch_window(left + 900, 900) == (left, "7.41f")
    assert inputs.patch_window(right, 900) == (right - 900, None)
    assert inputs.patch_window(left + 899, 900) == (left - 1, None)
    assert inputs.patch_window(None, 900) == (None, None)


def test_active_parser_source_and_file_set(tmp_path):
    package = tmp_path / "gem"
    package.mkdir()
    source = package / "clock.py"
    source.write_text("a")
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    frozen = {
        "compat": {"manifest.json": inputs.digest(manifest), "gem/clock.py": inputs.digest(source)}
    }
    assert inputs.verify_compat(package, frozen) == inputs.digest(manifest)
    source.write_text("b")
    with pytest.raises(ValueError, match="clock.py"):
        inputs.verify_compat(package, frozen)
    (package / "extra.py").write_text("")
    with pytest.raises(ValueError, match="source files"):
        inputs.verify_compat(package, frozen)


def test_existing_output_and_identity_mismatch_preserve_source(tmp_path, monkeypatch):
    demo = tmp_path / "untrusted-name.dem"
    demo.write_bytes(b"example")
    monkeypatch.setattr(inputs, "active_compat", lambda: "sha")
    monkeypatch.setattr(inputs, "replay_header", lambda _: {"match_id": 9})
    with pytest.raises(ValueError, match="fresh output"):
        inputs.prepare(demo, tmp_path)
    with pytest.raises(ValueError, match="Embedded match ID 9"):
        inputs.prepare(demo, tmp_path / "output", expected_id=10)
    assert demo.read_bytes() == b"example" and not (tmp_path / "output").exists()
