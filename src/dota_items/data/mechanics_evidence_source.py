"""Read the registered immutable baseline and reconstruct its engineering proof inputs."""

from pathlib import Path

from dota_items.data.mechanics_engineering_evidence import SOURCE_PATHS
from dota_items.data.mechanics_evidence_projection import BASE_SCHEMAS
from dota_items.data.patch_asset_evidence import EvidencePins

# Registered engineering baseline, not arbitrary user-approved knowledge.
BASE_RECEIPT_SHA256 = "2791d6d17aa47706e464ba4e298fd816d0e12e40d605e800fbdd956c44ada025"


class MechanicsEvidenceSource:
    """Only this registered baseline is supported; unknown migrations fail closed."""

    def __init__(self, baseline_receipt, engineering_ref, *, repository_root):
        if baseline_receipt.get("sha256") != BASE_RECEIPT_SHA256:
            raise ValueError("Unregistered baseline receipt; explicit migration required")
        self.pins = EvidencePins()
        receipt = self.pins.read(baseline_receipt)
        if (
            receipt.get("schema") != "patch-review-assets-receipt/1"
            or receipt.get("exact_patch") != "7.42"
            or receipt.get("training_allowed") is not False
            or receipt.get("action_review_allowed") is not False
        ):
            raise ValueError("Invalid registered candidate receipt")
        for path, digest in receipt["used_files"].items():
            self.pins.add({"path": path, "sha256": digest})
        directory = Path(baseline_receipt["path"]).parent
        self.asset_refs, self.assets = {}, {}
        for name in ("admission", *BASE_SCHEMAS):
            filename = f"mechanics-{name}.json"
            ref = {
                "path": str(directory / filename),
                "sha256": receipt["output_sha256"][filename],
            }
            self.asset_refs[name] = ref
            self.assets[name] = self.pins.read(ref)
        self.baseline = self.assets.pop("admission")
        for ref in self.baseline["source_refs"].values():
            path = Path(ref["path"])
            expected = receipt["used_files"].get(str(path))
            if path.parent == directory:
                expected = receipt["output_sha256"].get(path.name, expected)
            if expected != ref["sha256"]:
                raise ValueError("Baseline source ref is outside its registered receipt")
            self.pins.add(ref)
        self.engineering = self.pins.read(engineering_ref)
        if self.engineering.get("source_refs", {}).get("admission") != self.asset_refs["admission"]:
            raise ValueError("Engineering proof is not bound to this registered admission")
        self.refs = {
            "baseline_admission": self.asset_refs["admission"],
            "engineering_evidence": engineering_ref,
        }
        self.documents = {}
        if set(self.engineering["source_refs"]) != set(SOURCE_PATHS) | {"admission"}:
            raise ValueError("Engineering source inventory differs from registered inputs")
        for key, filename in SOURCE_PATHS.items():
            ref = self.engineering["source_refs"][key]
            if Path(ref["path"]) != Path(repository_root).resolve() / filename:
                raise ValueError("Engineering source path differs from its registered identity")
            self.refs[key] = ref
            self.documents[key] = self.pins.read(ref)
        self.baseline_receipt = dict(baseline_receipt)

    def verify(self):
        self.pins.verify()
