"""CLI for explicit JOLIKA asset-resolution review workflows."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from backend.asset_resolution import load_jolika_asset_resolution_registry
from backend.asset_resolution_workflow import (
    build_updated_jolika_asset_resolution_registry,
    load_jolika_asset_resolution_decisions,
    load_unresolved_jolika_assets,
    validate_jolika_resolution_decisions,
    write_jolika_asset_resolution_registry,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m backend.asset_resolution_cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--unresolved", required=True)
    validate.add_argument("--decisions", required=True)
    validate.add_argument("--registry", required=True)

    build = subparsers.add_parser("build")
    build.add_argument("--unresolved", required=True)
    build.add_argument("--decisions", required=True)
    build.add_argument("--registry", required=True)
    build.add_argument("--output", required=True)
    build.add_argument("--overwrite", action="store_true")
    return parser


def _inputs(args):
    unresolved = load_unresolved_jolika_assets(args.unresolved)
    decisions = load_jolika_asset_resolution_decisions(args.decisions)
    registry = load_jolika_asset_resolution_registry(args.registry)
    return unresolved, decisions, registry


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        unresolved, decisions, registry = _inputs(args)
        if args.command == "validate":
            validate_jolika_resolution_decisions(unresolved, decisions, registry)
            print("JOLIKA asset resolution review is valid")
            return 0

        proposed = build_updated_jolika_asset_resolution_registry(
            unresolved,
            decisions,
            registry,
        )
        write_jolika_asset_resolution_registry(
            proposed,
            output_path=Path(args.output),
            overwrite=args.overwrite,
        )
        print(f"Proposed JOLIKA registry written to {args.output}")
        return 0
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
