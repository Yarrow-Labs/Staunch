# Changelog

## 0.1.1 (2026-10-22)

- A puzzle read from `--puzzle`, `--puzzle-file` or a node is refused if it is
  longer than 64 KiB (exit 2), because parsing a huge puzzle takes seconds and
  the largest real one we have is under 5 KB. `--max-puzzle-bytes N` raises or
  lowers the limit. Programs Staunch compiles itself are not limited.
- Releases are published to PyPI from a version tag by GitHub Actions.

## 0.1.0 (2026-10-18)

First release.

- `staunch verify` checks a recipe against a revealed puzzle, a coin (through a
  full node) or a puzzle hash, and `staunch build` prints a recipe's mod hash.
- Recipes: format 1, with a pinned compiler version, a commit check, curried
  and precurried values (`int`, `bytes`, `program`, `hash`, `any`).
- The whole puzzle is searched for the recipe's code, at any depth, and the
  report says where it was found. CAT2, singleton v1_1 and standard wallet
  layers are recognised and described. Code curried in several steps is found
  too, with its values in the order the code receives them.
- `--json` output, documented in the guide.
- Tested on 115 puzzles from Chia, TibetSwap and warp.green (each rebuilds to
  its published binary), and on live mainnet coins of the 32 seen in use, 9 of
  them warp.green's.
- Every source is compiled many times in fresh processes; every variant is reported.
