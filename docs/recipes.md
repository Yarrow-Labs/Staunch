# Writing a recipe

This guide is for projects that want anyone to be able to check that their
contracts on chain are the source they publish. It takes one small file per
puzzle.

## 1. A first recipe

Put a file such as `staunch/my_puzzle.json` in your repo:

```json
{
  "staunch": 1,
  "name": "My project: vault",
  "source": "puzzles/vault.clsp",
  "include": ["puzzles/include"],
  "compiler": "clvm_tools_rs 0.4.0",
  "repo": "https://github.com/me/my-project",
  "commit": "<the commit your deployment was built from>"
}
```

Check it rebuilds, from your repo's root:

```sh
staunch build staunch/my_puzzle.json --root .
```

It prints your puzzle's **mod hash**: the hash of the code before any values
are curried in. That should be the mod hash your deployment uses. If it prints
more than one line, read section 5.

Then check it against a real coin of yours:

```sh
staunch verify staunch/my_puzzle.json --root . --coin <a spent coin id>
```

## 2. Every field

| Field | Required | What it is |
|---|---|---|
| `staunch` | yes | The recipe format version. Always `1` for now |
| `name` | no | Shown in reports. Default: the source path |
| `source` | yes | The `.clsp` file to compile, relative to the checkout root |
| `include` | no | Folders the compiler searches for `(include ...)` files, in order |
| `compiler` | yes | `"clvm_tools_rs <version>"`, the exact version you built with |
| `repo` | no | Where the source lives. Shown, not checked |
| `commit` | no, but use it | The git commit the source must be at. Staunch refuses any other commit, and uncommitted changes |
| `precurry` | no | Values baked into your published mod before deployment (section 4) |
| `curry` | no | The values curried in at deployment (section 3). Leave it out to check the code alone |

Paths are relative to the checkout root (`--root`, or the recipe's own folder).
They cannot point outside it.

**Find your compiler version** with `pip show clvm_tools_rs`. Chia's own
puzzles reproduce on 0.4.0. If you built with something else, such as the `run`
command or another tool, check that `staunch build` gives your deployed hash:
the `run` command does not always give the same bytes as the compiler function
Staunch uses.

## 3. Curried values

Most deployed puzzles have values curried in: an owner's key, a token's asset
id, a fee rate. List them in `curry`, in the order your code receives them.
If your deployment curries in steps (some values first, more on top later),
list them all, first step first. Each value is one of:

| Form | Use it for | Example |
|---|---|---|
| `{"int": n}` | A number. Written the way CLVM stores it | `{"int": 1000}` |
| `{"bytes": "hex"}` | An atom: a hash, key, id | `{"bytes": "37bef360..."}` |
| `{"program": "hex"}` | Any value, as serialized CLVM: a list, a struct, a puzzle | `{"program": "ff01ff0280"}` |
| `{"hash": "hex"}` | Any value, known only by its tree hash | `{"hash": "e58b2cfc..."}` |
| `{"any": true}` | A slot that differs from coin to coin, such as each user's owner | `{"any": true}` |

How to choose:

- **Pin everything that makes your contract yours**: asset ids, admin or
  oracle keys, fee settings, other contracts' hashes. That is what users
  need checked.
- **Leave open what differs per coin**, such as each user's own puzzle. The
  report still shows those values.
- **Use `hash` for a value that is itself a puzzle**, such as an inner puzzle
  you don't want to publish in full. Staunch compares by tree hash anyway, so
  this checks exactly as well.
- A puzzle hash can only be checked against a recipe that pins every value. If
  you want unspent coins to be checkable, publish a recipe per deployment that
  pins them all. If you curry in steps, also see section 4.

Example: a CAT of one token, with any owner:

```json
"curry": [
  {"bytes": "37bef360ee858133b69d595a906dc45d01af50379dad515eb9518abb7c1d2a7a"},
  {"bytes": "<your asset id>"},
  {"any": true}
]
```

## 4. Precurried mods

Some projects publish a mod hash that already has values baked in. For example,
a vault may curry in the hashes of the contracts it works with, then publish
*that* as "the vault mod", and deployments curry the rest on top. On chain that
is two curries, one inside the other.

List the inner values in `precurry` and the outer ones in `curry`. Then
`staunch build` prints your published mod hash, and `verify` compares the outer
values only.

You can also leave `precurry` out and list every value in `curry`, inner ones
first: a revealed puzzle checks the same either way. The difference is a bare
puzzle hash, which Staunch can only rebuild one curry step on top of the mod
hash, so it needs the inner values in `precurry`.

## 5. If your source compiles more than one way

`staunch build` printing several hashes means the compiler is giving different
programs from the same source, at random. Chialisp's compiler does this in some
cases, and every version so far has had it. It matters because a user, wallet
or auditor rebuilding your source will sometimes get a hash that differs from
your deployment.

Patterns known to trigger it:

- several `defun-inline` helpers together with a two-branch dispatch;
- an `assign` with more than one binding.

Turning one inline helper into a `defun`, or passing values to a named function
instead of a multi-binding `assign`, has fixed every case seen so far. Run
`staunch build --strict -n 64` until you get one hash.

## 6. Publishing checklist

- [ ] The recipe names the commit your deployment was built from.
- [ ] `staunch build --strict` gives exactly one hash, and it is your deployed mod hash.
- [ ] `staunch verify` against a real spent coin gives MATCH.
- [ ] Every value that makes the contract yours is pinned; open slots are only per-coin values.
- [ ] Link the recipe from your README, so users can find it.
