"""Read frozen candidate evidence for observer-context engineering checks only."""

from pathlib import Path

from dota_items.data.patch_asset_evidence import EvidencePins
from dota_items.data.patch_evidence_io import producer_files, read_evidence_capture

# This is the complete registered patch-evidence-assets/1 producer closure.
# Keep it independent of importing a CLI into data; a regression checks equality.
EVIDENCE_PRODUCERS = tuple(
    sorted(
        set(producer_files("objectives") + producer_files("vision"))
        | {
            "scripts/build_patch_evidence.py",
            "src/dota_items/data/patch_assets.py",
            "src/dota_items/data/map_snapshot.py",
            "src/dota_items/data/mechanics_candidate.py",
            "src/dota_items/data/patch_camp_semantics.py",
            "src/dota_items/data/patch_objective_cycles.py",
            "src/dota_items/data/patch_objectives.py",
            "src/dota_items/data/patch_vision_evidence.py",
        }
    )
)
OUTPUT_SCHEMAS = {
    "camp-observations.json": "patch-camp-assets/1",
    "camp-semantics.json": "patch-camp-semantics/1",
    "objective-cycles.json": "patch-objective-cycle-evidence/1",
    "vision-evidence.json": "patch-vision-evidence-batch/1",
}
EVIDENCE_TEXTS = {
    "official_notes": (
        "knowledge/mechanics/reviews/patch-update-2026-11-19/notes/datafeed-7.42-english.json"
    ),
    "historical_patchnotes": (
        "knowledge/mechanics/reviews/patch-update-2026-11-19/notes/patchnotes_english.txt"
    ),
    "localization": (
        "knowledge/game-files/snapshots/2026-11-19/sources/resource/localization/"
        "abilities_english.txt"
    ),
}


def _merge(target, inventory):
    if not isinstance(inventory, dict):
        raise ValueError("Source inventory must be a mapping")
    for path, digest in inventory.items():
        if path in target and target[path] != digest:
            raise ValueError("Conflicting source inventory digests")
        target[path] = digest


def _closed(doc):
    return all(doc.get(k) is False for k in ("training_allowed", "action_review_allowed"))


def open_decision_evidence(receipt_ref, *, repository_root, match_allowed):
    """Exclude matches before reading capture bodies or their underlying replay files."""
    return DecisionEvidenceSource(receipt_ref, repository_root, match_allowed)


