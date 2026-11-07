"""Embed sample.json and mechanism names into page.template.html as page.html."""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]


def main():
    sample = json.loads((OUT / "sample.json").read_text(encoding="utf-8"))
    current = json.loads((ROOT / "knowledge/mechanics/current.json").read_text(encoding="utf-8"))
    vocab_path = ROOT / current["entries"]["vocabulary"]["path"]
    vocab = json.loads(vocab_path.read_text(encoding="utf-8"))
    names = {term["id"]: term["zh"] for term in vocab["mechanisms"]}
    data = {"rows": sample["rows"], "mz": names}
    text = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    template = (OUT / "page.template.html").read_text(encoding="utf-8")
    (OUT / "page.html").write_text(template.replace("__DATA__", text), encoding="utf-8")


if __name__ == "__main__":
    main()
