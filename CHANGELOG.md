# Changelog

## 0.1.0 (unreleased)

First release.

- `staunch verify` checks a recipe against a revealed puzzle, a coin (through a
  full node) or a puzzle hash, and `staunch build` prints a recipe's mod hash.
- Recipes: format 1, with a pinned compiler version, a commit check, curried
  and precurried values (`int`, `bytes`, `program`, `hash`, `any`).
- Standard layers peeled: CAT2, singleton v1_1, standard wallet.
- Every source is compiled many times in fresh processes; every variant is reported.