class DecisionEvidenceSource:
    def __init__(self, receipt_ref, repository_root, match_allowed):
        self.pins, self.repository_root = EvidencePins(), Path(repository_root)
        self.match_allowed, self.receipt_ref = match_allowed, dict(receipt_ref)
        receipt = self.pins.read(receipt_ref)
        if (
            receipt.get("schema") != "patch-evidence-assets-receipt/1"
            or receipt.get("patch") != "7.42"
            or not _closed(receipt)
            or not isinstance(receipt.get("used_files"), dict)
            or not isinstance(receipt.get("output_sha256"), dict)
            or set(receipt["output_sha256"]) != set(OUTPUT_SCHEMAS)
        ):
            raise ValueError("Invalid closed candidate evidence receipt")
        spec = self.pins.read(receipt["spec"])
        if (
            set(spec) != {"schema", "exact_patch", "base_receipt", "captures"}
            or spec["schema"] != "patch-evidence-assets-spec/1"
            or spec["exact_patch"] != "7.42"
            or not isinstance(spec["captures"], list)
            or not spec["captures"]
        ):
            raise ValueError("Invalid candidate evidence specification")
        self.capture_refs, self.capture_receipts = {}, {}
        required = {receipt["spec"]["path"]: receipt["spec"]["sha256"]}
        for refs in spec["captures"]:
            if not isinstance(refs, dict) or set(refs) != {"capture", "receipt"}:
                raise ValueError("Capture and receipt references required")
            rec = self.pins.read(refs["receipt"])
            mid, kind = rec.get("match_id"), rec.get("kind")
            if type(mid) is not int or mid <= 0 or kind not in {"objectives", "vision"}:
                raise ValueError("Invalid capture identity")
            if not match_allowed(mid):
                raise ValueError("Match excluded before replay evidence reads")
            manifest = self.pins.read(rec["manifest"])
            actual_mid = manifest.get("identity", {}).get("match_id")
            if type(actual_mid) is not int or not match_allowed(actual_mid):
                raise ValueError("Manifest match excluded before replay evidence reads")
            if actual_mid != mid:
                raise ValueError("Manifest and capture receipt match identity mismatch")
            if (
                rec.get("schema") != "patch-evidence-capture-receipt/1"
                or rec.get("patch") != "7.42"
                or not _closed(rec)
                or rec.get("output_sha256") != {"capture.json": refs["capture"]["sha256"]}
                or (mid, kind) in self.capture_refs
            ):
                raise ValueError("Duplicate or incompatible capture receipt")
            self.capture_refs[mid, kind], self.capture_receipts[mid, kind] = refs, rec
            _merge(required, rec.get("used_files"))
            for ref in refs.values():
                required[ref["path"]] = ref["sha256"]
        self.match_ids = sorted({mid for mid, _ in self.capture_refs})
        if any(
            (mid, kind) not in self.capture_refs
            for mid in self.match_ids
            for kind in ("objectives", "vision")
        ):
            raise ValueError("Both evidence channels required for every match")
        for mid in self.match_ids:
            a, b = (self.capture_receipts[mid, kind] for kind in ("objectives", "vision"))
            if any(
                a.get(k) != b.get(k) for k in ("manifest", "demo_sha256", "patch", "game_build")
            ):
                raise ValueError("Conflicting cross-channel replay identity")
        base = spec["base_receipt"]
        required[base["path"]] = base["sha256"]
        baseline = self.pins.read(base)
        if (
            baseline.get("schema") != "patch-review-assets-receipt/1"
            or baseline.get("exact_patch") != "7.42"
            or not _closed(baseline)
            or not baseline.get("used_files")
            or not baseline.get("output_sha256")
        ):
            raise ValueError("Invalid closed baseline receipt")
        _merge(required, baseline["used_files"])
        for name, digest in baseline["output_sha256"].items():
            if not isinstance(name, str) or Path(name).name != name or name in {".", ".."}:
                raise ValueError("Invalid baseline output path")
            _merge(required, {str(Path(base["path"]).parent / name): digest})
        for name in EVIDENCE_PRODUCERS:
            ref = self.pins.track(self.repository_root / name)
            required[ref["path"]] = ref["sha256"]
        text_refs = {
            key: self.pins.track(self.repository_root / name)
            for key, name in EVIDENCE_TEXTS.items()
        }
        _merge(required, {ref["path"]: ref["sha256"] for ref in text_refs.values()})
        if receipt["used_files"] != required:
            raise ValueError("Unexpected or incomplete candidate source inventory")
        self.assets, self.asset_refs = {}, {}
        for name, schema in OUTPUT_SCHEMAS.items():
            ref = {
                "path": str(Path(receipt_ref["path"]).parent / name),
                "sha256": receipt["output_sha256"][name],
            }
            doc = self.pins.read(ref)
            mids = doc.get("match_ids")
            if mids is None:
                mids = [m.get("match_id") for m in doc.get("matches", [])]
            if (
                doc.get("schema") != schema
                or doc.get("exact_patch", doc.get("patch")) != "7.42"
                or not _closed(doc)
                or not isinstance(mids, list)
                or any(type(mid) is not int for mid in mids)
                or sorted(mids) != self.match_ids
                or doc.get("source_refs", {}).get("base") != base
                or doc.get("source_refs", {}).get("captures") != spec["captures"]
                or any(doc.get("source_refs", {}).get(key) != ref for key, ref in text_refs.items())
            ):
                raise ValueError("Published evidence identity, coverage or purpose mismatch")
            self.assets[name], self.asset_refs[name] = doc, ref
        if (
            self.assets["camp-semantics.json"]["source_refs"].get("camp_assets")
            != self.asset_refs["camp-observations.json"]
        ):
            raise ValueError("Camp semantic references must bind the published observations")
        for path, digest in required.items():
            self.pins.add({"path": path, "sha256": digest})
        self._consumed = set()

    def read_match(self, match_id):
        if type(match_id) is not int or match_id not in self.match_ids:
            raise ValueError("Match outside verified evidence set")
        docs = {}
        for kind in ("objectives", "vision"):
            refs = self.capture_refs[match_id, kind]
            docs[kind] = read_evidence_capture(
                refs["capture"],
                refs["receipt"],
                pins=self.pins,
                repository_root=self.repository_root,
                match_allowed=self.match_allowed,
            )
        if any(
            docs["objectives"].get(k) != docs["vision"].get(k)
            for k in ("match_id", "patch", "game_build", "post_game_tick")
        ):
            raise ValueError("Cross-channel completion mismatch")
        manifest = self.pins.read(self.capture_receipts[match_id, "vision"]["manifest"])
        docs["metadata_duration"] = manifest["quality"]["base"]["metadata_duration"]
        self._consumed.add(match_id)
        return docs

    def verify(self):
        if self._consumed != set(self.match_ids):
            raise ValueError("Every selected capture must be verified before publication")
        self.pins.verify()
