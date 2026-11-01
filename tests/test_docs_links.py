"""Relative links in maintained Markdown resolve (archive snapshots keep original paths)."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Local evidence and private workspaces are never distributed by Git (docs/README.md).
LOCAL_ONLY = ("data", "reports", "coach-workspace", "memory", "configs")
LINK = re.compile(r"\]\(([^)\s]+)\)")
FENCE = re.compile(r"```.*?```|~~~.*?~~~", re.S)


def maintained_markdown():
    listed = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return [ROOT / name for name in listed if not name.startswith("docs/archive/")]


def broken_links(path, root=ROOT):
    text = FENCE.sub("", path.read_text(encoding="utf-8"))
    for match in LINK.finditer(text):
        target = match.group(1).split("#", 1)[0]
        if not target or re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target):
            continue
        resolved = (path.parent / target).resolve()
        try:
            top = resolved.relative_to(root).parts[0]
        except (ValueError, IndexError):
            yield target
            continue
        if top in LOCAL_ONLY:
            continue
        if not resolved.exists():
            yield target


def test_maintained_markdown_relative_links_resolve():
    files = maintained_markdown()
    assert files, "git ls-files returned no Markdown"
    problems = [
        f"{path.relative_to(ROOT)} -> {target}" for path in files for target in broken_links(path)
    ]
    assert not problems, "\n".join(problems)


def test_link_checker_flags_missing_targets(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "ok.md").write_text("ok", "utf-8")
    page = tmp_path / "docs" / "page.md"
    page.write_text(
        "[ok](ok.md#a) [gone](missing.md) [web](https://example.com) [local](../reports/x.json)"
        " [outside](../../elsewhere.md)\n```\n[fenced](nope.md)\n```\n",
        "utf-8",
    )
    assert list(broken_links(page, tmp_path)) == ["missing.md", "../../elsewhere.md"]


def linked_from(index):
    text = FENCE.sub("", index.read_text(encoding="utf-8"))
    return {
        (index.parent / match.group(1).split("#", 1)[0]).resolve()
        for match in LINK.finditer(text)
        if match.group(1).split("#", 1)[0]
    }


def test_every_maintained_doc_is_indexed():
    docs = ROOT / "docs"
    decisions = docs / "decisions"
    maintained = [path for path in maintained_markdown() if docs in path.parents]
    index = linked_from(docs / "README.md")
    missing = [
        path.relative_to(ROOT).as_posix()
        for path in maintained
        if decisions not in path.parents and path != docs / "README.md" and path not in index
    ]
    assert not missing, "List these in docs/README.md:\n" + "\n".join(missing)
    decision_index = linked_from(decisions / "README.md")
    unlisted = [
        path.name
        for path in maintained
        if path.parent == decisions and path.name != "README.md" and path not in decision_index
    ]
    assert not unlisted, "List these in docs/decisions/README.md:\n" + "\n".join(unlisted)
