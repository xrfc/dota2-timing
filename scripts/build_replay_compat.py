"""Build an isolated, fingerprinted Gem 0.10.0 backport; never modify site-packages."""

import argparse
import hashlib
import importlib.metadata
import json
import shutil
from pathlib import Path

UPSTREAM = "https://github.com/whanyu1212/gem-dota/tree/bae361de1d82e7a0a8457c788bf6f9d90e9c4d86"


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Unexpected source shape: {old[:60]}")
    return text.replace(old, new, 1)


def build(output):
    dist = importlib.metadata.distribution("gem-dota")
    if dist.version != "0.10.0":
        raise ValueError("Backport only supports Gem 0.10.0")
    source = Path(dist.locate_file("gem"))
    output.mkdir(parents=True, exist_ok=False)
    target = output / "gem"
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    patches = {
        "schema/field_decoder/scalar_codecs.py": [
            (
                "def component_decoder",
                '''def fixed8_decoder(r: BitReader) -> int:
    """Read the upstream fixed8 encoder, not a varint."""
    return r.read_bits(8)


def fixed8_signed_decoder(r: BitReader) -> int:
    value = r.read_bits(8)
    return value - 256 if value & 128 else value


def component_decoder''',
            )
        ],
        "schema/field_decoder/type_resolver.py": [
            (
                "    fixed64_decoder,",
                "    fixed64_decoder,\n    fixed8_decoder,\n    fixed8_signed_decoder,",
            ),
            (
                "    base_type = field.field_type.base_type",
                """    base_type = field.field_type.base_type
    if field.encoder == "fixed8":
        return fixed8_signed_decoder if base_type == "int8" else fixed8_decoder""",
            ),
            (
                "def find_decoder_by_base_type(base_type: str)",
                'def find_decoder_by_base_type(base_type: str, encoder: str = "")',
            ),
            (
                "    return _FIELD_TYPE_DECODERS.get(base_type, default_decoder)",
                """    if encoder == "fixed8":
        return fixed8_signed_decoder if base_type == "int8" else fixed8_decoder
    return _FIELD_TYPE_DECODERS.get(base_type, default_decoder)""",
            ),
        ],
        "schema/sendtable/models.py": [
            (
                "find_decoder_by_base_type(generic_base)",
                "find_decoder_by_base_type(generic_base, self.encoder)",
            )
        ],
        "parser.py": [
            ("v = grp._get_uint32_resolved(fields[5])", "v = grp._get_uint64_resolved(fields[5])")
        ],
    }
    for name, edits in patches.items():
        path = target / name
        text = path.read_text()
        for old, new in edits:
            text = replace_once(text, old, new)
        path.write_text(text)

    def hashes(folder):
        return {
            str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*.py"))
        }

    manifest = dict(
        schema="gem-isolated-backport/1",
        base_version=dist.version,
        fixed8_upstream=UPSTREAM,
        local_fix="64-bit gamerules match ID getter",
        original=hashes(source),
        patched=hashes(target),
        changed=list(patches),
    )
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args().output)
