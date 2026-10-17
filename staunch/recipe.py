"""The recipe: how to rebuild a puzzle, published beside its source.

    {
      "staunch": 1,
      "name": "CAT v2",
      "source": "puzzles/cat_puzzles/cat_v2.clsp",
      "include": ["puzzles", "puzzles/cat_puzzles"],
      "compiler": "clvm_tools_rs 0.4.0",
      "repo": "https://github.com/Chia-Network/chia_puzzles",
      "commit": "d122456feeef55708d354a065623037bfa010714",
      "precurry": [],
      "curry": [{"hash": "37bef360..."}, {"bytes": "ae15..."}, {"any": true}]
    }

Paths are relative to the checkout root (by default the recipe's folder).

`precurry` holds values baked into the code before it is published as a
"mod". Some projects publish their mod hash that way, and comparing the bare
code would then always say no match. `curry` holds the values curried on top.
Leave `curry` out to check the code alone.

A value is one of:
  {"int": 5}            an integer, in CLVM's shortest spelling
  {"bytes": "ab01"}     an atom, given exactly
  {"program": "ff01"}   any CLVM value, serialized
  {"hash": "<64 hex>"}  any value, known only by its tree hash
  {"any": true}         a slot the recipe does not pin (for example, the
                        owner of one coin among many); reported, not checked
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from clvm import SExp

from . import program

FORMAT = 1


class RecipeError(Exception):
    pass


@dataclass(frozen=True)
class Value:
    hash: bytes | None          # None for an "any" slot
    sexp: SExp | None = None    # None when known only by hash
    shown: str = ""

    @property
    def pinned(self) -> bool:
        return self.hash is not None


@dataclass
class Recipe:
    path: Path
    root: Path
    name: str
    source: Path
    include: list[Path]
    compiler: str
    repo: str | None = None
    commit: str | None = None
    precurry: list[Value] = field(default_factory=list)
    curry: list[Value] | None = None


def parse_value(raw: dict, where: str) -> Value:
    if not isinstance(raw, dict) or len(raw) != 1:
        raise RecipeError(f"{where}: a value is an object with exactly one key")
    (kind, given), = raw.items()
    try:
        if kind == "int":
            if not isinstance(given, int) or isinstance(given, bool):
                raise RecipeError(f"{where}: int must be a JSON integer")
            sexp = SExp.to(program.int_atom(given))
        elif kind == "bytes":
            sexp = SExp.to(bytes.fromhex(given.removeprefix("0x")))
        elif kind == "program":
            sexp = program.from_hex(given)
        elif kind == "hash":
            blob = bytes.fromhex(given.removeprefix("0x"))
            if len(blob) != 32:
                raise RecipeError(f"{where}: a hash is 32 bytes")
            return Value(blob, None, f"hash {blob.hex()}")
        elif kind == "any":
            if given is not True:
                raise RecipeError(f"{where}: write {{\"any\": true}}")
            return Value(None, None, "any")
        else:
            raise RecipeError(f"{where}: unknown value kind {kind!r}")
    except ValueError as e:
        raise RecipeError(f"{where}: {e}") from None
    return Value(program.tree_hash(sexp), sexp, f"{kind} {given}")


def load(path: Path | str, root: Path | str | None = None) -> Recipe:
    path = Path(path).resolve()
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise RecipeError(f"cannot read recipe {path}: {e}") from None
    if raw.get("staunch") != FORMAT:
        raise RecipeError(f"{path}: \"staunch\" must be {FORMAT}")
    known = {"staunch", "name", "source", "include", "compiler", "repo", "commit", "precurry", "curry"}
    extra = set(raw) - known
    if extra:
        raise RecipeError(f"{path}: unknown fields {sorted(extra)}")
    for key in ("source", "compiler"):
        if not isinstance(raw.get(key), str):
            raise RecipeError(f"{path}: \"{key}\" is required")
    base = Path(root).resolve() if root else path.parent
    curry = raw.get("curry")
    return Recipe(
        path=path,
        root=base,
        name=raw.get("name", raw["source"]),
        source=base / raw["source"],
        include=[base / p for p in raw.get("include", [])],
        compiler=raw["compiler"],
        repo=raw.get("repo"),
        commit=raw.get("commit"),
        precurry=[parse_value(v, f"precurry[{i}]") for i, v in enumerate(raw.get("precurry", []))],
        curry=None if curry is None else [parse_value(v, f"curry[{i}]") for i, v in enumerate(curry)],
    )
