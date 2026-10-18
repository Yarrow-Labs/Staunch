# How it works

This document is for auditors and contributors. It says what Staunch checks,
what it trusts, what it cannot tell you, and where each step lives in the code.

## The steps

1. **Read the recipe** (`staunch/recipe.py`). The JSON is checked strictly:
   unknown fields, wrong types and paths that leave the checkout are refused.
   Every curried value becomes a 32-byte tree hash, or "open" for `{"any": true}`.
2. **Preflight** (`verify.preflight`). Refuse unless the installed compiler is
   exactly the recipe's version, every file exists, and, if the recipe names a
   commit, the checkout is at that commit with no uncommitted changes to the
   recipe's files.
3. **Rebuild** (`staunch/build.py`, `verify.rebuild`). Compile the source N times
   (16 by default), each in a new Python process and a new scratch folder,
   through `clvm_tools_rs.compile_clvm`. Each distinct program is a *variant*.
   Its *mod hash* is its tree hash, with any `precurry` values curried in.
4. **Get the target** (`staunch/fetch.py`, or the command line). A revealed
   puzzle in hex, a coin from a node, or a bare puzzle hash. A node's answer is
   checked: the revealed puzzle must hash to the coin's puzzle hash.
5. **Search** (`verify._places`). Starting with the whole puzzle, go
   breadth-first through every program curried into it: uncurry a place, and
   queue each curried value that is a pair. This finds the code at any depth,
   inside any wrapper, without needing to know the wrapper. The search stops
   after `MAX_PLACES` (10,000) places, with a warning. Separately, `layers.peel`
   recognises Chia's standard layers (CAT2, singleton v1_1, standard wallet) for
   the report, and `layers.NAMES` names known puzzles along the way.
6. **Compare** (`verify._compare_place`). For every place and every variant:
   - the place's hash equals the mod hash: the code, with nothing curried; or
   - the place is curried (exactly the standard shape) and its mod hashes to
     the mod hash: the code; then each curried value's tree hash is compared
     with the recipe's.

   The strongest result wins; of equal results, the shallowest. A bare hash
   cannot be searched: it is compared with the mod hash, and with the mod hash
   curried with the recipe's values when the recipe pins them all.

## Why every comparison is by tree hash

A Chia puzzle hash *is* a tree hash, so comparing tree hashes compares exactly
what consensus compares. It also lets a recipe give a value by its hash alone,
and `program.curried_hash` computes a curried puzzle's hash from the hashes of
its parts, which `tests/test_program.py` checks against hashing the full program.

## What Staunch trusts

- **The compiler package** (`clvm_tools_rs`, the version the recipe names).
  Staunch checks the version, not the package's integrity: install it from a
  source you trust. If the compiler were wrong, Staunch's rebuild would be too.
- **The `clvm` package**, for parsing serialized programs.
- **git**, for the commit check.
- **Its own tables** in `layers.py`: the three standard layers it peels and the
  puzzles it names. `tests/test_layers.py` rebuilds each from Chia's published
  source. A wrong table would mislabel a report; it cannot cause a false match,
  because matching compares against the recipe's own rebuild only.

It does **not** trust the node (step 4), the recipe (step 1 and 2), or the
puzzle (it is only hashed and taken apart, never run).

## What Staunch cannot tell you

- **Whether the code is safe.** A MATCH says the source is what runs, nothing
  about whether the source is correct.
- **What the wrappers around the code do.** Staunch says where the code was
  found; the puzzles around it need their own recipes to be checked.
- **Code that is not curried in.** The search follows curried values. Code
  passed in a solution at spend time is not part of the puzzle, so it is not
  searched.
- **Values the recipe leaves open.** They are shown, not judged.
- **Rare compiler variants.** N compiles find a variant that appears half the
  time almost surely, but not one that appears once in a thousand. Raise `-n`
  for a deeper check.
- **What a hash wraps.** A bare puzzle hash cannot be unwrapped.

## Reading the code

| File | Lines | What it does |
|---|---|---|
| `staunch/program.py` | ~150 | Parse, hash, curry and uncurry CLVM values. Everything else rests on this; read it first |
| `staunch/recipe.py` | ~150 | Parse and check a recipe |
| `staunch/build.py` | ~90 | Compile in fresh processes; collect variants |
| `staunch/layers.py` | ~85 | The standard layers, `peel`, and the names used in reports |
| `staunch/verify.py` | ~240 | Preflight, rebuild, search, compare; the `Result` and `Report` types |
| `staunch/fetch.py` | ~50 | Read a coin from a full node through `chia rpc` |
| `staunch/cli.py` | ~130 | The command line and the printed report |

The tests (`tests/`) pair every check with a control that must fail. They run
offline against real mainnet puzzles saved in `tests/fixtures/mainnet`, and
Chia's own source in `tests/fixtures/chia_puzzles`:

| Test file | Covers |
|---|---|
| `test_program.py` | Hashing against Chia's known values, integer encoding, curry and uncurry, and the shapes `uncurry` must refuse |
| `test_layers.py` | The layer table rebuilt from Chia's source; peeling real coins; a look-alike that must not peel |
| `test_verify.py` | Matches on real coins, including an NFT's layers and a plot NFT; controls for a changed source byte, puzzle byte, value, compiler or commit; which match wins; the search bound; hashes; precurry; unstable sources; recipe errors |
| `test_cli.py` | The command line, `--coin` through a stand-in node, including one whose answer is wrong |

## The compiler findings behind the design

- **`clvm_tools_rs` is not always deterministic.** Some sources compile to more
  than one program, chosen at random per process. That is why each compile runs
  in a fresh process and every variant is kept.
- **`run` and `compile_clvm` can disagree.** With clvm_tools_rs 0.4.0, the `run`
  command builds Chia's `cat_v2.clsp` into a program that differs from the
  published CAT2 in one constant, every time. `compile_clvm`, which Chia's
  build uses, reproduces it on 0.4.0 and on 0.1.48. `run` also reports a missing
  include as text with exit code 0, while `compile_clvm` raises.
