import json
import sys
from pathlib import Path

from app.main import app


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m app.export_openapi <output-path>")
    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
