from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.placement_model import train_placement_model


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check whether a workbook contains valid future placement-readiness training data."
    )
    parser.add_argument("workbook", type=Path, help="Workbook containing dated features and future outcomes")
    parser.add_argument("--sheet", default=0, help="Worksheet name or index (default: first worksheet)")
    args = parser.parse_args()

    if not args.workbook.is_file():
        parser.error(f"Workbook not found: {args.workbook}")

    frame = pd.read_excel(args.workbook, sheet_name=args.sheet)
    try:
        train_placement_model(frame)
    except ValueError as exc:
        parser.error(str(exc))
    parser.error("No future placement model was created.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
