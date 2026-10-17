"""staunch: check that a Chialisp source is the puzzle on chain.

    staunch build  RECIPE [-n 16]
    staunch verify RECIPE (--puzzle HEX | --puzzle-file FILE | --coin ID | --hash HASH)

Exit codes: 0 match, 1 no match or values differ, 2 refused or error,
3 match but the source compiles to more than one program (with --strict).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, build, fetch, program
from .recipe import RecipeError, load
from .verify import Result, rebuild, verify_hash, verify_puzzle

VERDICT = {
    Result.MATCH: "MATCH: this is the recipe's code, with the recipe's values",
    Result.CODE_MATCH: "MATCH (code only): this is the recipe's code; no curried values were pinned",
    Result.VALUES_DIFFER: "NO MATCH: same code, different curried values",
    Result.NO_MATCH: "NO MATCH: this is not the recipe's code",
}


def _print_report(report, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report.as_dict(), indent=2))
        return
    d = report.as_dict()
    print(f"{VERDICT[report.result]}\n  recipe: {d['recipe']}")
    if d["layer"]:
        print(f"  found at layer: {d['layer']}")
    for line in d["details"]:
        print(f"  {line}")
    if d["layers"]:
        print("  layers, outermost first:")
        for l in d["layers"]:
            extra = "".join(f"; {k} {v}" for k, v in l.items() if k not in ("name", "hash"))
            print(f"    {l['name']}: {l['hash']}{extra}")
    for w in d["warnings"]:
        print(f"  warning: {w}")


def _cmd_build(args) -> int:
    recipe = load(args.recipe, args.root)
    variants, mods, warnings = rebuild(recipe, args.n)
    for h, v in zip(mods, variants):
        print(f"{h.hex()}  {v.count}/{args.n} compiles, {len(v.program)} bytes")
    for w in warnings:
        print(f"warning: {w}")
    return 3 if args.strict and len(variants) > 1 else 0


def _cmd_verify(args) -> int:
    recipe = load(args.recipe, args.root)
    if args.coin:
        puzzle, puzzle_hash = fetch.coin(args.coin, args.chia)
        report = verify_puzzle(recipe, puzzle, args.n) if puzzle is not None else verify_hash(recipe, puzzle_hash, args.n)
        if puzzle is None:
            report.warnings.append("the coin is unspent, so only its puzzle hash is public")
    elif args.hash:
        report = verify_hash(recipe, bytes.fromhex(args.hash.removeprefix("0x")), args.n)
    else:
        text = Path(args.puzzle_file).read_text() if args.puzzle_file else args.puzzle
        report = verify_puzzle(recipe, program.from_hex(text), args.n)
    _print_report(report, args.json)
    if not report.result.ok:
        return 1
    return 3 if args.strict and len(report.variants) > 1 else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="staunch", description=__doc__.split("\n")[0])
    parser.add_argument("--version", action="version", version=f"staunch {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "verify"):
        p = sub.add_parser(name)
        p.add_argument("recipe")
        p.add_argument("--root", help="checkout root the recipe's paths start from (default: the recipe's folder)")
        p.add_argument("-n", type=int, default=16, help="compiles per check (default 16)")
        p.add_argument("--strict", action="store_true", help="exit 3 if the source compiles more than one way")
        if name == "verify":
            target = p.add_mutually_exclusive_group(required=True)
            target.add_argument("--puzzle", help="a revealed puzzle, serialized, in hex")
            target.add_argument("--puzzle-file", help="a file holding a revealed puzzle in hex")
            target.add_argument("--coin", help="a coin id; needs a synced full node and the chia command")
            target.add_argument("--hash", help="a puzzle hash")
            p.add_argument("--chia", default="chia", help="path to the chia command (for --coin)")
            p.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        return _cmd_build(args) if args.command == "build" else _cmd_verify(args)
    except (RecipeError, build.BuildError, fetch.FetchError, ValueError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
