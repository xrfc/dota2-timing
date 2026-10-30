"""Offline header-only mana metadata audit; never corrects a frozen resource value."""

import argparse
import json
import sys
from pathlib import Path

from dota_items.data.source_io import parse_source_json, read_source_bytes
from dota_items.storage import file_hash

ROOT = Path(__file__).resolve().parents[1]


def audit(output):
    if output.exists() or "gem" in sys.modules:
        raise ValueError("Requires new output and fresh parser process")
    plan_path = ROOT / "reports/decision-live-probe-2026-10-27-v2/plan.json"
    plan = parse_source_json(read_source_bytes(plan_path))
    sources = {**plan["sources"], str(plan_path): file_hash(plan_path)}
    sources[str(Path(__file__).resolve())] = file_hash(Path(__file__))
    if any(file_hash(Path(p)) != h for p, h in sources.items()):
        raise ValueError("Frozen source drift")
    output.mkdir(parents=True)

    def write(name, value):
        with (output / name).open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")

    write("plan.json", {"sources": sources, "cases": plan["cases"], "header_only": True})
    sys.path.insert(0, plan["compat"])
    from gem.binary.stream import DemoStream
    from gem.parser import ReplayParser
    from gem.schema.sendtable.parser import _parse_flattened_serializer

    from dota_items.sources.gem_replay import prepared_demo

    results = []
    for case in plan["cases"]:

        class Audit(ReplayParser):
            evidence = None

            def _on_send_tables(self, data):
                msg = _parse_flattened_serializer(data)
                native = []
                for field in msg.fields:
                    name = msg.symbols[field.var_name_sym]
                    if name in {"m_flMana", "m_flMaxMana"}:
                        native.append(
                            {
                                "name": name,
                                **{
                                    k: getattr(field, k) if field.HasField(k) else None
                                    for k in (
                                        "bit_count",
                                        "low_value",
                                        "high_value",
                                        "encode_flags",
                                    )
                                },
                            }
                        )
                build = self.game_build
                super()._on_send_tables(data)
                decoded = self.entity_manager.serializers.get("CDOTA_BaseNPC")
                # Schema evidence only: no entity/resource values or future events.
                self.evidence = {
                    "schema_tick": self.tick,
                    "build_at_schema_decode": build,
                    "build_after_pending_server_info": self.game_build,
                    "native_mana_fields": native,
                    "decoded_mana_fields": [
                        {"name": f.var_name, "high_value": f.high_value, "low_value": f.low_value}
                        for f in decoded.fields
                        if f.var_name in {"m_flMana", "m_flMaxMana"}
                    ]
                    if decoded is not None
                    else [],
                    "legacy_mana_patch_applies": 0 <= build <= 954,
                    "legacy_patch_high_value": 8192.0,
                    "resource_correction_applied": False,
                    "gameplay_units_certified": False,
                }

        with prepared_demo(Path(case["archive"]), output / "scratch") as demo:
            parser = Audit(demo)
            # Stop at schema: do not invoke full replay parse or read case outcomes.
            with DemoStream(demo) as stream:
                for tick, kind, data in stream:
                    parser.tick = tick
                    parser._dispatch_outer(kind, data)
                    if parser.evidence is not None:
                        break
            if parser.evidence is None:
                raise ValueError("No schema found")
            results.append({"match_id": case["match_id"], **parser.evidence})
    if any(file_hash(Path(p)) != h for p, h in sources.items()):
        raise ValueError("Source drift during audit")
    write("audit.json", {"cases": results, "sources_unchanged": True, "training_allowed": False})
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", type=Path, required=True)
    audit(cli.parse_args().output)
