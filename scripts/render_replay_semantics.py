"""Render preserved audit events as a standalone SVG; no map/teleport claims."""

import argparse
import html
from pathlib import Path

from dota_items.data.source_io import parse_source_json, read_source_bytes


def render(audit):
    duration = audit["duration"]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="570" viewBox="0 0 1200 570">',
        '<rect width="1200" height="570" fill="white"/>',
    ]

    def text(x, y, value, size=15):
        parts.append(
            f'<text x="{x}" y="{y}" font-size="{size}" '
            f'font-family="sans-serif">{html.escape(str(value))}</text>'
        )

    text(20, 30, f"Match {audit['match_id']} — sampled life-state and unclassified jumps", 22)
    text(20, 55, "Green: code 0 | Orange: code 1 | Red: code 2 | Black: jump >=1200 native units")
    text(
        20,
        78,
        "Sampled state only; grey = no transition-derived evidence. Jumps are NOT teleport labels.",
    )
    for index, player in enumerate(audit["players"]):
        slot, y = player["player_slot"], 115 + index * 38
        text(20, y + 10, f"slot {slot} / hero {player['hero_id']}", 13)
        parts.append(f'<rect x="180" y="{y}" width="980" height="18" fill="#ddd"/>')
        transitions = [r for r in audit["life_transitions"] if r["player_slot"] == slot]
        # Draw only intervals bracketed by recorded transition evidence. Do not
        # infer initial/final state outside that evidence or bridge identity changes.
        for left, right in zip(transitions, transitions[1:], strict=False):
            if any(
                left["current"][k] != right["previous"][k]
                for k in ("entity_index", "entity_serial")
            ):
                continue
            a, b = max(0, left["time"]), min(duration, right["time"])
            if b <= a:
                continue
            color = {0: "#3a9d5d", 1: "#e7a629", 2: "#cd5050"}.get(
                left["current"]["life_state"], "#ddd"
            )
            x, width = 180 + a / duration * 980, (b - a) / duration * 980
            title = html.escape(
                f"{a}–{b}s; life_state={left['current']['life_state']}; "
                f"{left['current']['source_ref']}"
            )
            parts.append(
                f'<rect x="{x:.2f}" y="{y}" width="{width:.2f}" height="18" '
                f'fill="{color}"><title>{title}</title></rect>'
            )
        for jump in audit["jumps"]:
            if jump["player_slot"] != slot:
                continue
            x = 180 + jump["current"]["time"] / duration * 980
            title = html.escape(
                f"{jump['current']['time']}s; distance "
                f"{jump['distance_native_units']:.1f}; "
                f"{jump['current']['source_ref']}"
            )
            parts.append(
                f'<path d="M{x:.2f} {y - 3}v24" stroke="#111" stroke-width="1">'
                f"<title>{title}</title></path>"
            )
    for time in range(0, duration + 1, 300):
        text(180 + time / duration * 980, 515, f"{time // 60}m", 12)
    text(
        20,
        550,
        "Offline audit: hover marks for source references. Not independent gameplay verification.",
    )
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit = parse_source_json(read_source_bytes(args.audit))
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(render(audit))


if __name__ == "__main__":
    main()
