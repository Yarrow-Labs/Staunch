# Changelog

## 0.1.0 (unreleased)

First release.

- `staunch verify` checks a recipe against a revealed puzzle, a coin (through a
  full node) or a puzzle hash, and `staunch build` prints a recipe's mod hash.
- Recipes: format 1, with a pinned compiler version, a commit check, curried
  and precurried values (`int`, `bytes`, `program`, `hash`, `any`).
- The whole puzzle is searched for the recipe's code, at any depth, and the
  report says where it was found. CAT2, singleton v1_1 and standard wallet
  layers are recognised and described.
- Tested on 115 puzzles from Chia, TibetSwap and warp.green (each rebuilds to
  its published binary), and on live mainnet coins of the 23 seen in use.
- Every source is compiled many times in fresh processes; every variant is reported.
