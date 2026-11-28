from pathlib import Path

import pytest

from dota_items.data.atomic_directory import publish_directory


def test_complete_directory_published(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "receipt.json").write_text("complete")
    publish_directory(staging, tmp_path / "published")
    assert not staging.exists()
    assert (tmp_path / "published/receipt.json").read_text() == "complete"


@pytest.mark.parametrize("existing", ["empty", "populated", "symlink"])
def test_racing_destination_is_never_replaced(tmp_path, existing):
    staging = tmp_path / "staging"
    staging.mkdir()
    target = tmp_path / "destination"
    if existing == "symlink":
        target.symlink_to(tmp_path / "missing", target_is_directory=True)
    else:
        target.mkdir()
        if existing == "populated":
            (target / "user.txt").write_text("keep")
    with pytest.raises(FileExistsError):
        publish_directory(staging, target)
    assert staging.exists()
    if existing == "symlink":
        assert target.is_symlink()
    elif existing == "populated":
        assert Path(target / "user.txt").read_text() == "keep"
