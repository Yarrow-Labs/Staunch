# Staunch

**Check that a Chialisp contract's published source is the code on chain.**

On Ethereum, a "verified" badge tells you a contract's published source is the
code that actually runs. Chia has had nothing like it. Staunch fills that gap:
it rebuilds a puzzle from its source, searches the coin you are looking at for
that code, at any depth inside its wrappers, and tells you whether it is there,
with the right values, and if not, exactly what differs.

```
$ staunch verify examples/chia_puzzles/cat_v2_one_token.json --root chia_puzzles --puzzle-file examples/cat_coin.hex
MATCH: Chia CAT v2, one token (asset id db1a9020...)
  This is the recipe's code, with every value the recipe pins.
  Code found in: the whole puzzle
  - curried value 0: matches (bytes 37bef360...)
  - curried value 1: matches (bytes db1a9020...)
  - curried value 2: a program with tree hash e58b2cfc... (left open by the recipe)
```

Staunch answers **"is this the code I was told?"** It does not answer "is this
code safe?" Reading the code is still up to you, or your auditor. Staunch makes
sure what they read is what runs.

## Try it in two minutes

You need Python 3.10 or later and git.

```sh
git clone https://github.com/Yarrow-Labs/Staunch && cd Staunch
pip install -e .                         # from v0.1.0: pip install staunch

# Chia's own puzzle source, at the commit the example recipes name
git clone https://github.com/Chia-Network/chia_puzzles
git -C chia_puzzles checkout 0.20.3

# Is this real mainnet CAT coin running Chia's CAT2 code?
staunch verify examples/chia_puzzles/cat_v2.json --root chia_puzzles --puzzle-file examples/cat_coin.hex
```

Then try `cat_v2_one_token.json`, which also checks which token it is.

## What you can check

| You have | Command |
|---|---|
| a puzzle revealed in a spend (hex) | `staunch verify RECIPE --puzzle HEX` or `--puzzle-file FILE` |
| a coin id, and a synced Chia full node | `staunch verify RECIPE --coin COIN_ID` |
| a puzzle hash only | `staunch verify RECIPE --hash PUZZLE_HASH` |
| a source you want to publish | `staunch build RECIPE` prints its mod hash |

A **recipe** is a small JSON file that says how to rebuild a puzzle: which file,
which compiler, which commit, and which values are baked in. Projects publish one
beside their source.

## The four answers

| Answer | Meaning | `--json` | Exit code |
|---|---|---|---|
| **MATCH** | The recipe's code, with every value the recipe pins | `match` | 0 |
| **MATCH (code only)** | The recipe's code; the recipe pins no values, so none were checked | `code-match` | 0 |
| **NO MATCH**, different values | The recipe's code, but a curried value differs; each one is named | `values-differ` | 1 |
| **NO MATCH** | The recipe's code is nowhere in the puzzle | `no-match` | 1 |

Staunch exits 2 when it refuses to run, for example with the wrong compiler
version or a checkout at the wrong commit. It never guesses.

## Documentation

- [Checking a contract](docs/guide.md): where to get a puzzle, reading the
  report, common refusals and what to do.
- [Writing a recipe](docs/recipes.md): for projects that want their contracts
  verifiable. Every field, with examples.
- [How it works](docs/how-it-works.md): for auditors. What Staunch checks, what
  it trusts, what it cannot tell you, and a map of the code.

## Why Chia needs a tool for this

- **The code is only visible after a coin is spent.** Before that, the chain
  holds just a hash of it.
- **Puzzles come in layers.** An NFT is a singleton around a state layer around
  an ownership layer around a royalty program, each with values baked in.
  Staunch searches every layer, including wrappers it has never seen, and
  code whose values were curried in more than one step.
- **The compiler is not always deterministic.** It can turn one source into
  more than one program. Staunch compiles each source many times and reports
  every result it gets.
- **How you call the compiler matters.** The `run` command builds Chia's own
  CAT2 source into different bytes from the published puzzle. Staunch uses
  the same compiler function as Chia's build, and reproduces it exactly.

## Status

Version 0.1. Tested on 115 puzzles from Chia, TibetSwap and warp.green, and on
live mainnet coins of 32 of them. See [CHANGELOG.md](CHANGELOG.md).

## Licence

Apache-2.0. `tests/fixtures/chia_puzzles` holds unmodified files from
[Chia-Network/chia_puzzles](https://github.com/Chia-Network/chia_puzzles),
also Apache-2.0, and `tests/fixtures/warp_green` unmodified files from
[warpdotgreen/cli](https://github.com/warpdotgreen/cli), under the MIT licence.
Contributions are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md).
