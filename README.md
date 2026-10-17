# Staunch

Check that a Chialisp source is the puzzle on chain.

Ethereum users can see a "verified" badge that says a contract's published
source is the code that runs. Chia has had nothing like it. Staunch rebuilds a
puzzle from its source and compares it with a coin's puzzle, layer by layer,
and says one of:

- **MATCH**: this is the recipe's code, with the recipe's curried values;
- **MATCH (code only)**: the code is the same; the recipe pins no values;
- **NO MATCH: same code, different curried values**, naming each one that differs;
- **NO MATCH**: this is not the recipe's code.

It says whether the code is what you were told. It does not say whether the
code is safe.

## Install

    pip install staunch            # from v0.1.0
    pip install -e '.[test]'       # from a checkout

Python 3.10 or later. The recipe names a compiler version, and Staunch refuses
to build with any other: install the one the recipe asks for.

## Use

    staunch build  RECIPE                 # print the mod hash, and every variant if unstable
    staunch verify RECIPE --puzzle HEX    # a revealed puzzle
    staunch verify RECIPE --coin ID       # a coin, through a synced full node's `chia rpc`
    staunch verify RECIPE --hash HASH     # a puzzle hash

Add `--json` for a machine-readable report, `-n` for the number of compiles
(default 16), and `--strict` to fail when a source compiles more than one way.
Exit codes: 0 match, 1 no match, 2 refused or error, 3 unstable (with `--strict`).

## The recipe

A project publishes a recipe beside its source:

```json
{
  "staunch": 1,
  "name": "Chia CAT v2",
  "source": "puzzles/cat_puzzles/cat_v2.clsp",
  "include": ["puzzles", "puzzles/cat_puzzles"],
  "compiler": "clvm_tools_rs 0.4.0",
  "repo": "https://github.com/Chia-Network/chia_puzzles",
  "commit": "d122456feeef55708d354a065623037bfa010714",
  "curry": [{"bytes": "37bef360..."}, {"any": true}, {"any": true}]
}
```

- Paths start from the checkout root: the recipe's folder, or `--root`.
- With `commit`, Staunch refuses a checkout at any other commit or with
  uncommitted changes to the recipe's files.
- `curry` lists the values curried onto the code. Leave it out to check the
  code alone. Each value is `{"int": n}`, `{"bytes": "hex"}`,
  `{"program": "serialized hex"}`, `{"hash": "tree hash"}` (a value known only
  by its hash), or `{"any": true}` (a slot left open, such as one coin's owner).
- `precurry` lists values already baked into a published mod. Some projects
  publish their mod hash that way, and comparing the bare code would always
  fail.

## Why Chia needs care

- **The code shows only when a coin is spent.** Before that the chain holds
  only its hash. A hash cannot be unwrapped, so check a wrapped coin through a
  revealed puzzle from any spend of the same kind, or use the inner hash.
- **Puzzles come in layers.** Staunch peels Chia's standard layers (CAT2, the
  singleton v1_1 top layer, the standard wallet) and checks the recipe against
  each layer. Any other layer is reported as unknown, never guessed.
- **The compiler is not always deterministic.** `clvm_tools_rs` can compile one
  source to more than one program. Staunch compiles each source many times,
  each in a fresh process, and reports every variant it finds.
- **How you compile matters.** On Chia's own `cat_v2.clsp`, the `run` command
  gives different bytes from the published puzzle, while `compile_clvm` (what
  Chia's build uses, and what Staunch uses) reproduces it exactly. `run` also
  reports a missing include as text with exit code 0.

## Tests

    pytest

Tests rebuild Chia's standard puzzles from source and check them against
real mainnet coins (`tests/fixtures`). Every check comes with a control that
must fail: a changed byte of source, a changed byte of the puzzle, a changed
curried value, the wrong compiler version, the wrong commit.

## Licence

Apache-2.0. `tests/fixtures/chia_puzzles` holds unmodified files from
Chia-Network/chia_puzzles, also Apache-2.0.
