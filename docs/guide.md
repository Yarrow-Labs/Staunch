# Checking a contract

This guide is for anyone who wants to know whether a coin on Chia is running
the code its project says it is: a user about to deposit, a wallet, an
explorer, an auditor.

## 1. What you need

- **Staunch:** `pip install staunch`. Python 3.10 or later.
- **The project's source, checked out with git**, at the commit its recipe
  names: `git clone <repo> && git -C <folder> checkout <commit>`.
- **The project's recipe.** A small JSON file, usually published in the
  project's repo. If the project has none, you can write one yourself: see
  [Writing a recipe](recipes.md).
- **The right compiler.** The recipe names one, for example `clvm_tools_rs
  0.4.0`. Staunch refuses to build with any other, because a different
  compiler can give different bytes. Install it with
  `pip install clvm_tools_rs==0.4.0`.
- **Something to check:** a revealed puzzle, a coin id or a puzzle hash.

## 2. Getting something to check

**A coin that has been spent** has revealed its whole puzzle on chain. That is
the best thing to check, because Staunch can unwrap it layer by layer.

- *With a full node:* `staunch verify RECIPE --coin COIN_ID`. Staunch asks your
  node through `chia rpc` (use `--chia PATH` if `chia` is not on your PATH).
  It checks that the puzzle the node returns really hashes to the coin, so a
  wrong node cannot fool it.
- *Without a node:* most block explorers show a spend's "puzzle reveal" in hex.
  Save it to a file and use `--puzzle-file FILE`, or paste it with
  `--puzzle HEX`.

Coins of the same kind share the same code. If the coin you care about is
unspent, check any spent coin of the same contract, then check your coin's hash
(below).

**A coin that has not been spent** has shown only its puzzle hash. Use
`--hash PUZZLE_HASH`, or `--coin` and Staunch will fall back to the hash itself.
A hash cannot be unwrapped, so this works only when:

- the hash is of the project's own puzzle, not of a wrapper around it (for a
  CAT or a singleton, check the inner puzzle's hash instead), and
- the recipe pins every curried value, because a hash cannot be compared with a
  value left open.

## 3. Reading the report

```
MATCH: Chia CAT v2, one token (asset id db1a9020...)
  This is the recipe's code, with every value the recipe pins.
  Code found at layer 1 of 2: CAT2
  - curried value 0: matches (bytes 37bef360...)
  - curried value 1: matches (bytes db1a9020...)
  - curried value 2: a program with tree hash e58b2cfc... (left open by the recipe)

Layers, outermost first:
  1. CAT2, puzzle hash a11df965...
       asset id (TAIL hash): db1a9020...
  2. standard wallet, puzzle hash e58b2cfc...
       synthetic public key: aaa3cc04...

Build: 16 compiles, one program (stable)
  variant 1: mod hash 37bef360... (16 of 16)
```

- **The first line is the answer.** See the table below.
- **"Code found at layer"** says which layer of the coin is the recipe's code.
  A recipe for a wallet puzzle can be found inside a CAT, for example.
- **Curried values** are values baked into the code, such as a token's asset id
  or an owner's key. Each one the recipe pins is checked. A value the recipe
  leaves open is shown, so you can judge it yourself.
- **Layers** lists every layer Staunch unwrapped, with what it learned from
  each. A layer it does not know is listed as "unknown".
- **Build** says how many compiles ran and how many different programs they
  gave. "Stable" is what you want to see.

| Answer | What it means | What to do |
|---|---|---|
| MATCH | The code and every pinned value are what the recipe says | Nothing. Read the source, or have it audited, knowing it is what runs |
| MATCH (code only) | The code is right; the recipe pins no values | Look at the curried values listed. Are they the ones you expect? |
| NO MATCH, different values | Right code, but a value differs (named in the report) | Find out why. A different asset id, owner or setting may be a different contract |
| NO MATCH | This coin is not running the recipe's code | Don't rely on that source for this coin. Check you have the right recipe and coin |

Add `--json` for the same report as JSON, for scripts and services.

## 4. When Staunch refuses

Staunch exits with code 2 and a line starting `Refused:` when it cannot
follow a recipe exactly. It never guesses its way round a problem.

| Message | Cause | Fix |
|---|---|---|
| `the recipe needs clvm_tools_rs X; this machine has Y` | Wrong compiler version | `pip install clvm_tools_rs==X` (a virtual environment per version helps) |
| `the checkout is at ...; the recipe names ...` | Wrong commit checked out | `git -C <folder> checkout <commit>` |
| `the recipe's files have uncommitted changes` | Local edits to the source | `git -C <folder> stash`, or check out a clean copy |
| `not found: ...` | Wrong `--root`, or a path the recipe gets wrong | Point `--root` at the project's checkout |
| `points outside the checkout` | A recipe path leads out of the checkout | The recipe is wrong. Staunch never reads outside the checkout |
| `compile failed ...` | The source does not compile as the recipe says | Often a missing `include` folder; the message names the file |
| `the node's puzzle reveal does not hash to the coin's puzzle hash` | The node returned a wrong puzzle | Use another node; do not trust this one |

## 5. Warnings worth reading

- **"this source is unstable"**: the compiler turned the source into more than
  one program. Staunch checks against all of them and says which one matched.
  It is not a sign of foul play: it is a known compiler behaviour. But a
  project should fix it, because users' tools may build a different variant.
  Use `--strict` to make it an error (exit 3).
- **"the recipe names no commit"**: Staunch cannot tell which version of the
  source you checked. Prefer recipes that name one.
- **"the coin is unspent"**: only its hash could be checked; see section 2.

## 6. Command reference

```
staunch build  RECIPE [--root DIR] [-n N] [--strict]
staunch verify RECIPE [--root DIR] [-n N] [--strict] [--json] [--chia PATH]
               (--puzzle HEX | --puzzle-file FILE | --coin COIN_ID | --hash PUZZLE_HASH)
```

- `--root DIR`: the checkout the recipe's paths start from. Default: the
  recipe's own folder.
- `-n N`: compiles per check. Default 16. More finds rarer variants and takes
  longer.
- `--strict`: exit 3 if the source compiles more than one way.

Exit codes: 0 match · 1 no match · 2 refused · 3 unstable (with `--strict`).
