"""Marks concept notes as human-reviewed (`reviewed: true`) or not.

    cd apps/api && uv run python ../../scripts/mark_reviewed.py sliding-window two-pointers
    cd apps/api && uv run python ../../scripts/mark_reviewed.py --all
    cd apps/api && uv run python ../../scripts/mark_reviewed.py --undo sliding-window
    cd apps/api && uv run python ../../scripts/mark_reviewed.py --list

Only run this after you have read the note and checked its claims yourself.
"""

import argparse
import re
from pathlib import Path

NOTES = Path(__file__).resolve().parent.parent / "knowledge" / "notes"
LINE = re.compile(r"^reviewed:.*$", re.MULTILINE)


def set_flag(path: Path, value: bool) -> bool:
    text = path.read_text(encoding="utf-8")
    new = LINE.sub(f"reviewed: {str(value).lower()}", text, count=1)
    changed = new != text
    if changed:
        path.write_text(new, encoding="utf-8")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("slugs", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--undo", action="store_true", help="set reviewed back to false")
    ap.add_argument("--list", action="store_true", help="show review status and exit")
    args = ap.parse_args()
    if args.list:
        for p in sorted(NOTES.glob("*.md")):
            ok = "reviewed: true" in p.read_text(encoding="utf-8")
            print(f"{'[x]' if ok else '[ ]'} {p.stem}")
        return 0
    paths = sorted(NOTES.glob("*.md")) if args.all else [NOTES / f"{s}.md" for s in args.slugs]
    if not paths:
        ap.error("give slugs, --all or --list")
    missing = [p.stem for p in paths if not p.exists()]
    if missing:
        ap.error(f"no such notes: {', '.join(missing)}")
    for p in paths:
        changed = set_flag(p, not args.undo)
        print(f"{p.stem}: {'updated' if changed else 'unchanged'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
