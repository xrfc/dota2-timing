"""Audit existing replay semantics without parsing, downloading or training."""

import argparse
import json
from pathlib import Path

from dota_items.data.replay_semantics import run_audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preparation", type=Path, required=True)
    parser.add_argument("--compat", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_audit(args.preparation, args.compat, args.output)
    print(
        json.dumps(
            dict(
                match_id=result["match_id"],
                players=len(result["players"]),
                life_transitions=len(result["life_transitions"]),
                jumps=len(result["jumps"]),
                warnings=result["adapter_warnings"]["counts"],
                visibility=result["hero_entity_visibility"],
                leakage_comparisons=result["observer_leakage"]["comparisons"],
                leakage_passed=result["observer_leakage"]["passed"],
            )
        )
    )
    return 0 if result["observer_leakage"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
