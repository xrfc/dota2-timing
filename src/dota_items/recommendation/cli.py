"""Offline CLI: input -> checked bundle -> pure rules -> JSON/text/HTML."""

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from dota_items.recommendation.contracts import UnknownHeroError, validate_lineup
from dota_items.recommendation.engine import recommend
from dota_items.recommendation.files import load_bundle
from dota_items.recommendation.report import render_html, render_text


def main(argv: list[str] | None = None, *, default_knowledge: Path | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="LineupRequest JSON; not a replay")
    parser.add_argument(
        "--knowledge",
        type=Path,
        default=default_knowledge,
        required=default_knowledge is None,
        help="versioned knowledge directory",
    )
    parser.add_argument("--format", choices=("json", "text", "html"), default="json")
    parser.add_argument("--output", type=Path, help="new file only; omitted means stdout")
    args = parser.parse_args(argv)
    phase = "knowledge"
    try:
        bundle = load_bundle(args.knowledge)
        phase = "input"
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        request = validate_lineup(
            payload, known_hero_ids=[h.hero_id for h in bundle.knowledge.heroes]
        )
        phase = "engine"
        result = recommend(request, bundle)
        if args.format == "json":
            output = result.model_dump_json(indent=2) + "\n"
        else:
            output = (render_html if args.format == "html" else render_text)(result, bundle)
        phase = "output"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(output)
        else:
            print(output, end="")
        return 3 if result.recommendation.status == "unsupported" else 0
    except (ValueError, OSError) as error:
        code = "invalid_knowledge" if phase == "knowledge" else "execution_error"
        if phase == "input":
            code = "unknown_hero" if isinstance(error, UnknownHeroError) else "invalid_input"
        elif phase == "output":
            code = "output_error"
        detail = str(error)
        if isinstance(error, ValidationError):
            # Do not echo the full user input as part of every validation message.
            detail = json.dumps(
                error.errors(include_input=False, include_context=False), ensure_ascii=False
            )
        print(json.dumps({"error": code, "detail": detail}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
