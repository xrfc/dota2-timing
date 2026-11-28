from test_patch_review_producers import local_dependencies

from dota_items.data.patch_evidence_io import producer_files


def test_supplementary_capture_includes_transitive_validation_and_parser_helpers():
    for kind in ("objectives", "vision"):
        pinned = set(producer_files(kind))
        for path in pinned - {
            "scripts/capture_patch_evidence.py",
            "scripts/capture_map_runtime.py",
        }:
            assert set(local_dependencies(path)) <= pinned, (kind, path)


def test_derived_evidence_pins_complete_execution_closure():
    from scripts.build_patch_evidence import PRODUCER_FILES

    pinned = set(PRODUCER_FILES)
    for path in pinned:
        assert set(local_dependencies(path)) <= pinned, path
