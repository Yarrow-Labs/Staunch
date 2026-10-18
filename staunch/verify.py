"""Compare a rebuilt source with a puzzle from the chain.

The steps, in order:

1. `preflight`: refuse a recipe this machine cannot follow exactly (wrong
   compiler version, wrong commit, uncommitted changes, missing files).
2. `rebuild`: compile the source many times; each distinct program is a
   *variant*. Its *mod hash* is its tree hash, after any `precurry` values.
3. `verify_puzzle`: peel the puzzle's standard layers, then compare every
   layer with every variant, and keep the best answer.
   `verify_hash`: the same, for a bare puzzle hash, which cannot be peeled.

Every comparison is by tree hash, so a value known only by its hash checks
exactly like one given in full.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from enum import IntEnum

from clvm import SExp

from . import build, program
from .layers import Layer, peel
from .recipe import Recipe, RecipeError


class Result(IntEnum):
    """The answer, from worst to best. A higher value is a stronger match."""
    NO_MATCH = 0        # not the recipe's code
    VALUES_DIFFER = 1   # the recipe's code, with different curried values
    CODE_MATCH = 2      # the recipe's code; the recipe pins no values to check
    MATCH = 3           # the recipe's code, with every value the recipe pins

    @property
    def ok(self) -> bool:
        return self >= Result.CODE_MATCH

    @property
    def label(self) -> str:
        return self.name.lower().replace("_", "-")


@dataclass
class Build:
    variants: list[build.Variant]
    mod_hashes: list[bytes]          # one per variant, same order
    warnings: list[str]

    @property
    def compiles(self) -> int:
        return sum(v.count for v in self.variants)


@dataclass
class Report:
    recipe: str
    build: Build
    result: Result = Result.NO_MATCH
    layers: list[Layer] = field(default_factory=list)   # empty when checking a bare hash
    layer: Layer | None = None       # the layer that matched
    variant: int | None = None       # index of the variant that matched
    details: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "recipe": self.recipe,
            "result": self.result.label,
            "layer": self.layer.name if self.layer else None,
            "variant": self.variant,
            "details": self.details,
            "warnings": self.warnings,
            "layers": [{"name": l.name, "hash": l.hash.hex(), **l.facts} for l in self.layers],
            "variants": [{"mod_hash": h.hex(), "compiles": v.count, "of": self.build.compiles}
                         for h, v in zip(self.build.mod_hashes, self.build.variants)],
        }


# --- 1. preflight ----------------------------------------------------------------

def _git(root, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def preflight(recipe: Recipe) -> list[str]:
    """Raise RecipeError if the recipe cannot be followed exactly; return warnings."""
    try:
        package, version = recipe.compiler.split()
    except ValueError:
        raise RecipeError(f"\"compiler\" must read \"{build.COMPILER} <version>\", not {recipe.compiler!r}") from None
    if package != build.COMPILER:
        raise RecipeError(f"Staunch builds with {build.COMPILER} only; the recipe asks for {package}")
    if (have := build.compiler_version()) != version:
        raise RecipeError(f"the recipe needs {package} {version}; this machine has {have}. "
                          f"Install the right one: pip install {package}=={version}")
    files = [recipe.source, *recipe.include]
    for path in files:
        if not path.exists():
            raise RecipeError(f"not found: {path}")

    if not recipe.commit:
        return ["the recipe names no commit, so which version of the source was checked is not pinned"]
    head = _git(recipe.root, "rev-parse", "HEAD")
    if head.returncode != 0:
        return [f"the commit was not checked: {recipe.root} is not a git checkout"]
    if head.stdout.strip() != recipe.commit:
        raise RecipeError(f"the checkout is at {head.stdout.strip()}; the recipe names {recipe.commit}. "
                          f"Run: git -C {recipe.root} checkout {recipe.commit}")
    dirty = _git(recipe.root, "status", "--porcelain", "--", *map(str, files)).stdout.strip()
    if dirty:
        raise RecipeError(f"the recipe's files have uncommitted changes:\n{dirty}")
    return []


# --- 2. rebuild ------------------------------------------------------------------

def rebuild(recipe: Recipe, times: int = 16) -> Build:
    warnings = preflight(recipe)
    variants = build.compile_many(recipe.source, recipe.include, times)
    precurry = [v.hash for v in recipe.precurry]
    mod_hashes = []
    for variant in variants:
        code_hash = program.tree_hash(program.from_bytes(variant.program))
        mod_hashes.append(program.curried_hash(code_hash, precurry) if precurry else code_hash)
    if len(variants) > 1:
        counts = ", ".join(f"{h.hex()[:12]}… ({v.count} of {times})" for h, v in zip(mod_hashes, variants))
        warnings.append(f"this source is unstable: {times} compiles gave {len(variants)} different programs: {counts}")
    return Build(variants, mod_hashes, warnings)


# --- 3. compare ------------------------------------------------------------------

def _describe(value: SExp) -> str:
    if value.listp():
        return f"a program with tree hash {program.tree_hash(value).hex()}"
    return f"atom {value.as_atom().hex() or '(empty)'}"


def _compare_values(recipe: Recipe, values: list[SExp]) -> tuple[Result, list[str]]:
    """The code matched; now the curried values."""
    if recipe.curry is None:
        return Result.CODE_MATCH, [f"curried value {i}: {_describe(v)}" for i, v in enumerate(values)]
    if len(values) != len(recipe.curry):
        return Result.VALUES_DIFFER, [f"the puzzle has {len(values)} curried values; the recipe expects {len(recipe.curry)}"]
    details, differ = [], False
    for i, (want, have) in enumerate(zip(recipe.curry, values)):
        if not want.pinned:
            details.append(f"curried value {i}: {_describe(have)} (left open by the recipe)")
        elif want.hash == program.tree_hash(have):
            details.append(f"curried value {i}: matches ({want.described})")
        else:
            differ = True
            details.append(f"curried value {i}: DIFFERS. The recipe has {want.described}; "
                           f"the puzzle has {_describe(have)}")
    return (Result.VALUES_DIFFER if differ else Result.MATCH), details


def _compare_layer(recipe: Recipe, layer: Layer, mod_hash: bytes) -> tuple[Result, list[str]]:
    if layer.hash == mod_hash:                        # the code, with nothing curried
        if recipe.curry:
            return Result.VALUES_DIFFER, ["the code matches, with nothing curried; the recipe expects values"]
        return (Result.CODE_MATCH if recipe.curry is None else Result.MATCH), ["the code matches, with nothing curried"]
    curried = program.uncurry(layer.puzzle)
    if curried and program.tree_hash(curried[0]) == mod_hash:
        return _compare_values(recipe, curried[1])
    return Result.NO_MATCH, []


def verify_puzzle(recipe: Recipe, puzzle: SExp, times: int = 16) -> Report:
    """Check a revealed puzzle against the recipe, layer by layer."""
    built = rebuild(recipe, times)
    report = Report(recipe.name, built, layers=peel(puzzle), warnings=list(built.warnings))
    for layer in report.layers:                              # outermost first
        for index, mod_hash in enumerate(built.mod_hashes):  # most common first
            result, details = _compare_layer(recipe, layer, mod_hash)
            if result > report.result:
                report.result, report.layer, report.variant, report.details = result, layer, index, details
    if report.result == Result.NO_MATCH:
        report.details.append("no layer of the puzzle is this code")
    elif report.variant:
        report.warnings.append(f"the match is with variant {report.variant + 1}, not the most common build")
    return report


def verify_hash(recipe: Recipe, target: bytes, times: int = 16) -> Report:
    """Check a bare puzzle hash. It cannot be peeled, so it is compared as it is."""
    built = rebuild(recipe, times)
    report = Report(recipe.name, built, warnings=list(built.warnings))
    pinned = recipe.curry is not None and all(v.pinned for v in recipe.curry)
    for index, mod_hash in enumerate(built.mod_hashes):
        if target == mod_hash:
            if recipe.curry:
                report.result = Result.VALUES_DIFFER
                report.details.append("the hash is the code with nothing curried; the recipe expects values")
            else:
                report.result = Result.CODE_MATCH if recipe.curry is None else Result.MATCH
                report.details.append("the hash is the code itself, with nothing curried")
        elif recipe.curry and pinned and target == program.curried_hash(mod_hash, [v.hash for v in recipe.curry]):
            report.result = Result.MATCH
            report.details.append("the hash is the code with the recipe's values curried in")
        else:
            continue
        report.variant = index
        break
    if report.result == Result.NO_MATCH:
        report.details.append("no match. A hash cannot be unwrapped, so if the coin is wrapped (a CAT, a "
                              "singleton) check a revealed puzzle instead, or the inner puzzle's hash")
        if recipe.curry and not pinned:
            report.details.append("the recipe leaves some values open, and a hash can only be checked "
                                  "against a recipe that pins every value")
    return report
