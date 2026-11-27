"""A changed transitive helper must invalidate the new derived artifact producer."""

import ast
from pathlib import Path

from dota_items.data.patch_asset_evidence import capture_producer_files
from scripts.build_patch_review_assets import PRODUCER_FILES

ROOT = Path(__file__).resolve().parents[1]


def local_dependencies(filename):
    for node in ast.walk(ast.parse((ROOT / filename).read_text())):
        names = []
        if isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module, *(node.module + "." + a.name for a in node.names)]
        elif isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        for name in names:
            if name.startswith("dota_items."):
                path = "src/" + name.replace(".", "/") + ".py"
                if (ROOT / path).is_file():
                    yield path


def test_build_receipt_includes_transitive_mechanics_dependencies():
    pinned = set(PRODUCER_FILES)
    seen, queue = set(), list(pinned)
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        queue.extend(local_dependencies(path))
    assert not seen - pinned, "Every locally executed helper belongs in the producer pins"


def test_capture_receipts_pin_common_validation_and_the_selected_parser():
    runtime = set(capture_producer_files("runtime"))
    visibility = set(capture_producer_files("visibility"))
    assert runtime - visibility == {"src/dota_items/sources/map_runtime_capture.py"}
    assert visibility - runtime == {"src/dota_items/sources/map_visibility_capture.py"}
    for kind in ("runtime", "visibility"):
        pinned = set(capture_producer_files(kind))
        # The CLI selects either source after the common inputs have been checked.
        for path in pinned - {"scripts/capture_map_runtime.py"}:
            assert set(local_dependencies(path)) <= pinned, (kind, path)
