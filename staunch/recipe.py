"""The recipe: how to rebuild a puzzle from its source.

A project publishes a recipe (a small JSON file) beside its source. The full
format, with examples, is in docs/recipes.md. In short:

    {
      "staunch": 1,                          format version, always 1 for now
      "name": "Chia CAT v2",                 shown in reports
      "source": "puzzles/cat_v2.clsp",       the file to compile
      "include": ["puzzles"],                folders the compiler searches
      "compiler": "clvm_tools_rs 0.4.0",     the exact compiler to use
      "repo": "https://github.com/...",      where the source lives (informational)
      "commit": "d122456f...",               the commit the source must be at
      "precurry": [ ...values... ],          values baked into the published mod
      "curry": [ ...values... ]              values curried on top
    }

Paths are relative to the checkout root, and may not point outside it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from clvm import SExp

from . import program

FORMAT = 1
FIELDS = {"staunch", "name", "source", "include", "compiler", "repo", "commit", "precurry", "curry"}


class RecipeError(Exception):
    """The recipe is malformed, or this machine cannot follow it."""


@dataclass(frozen=True)
class Value:
    """One curried value as the recipe states it.

    Every comparison is by tree hash, so `hash` is all that is checked.
    `hash` is None for an {"any": true} slot, which is reported, not checked.
    """
    hash: bytes | None
    described: str

    @property
    def pinned(self) -> bool:
        return self.hash is not None


@dataclass
class Recipe:
    path: Path                  # the recipe file
    root: Path                  # the checkout its paths start from
    name: str
    source: Path
    include: list[Path]
    compiler: str
    repo: str | None = None
    commit: str | None = None
    precurry: list[Value] = field(default_factory=list)
    curry: list[Value] | None = None    # None: check the code only


def _hex(given, where: str) -> bytes:
    if not isinstance(given, str):
        raise RecipeError(f"{where}: expected a hex string")
    try:
        return bytes.fromhex(given.removeprefix("0x"))
    except ValueError:
        raise RecipeError(f"{where}: not valid hex") from None


def parse_value(raw, where: str) -> Value:
    """One value: {"int": n}, {"bytes": hex}, {"program": hex}, {"hash": hex} or {"any": true}."""
    if not isinstance(raw, dict) or len(raw) != 1:
        raise RecipeError(f"{where}: a value is an object with exactly one key")
    (kind, given), = raw.items()
    if kind == "int":
        if not isinstance(given, int) or isinstance(given, bool):
            raise RecipeError(f"{where}: int must be a JSON integer")
        return Value(program.tree_hash(SExp.to(program.int_atom(given))), f"int {given}")
    if kind == "bytes":
        return Value(program.tree_hash(SExp.to(_hex(given, where))), f"bytes {given}")
    if kind == "program":
        try:
            sexp = program.from_bytes(_hex(given, where))
        except ValueError as e:
            raise RecipeError(f"{where}: not a serialized program ({e})") from None
        return Value(program.tree_hash(sexp), f"program with tree hash {program.tree_hash(sexp).hex()}")
    if kind == "hash":
        blob = _hex(given, where)
        if len(blob) != 32:
            raise RecipeError(f"{where}: a hash is 32 bytes")
        return Value(blob, f"hash {blob.hex()}")
    if kind == "any":
        if given is not True:
            raise RecipeError(f"{where}: write {{\"any\": true}}")
        return Value(None, "any")
    raise RecipeError(f"{where}: unknown value kind {kind!r}")


def _inside(root: Path, relative, where: str) -> Path:
    """`root / relative`, refusing anything that resolves outside `root`."""
    if not isinstance(relative, str):
        raise RecipeError(f"{where}: expected a path string")
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise RecipeError(f"{where}: {relative!r} points outside the checkout {root}")
    return path


def _values(raw, where: str) -> list[Value]:
    if not isinstance(raw, list):
        raise RecipeError(f"{where}: expected a list of values")
    return [parse_value(v, f"{where}[{i}]") for i, v in enumerate(raw)]


def load(path: Path | str, root: Path | str | None = None) -> Recipe:
    """Read and check a recipe. `root` defaults to the recipe's own folder."""
    path = Path(path).resolve()
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise RecipeError(f"cannot read recipe {path}: {e}") from None
    if not isinstance(raw, dict):
        raise RecipeError(f"{path}: a recipe is a JSON object")
    if raw.get("staunch") != FORMAT:
        raise RecipeError(f"{path}: \"staunch\" must be {FORMAT}")
    if extra := set(raw) - FIELDS:
        raise RecipeError(f"{path}: unknown fields {sorted(extra)}")
    for key in ("source", "compiler"):
        if not isinstance(raw.get(key), str):
            raise RecipeError(f"{path}: \"{key}\" is required")
    for key in ("name", "repo", "commit"):
        if key in raw and not isinstance(raw[key], str):
            raise RecipeError(f"{path}: \"{key}\" must be a string")
    include = raw.get("include", [])
    if not isinstance(include, list):
        raise RecipeError(f"{path}: \"include\" must be a list of folders")

    base = Path(root).resolve() if root else path.parent
    return Recipe(
        path=path,
        root=base,
        name=raw.get("name", raw["source"]),
        source=_inside(base, raw["source"], "source"),
        include=[_inside(base, p, f"include[{i}]") for i, p in enumerate(include)],
        compiler=raw["compiler"],
        repo=raw.get("repo"),
        commit=raw.get("commit"),
        precurry=_values(raw.get("precurry", []), "precurry"),
        curry=None if raw.get("curry") is None else _values(raw["curry"], "curry"),
    )
