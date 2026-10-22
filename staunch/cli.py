"""The `staunch` command.

    staunch build  RECIPE                      rebuild; print the mod hash of each variant
    staunch verify RECIPE --puzzle HEX         check a revealed puzzle
    staunch verify RECIPE --puzzle-file FILE   ... read from a file
    staunch verify RECIPE --coin COIN_ID       check a coin, through a full node
    staunch verify RECIPE --hash PUZZLE_HASH   check a bare puzzle hash

Exit codes: 0 match · 1 no match · 2 refused or error · 3 match, but the
source compiles more than one way (only with --strict).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, build, fetch, program
from .recipe import RecipeError, load
from .verify import Report, Result, rebuild, verify_hash, verify_puzzle

EXIT_MATCH, EXIT_NO_MATCH, EXIT_REFUSED, EXIT_UNSTABLE = 0, 1, 2, 3

HEADLINE = {
    Result.MATCH: ("MATCH", "This is the recipe's code, with every value the recipe pins."),
    Result.CODE_MATCH: ("MATCH (code only)", "This is the recipe's code. The recipe pins no curried values, so none were checked."),
    Result.VALUES_DIFFER: ("NO MATCH", "This is the recipe's code, but with different curried values."),
    Result.NO_MATCH: ("NO MATCH", "The recipe's code is not anywhere in this puzzle."),
}


def print_report(report: Report) -> None:
    title, meaning = HEADLINE[report.result]
    print(f"{title}: {report.recipe}\n  {meaning}")
    if report.location is not None:
        print("  Code found in: " + (" > ".join(report.location) or "the whole puzzle"))
    for line in report.details:
        print(f"  - {line}")
    if report.layers:
        print("\nStandard layers, outermost first:")
        for n, layer in enumerate(report.layers, 1):
            print(f"  {n}. {layer.name}, puzzle hash {layer.hash.hex()}")
            for key, value in layer.facts.items():
                print(f"       {key}: {value}")
    built = report.build
    print(f"\nBuild: {built.compiles} compiles, "
          + ("one program (stable)" if len(built.variants) == 1 else f"{len(built.variants)} different programs"))
    for n, (mod_hash, variant) in enumerate(zip(built.mod_hashes, built.variants), 1):
        print(f"  variant {n}: mod hash {mod_hash.hex()} ({variant.count} of {built.compiles})")
    for warning in report.warnings:
        print(f"\nWarning: {warning}")


def _parse_hash(text: str) -> bytes:
    blob = bytes.fromhex(text.removeprefix("0x"))
    if len(blob) != 32:
        raise ValueError(f"a puzzle hash is 32 bytes (64 hex digits); this is {len(blob)}")
    return blob


def cmd_build(args) -> int:
    built = rebuild(load(args.recipe, args.root), args.n)
    for mod_hash, variant in zip(built.mod_hashes, built.variants):
        print(f"{mod_hash.hex()}  {variant.count} of {args.n} compiles, {len(variant.program)} bytes")
    for warning in built.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    return EXIT_UNSTABLE if args.strict and len(built.variants) > 1 else EXIT_MATCH


def cmd_verify(args) -> int:
    recipe = load(args.recipe, args.root)
    if args.coin:
        puzzle, puzzle_hash = fetch.coin(args.coin, args.chia, args.max_puzzle_bytes)
        if puzzle is None:
            report = verify_hash(recipe, puzzle_hash, args.n)
            report.warnings.append("the coin is unspent, so only its puzzle hash is public")
        else:
            report = verify_puzzle(recipe, puzzle, args.n)
    elif args.hash:
        report = verify_hash(recipe, _parse_hash(args.hash), args.n)
    else:
        text = Path(args.puzzle_file).read_text() if args.puzzle_file else args.puzzle
        report = verify_puzzle(recipe, program.from_hex(text, args.max_puzzle_bytes), args.n)

    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print_report(report)
    if not report.result.ok:
        return EXIT_NO_MATCH
    return EXIT_UNSTABLE if args.strict and len(report.build.variants) > 1 else EXIT_MATCH


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="staunch", description="Check that a Chialisp contract's published source is the code on chain.")
    top.add_argument("--version", action="version", version=f"staunch {__version__}")
    commands = top.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("recipe", help="the recipe file (JSON)")
        p.add_argument("--root", help="the checkout the recipe's paths start from (default: the recipe's folder)")
        p.add_argument("-n", type=int, default=16, metavar="N", help="compiles per check (default 16)")
        p.add_argument("--strict", action="store_true", help="exit 3 if the source compiles more than one way")

    common(commands.add_parser("build", help="rebuild a recipe and print its mod hash"))
    v = commands.add_parser("verify", help="check a recipe against a puzzle, coin or hash")
    common(v)
    target = v.add_mutually_exclusive_group(required=True)
    target.add_argument("--puzzle", metavar="HEX", help="a revealed puzzle, serialized, in hex")
    target.add_argument("--puzzle-file", metavar="FILE", help="a file holding a revealed puzzle in hex")
    target.add_argument("--coin", metavar="COIN_ID", help="a coin id (needs a synced full node and the chia command)")
    target.add_argument("--hash", metavar="PUZZLE_HASH", help="a puzzle hash")
    v.add_argument("--chia", default="chia", metavar="PATH", help="the chia command to use with --coin (default: chia)")
    v.add_argument("--max-puzzle-bytes", type=int, default=program.MAX_PUZZLE_BYTES, metavar="N",
                   help=f"refuse a puzzle longer than N bytes (default {program.MAX_PUZZLE_BYTES:,})")
    v.add_argument("--json", action="store_true", help="print the report as JSON")
    return top


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return cmd_build(args) if args.command == "build" else cmd_verify(args)
    except (RecipeError, build.BuildError, fetch.FetchError, ValueError, OSError) as e:
        print(f"Refused: {e}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
