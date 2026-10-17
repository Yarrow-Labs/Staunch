"""Compare a rebuilt source with a puzzle from the chain.

Every comparison is by tree hash, so a curried value known only by its hash
checks exactly like one given in full.
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
    NO_MATCH = 0
    VALUES_DIFFER = 1   # same code, different curried values
    CODE_MATCH = 2      # same code; the recipe pins no values to check
    MATCH = 3           # same code and every pinned value

    @property
    def ok(self) -> bool:
        return self >= Result.CODE_MATCH


@dataclass
class Report:
    recipe: str
    result: Result = Result.NO_MATCH
    layer: int | None = None              # index into `layers`
    variant: int | None = None            # index into `variants`
    details: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    layers: list[Layer] = field(default_factory=list)
    variants: list[build.Variant] = field(default_factory=list)
    mod_hashes: list[bytes] = field(default_factory=list)

    def as_dict(self) -> dict:
        total = sum(v.count for v in self.variants)
        return {
            "recipe": self.recipe,
            "result": self.result.name.lower().replace("_", "-"),
            "layer": None if self.layer is None else self.layers[self.layer].name,
            "variant": self.variant,
            "details": self.details,
            "warnings": self.warnings,
            "layers": [{"name": l.name, "hash": l.hash.hex(), **l.facts} for l in self.layers],
            "variants": [{"mod_hash": h.hex(), "compiles": v.count, "of": total}
                         for h, v in zip(self.mod_hashes, self.variants)],
        }


def preflight(recipe: Recipe) -> list[str]:
    """Refuse a recipe this machine cannot honour; return warnings."""
    warnings = []
    try:
        package, version = recipe.compiler.split()
    except ValueError:
        raise RecipeError(f"compiler must read \"{build.COMPILER} <version>\", not {recipe.compiler!r}") from None
    if package != build.COMPILER:
        raise RecipeError(f"v0.1 builds with {build.COMPILER} only; the recipe asks for {package}")
    have = build.compiler_version()
    if have != version:
        raise RecipeError(f"the recipe needs {package} {version}; this machine has {have}. "
                          f"Install it: pip install {package}=={version}")
    for path in [recipe.source, *recipe.include]:
        if not path.exists():
            raise RecipeError(f"not found: {path}")
    if recipe.commit:
        git = lambda *a: subprocess.run(["git", "-C", str(recipe.root), *a], capture_output=True, text=True)
        head = git("rev-parse", "HEAD")
        if head.returncode != 0:
            warnings.append(f"commit not checked: {recipe.root} is not a git checkout")
        elif head.stdout.strip() != recipe.commit:
            raise RecipeError(f"the checkout is at {head.stdout.strip()}, the recipe names {recipe.commit}")
        else:
            dirty = git("status", "--porcelain", "--", *[str(p) for p in [recipe.source, *recipe.include]])
            if dirty.stdout.strip():
                raise RecipeError(f"uncommitted changes in the recipe's files:\n{dirty.stdout.rstrip()}")
    else:
        warnings.append("the recipe names no commit, so the source cannot be pinned")
    return warnings


def rebuild(recipe: Recipe, times: int = 16) -> tuple[list[build.Variant], list[bytes], list[str]]:
    """Variants, their mod hashes (precurry applied), and warnings."""
    warnings = preflight(recipe)
    variants = build.compile_many(recipe.source, recipe.include, times)
    pre = [v.hash for v in recipe.precurry]
    mods = []
    for v in variants:
        code = program.tree_hash(program.from_bytes(v.program))
        mods.append(program.curried_hash(code, pre) if pre else code)
    if len(variants) > 1:
        shown = ", ".join(f"{h.hex()[:12]}… ({v.count}/{times})" for h, v in zip(mods, variants))
        warnings.append(f"this source is unstable: {times} compiles gave {len(variants)} different programs: {shown}")
    return variants, mods, warnings


def _show(value: SExp) -> str:
    if value.listp():
        return f"a program with tree hash {program.tree_hash(value).hex()}"
    return f"atom {value.as_atom().hex() or '(empty)'}"


def _compare_values(recipe: Recipe, args: list[SExp]) -> tuple[Result, list[str]]:
    got = [program.tree_hash(a) for a in args]
    if recipe.curry is None:
        return Result.CODE_MATCH, [f"curried value {i}: {_show(a)}" for i, a in enumerate(args)]
    if len(got) != len(recipe.curry):
        return Result.VALUES_DIFFER, [f"the puzzle carries {len(got)} curried values; the recipe expects {len(recipe.curry)}"]
    notes, differ = [], False
    for i, (want, have) in enumerate(zip(recipe.curry, got)):
        if not want.pinned:
            notes.append(f"curried value {i}: {_show(args[i])} (not pinned by the recipe)")
        elif want.hash == have:
            notes.append(f"curried value {i}: matches ({want.shown})")
        else:
            differ = True
            notes.append(f"curried value {i}: DIFFERS: the recipe has {want.hash.hex()} ({want.shown}), the puzzle has {_show(args[i])}")
    return (Result.VALUES_DIFFER if differ else Result.MATCH), notes


def _compare_layer(recipe: Recipe, layer: Layer, mod_hash: bytes) -> tuple[Result, list[str]]:
    if layer.hash == mod_hash:
        if recipe.curry:
            return Result.VALUES_DIFFER, ["the code matches with no values curried; the recipe expects some"]
        return (Result.MATCH if recipe.curry == [] else Result.CODE_MATCH), ["the code matches, nothing curried"]
    parts = program.uncurry(layer.puzzle)
    if parts and program.tree_hash(parts[0]) == mod_hash:
        return _compare_values(recipe, parts[1])
    return Result.NO_MATCH, []


def verify_puzzle(recipe: Recipe, puzzle: SExp, times: int = 16) -> Report:
    variants, mods, warnings = rebuild(recipe, times)
    report = Report(recipe.name, warnings=warnings, layers=peel(puzzle), variants=variants, mod_hashes=mods)
    best = (Result.NO_MATCH, None, None, [])
    for li, layer in enumerate(report.layers):
        for vi, mod_hash in enumerate(mods):
            result, notes = _compare_layer(recipe, layer, mod_hash)
            if result > best[0]:
                best = (result, li, vi, notes)
    report.result, report.layer, report.variant, report.details = best
    if report.result == Result.NO_MATCH:
        report.details.append("no layer of the puzzle is this code: " + ", ".join(
            f"{l.name} {l.hash.hex()[:12]}…" for l in report.layers))
    elif report.variant:
        report.warnings.append(f"it matches variant {report.variant + 1}, not the most common build")
    return report


def verify_hash(recipe: Recipe, target: bytes, times: int = 16) -> Report:
    variants, mods, warnings = rebuild(recipe, times)
    report = Report(recipe.name, warnings=warnings, variants=variants, mod_hashes=mods)
    for vi, mod_hash in enumerate(mods):
        if target == mod_hash:
            report.result, report.variant = Result.CODE_MATCH, vi
            report.details.append("the hash is the code itself, with nothing curried")
            break
        if recipe.curry and all(v.pinned for v in recipe.curry):
            if target == program.curried_hash(mod_hash, [v.hash for v in recipe.curry]):
                report.result, report.variant = Result.MATCH, vi
                report.details.append("the hash is the code curried with the recipe's values")
                break
    if report.result == Result.NO_MATCH:
        report.details.append("no match. A hash alone cannot be unwrapped: if the coin is wrapped "
                              "(a CAT, a singleton), use a revealed puzzle or the inner puzzle hash")
        if recipe.curry and not all(v.pinned for v in recipe.curry):
            report.details.append("the recipe leaves some values open, which a hash cannot be checked against")
    return report
