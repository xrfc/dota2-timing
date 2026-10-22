"""Summarize hash-verified identity audits and draw native landmarks (not a game map)."""

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash

STATIC_CLASSES = {
    "CDOTA_BaseNPC_Tower": "Tower",
    "CDOTA_BaseNPC_Barracks": "Barracks",
    "CDOTA_BaseNPC_Fort": "Ancient",
    "CDOTA_Unit_Fountain": "Fountain",
}


def read(path):
    return parse_source_json(read_source_bytes(path, max_bytes=512 * 1024**2))


def signatures(audit):
    return sorted(
        {
            (r["class_name"], r["team"], *r["native_xy"])
            for r in audit["landmarks"]
            if r["class_name"] in STATIC_CLASSES and r["native_xy"] is not None
        }
    )


def draw(audit, output):
    root = ET.Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        width="880",
        height="900",
        viewBox="0 0 880 900",
        role="img",
    )
    ET.SubElement(root, "title").text = "Replay-native landmark coordinates; no basemap transform"
    ET.SubElement(root, "rect", width="880", height="900", fill="#101827")

    def label(x, y, text, size=14):
        ET.SubElement(
            root,
            "text",
            x=str(x),
            y=str(y),
            fill="#e5e7eb",
            **{"font-family": "sans-serif", "font-size": str(size)},
        ).text = text

    label(55, 35, f"Replay {audit['match_id']} | build {audit['game_build']}", 22)
    label(55, 60, "Native cell*128+vec | green: Radiant, red: Dire | no map alignment claimed")
    for value in range(8000, 24001, 2000):
        px = 80 + (value - 8000) / 16000 * 720
        py = 800 - (value - 8000) / 16000 * 720
        ET.SubElement(
            root, "path", d=f"M {px} 80 V 800 M 80 {py} H 800", stroke="#334155", fill="none"
        )
        label(px - 15, 825, str(value), 11)
        label(20, py + 4, str(value), 11)
    seen = set()
    for row in audit["landmarks"]:
        if row["class_name"] not in STATIC_CLASSES or row["native_xy"] is None:
            continue
        key = (row["entity_index"], row["entity_serial"], *row["native_xy"])
        if key in seen:
            continue
        seen.add(key)
        x, y = row["native_xy"]
        px, py = 80 + (x - 8000) / 16000 * 720, 800 - (y - 8000) / 16000 * 720
        kind = STATIC_CLASSES[row["class_name"]]
        circle = ET.SubElement(
            root,
            "circle",
            cx=str(px),
            cy=str(py),
            r="7" if kind in ("Ancient", "Fountain") else "4",
            fill="#4ade80" if row["team"] == 2 else "#fb7185",
        )
        ET.SubElement(circle, "title").text = (
            f"{kind}; entity {row['entity_index']}:{row['entity_serial']}; "
            f"native ({x}, {y}); {row['capture_ref']}"
        )
        if kind in ("Ancient", "Fountain"):
            label(px + 10, py - 6, kind, 12)
    label(
        55,
        865,
        "Tower/Barracks: small dots; Ancient/Fountain: large dots. Hover for source reference.",
    )
    label(
        55,
        886,
        "Display y increases upward; this convention is not an independent orientation check.",
        12,
    )
    with output.open("xb") as stream:
        ET.ElementTree(root).write(stream, encoding="utf-8", xml_declaration=True)
    ET.parse(output)


def main(audits, output):
    if output.exists():
        raise ValueError("Output already exists")
    hashes = {str(p): file_hash(p) for p in audits}
    values = []
    for path in audits:
        receipt = read(path.with_name("receipt.json"))
        if hashes[str(path)] != receipt["audit_sha256"]:
            raise ValueError("Audit hash mismatch")
        audit = read(path)
        if file_hash(path.with_name("capture.json")) != audit["provenance"]["capture_sha256"]:
            raise ValueError("Capture hash mismatch")
        values.append(audit)
    if not values or len({a["match_id"] for a in values}) != len(values):
        raise ValueError("Expected nonempty unique matches")
    output.mkdir(parents=True, exist_ok=False)
    summary = {
        "audits": hashes,
        "script_sha256": file_hash(Path(__file__)),
        "matches": [
            {
                "match_id": a["match_id"],
                "game_build": a["game_build"],
                "positions": a["positions_compared"],
                "noncanonical": sum(p["noncanonical_samples"] for p in a["players"]),
                "static_landmark_signatures": signatures(a),
            }
            for a in values
        ],
        "same_build": len({a["game_build"] for a in values}) == 1,
        "identical_static_landmarks": all(
            signatures(a) == signatures(values[0]) for a in values[1:]
        ),
        "map_transform_verified": False,
        "training_admission": False,
    }
    for audit in values:
        draw(audit, output / f"{audit['match_id']}.svg")
    if hashes != {str(p): file_hash(p) for p in audits}:
        raise ValueError("Audit drift")
    with (output / "summary.json").open("x") as stream:
        json.dump(summary, stream, indent=2)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audits", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    main(**vars(parser.parse_args()))
