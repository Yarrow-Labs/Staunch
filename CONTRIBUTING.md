# Contributing

Issues and pull requests are welcome.

## Set up

```sh
python -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

The tests take under a minute and need no network.

## Ground rules

- **Every check needs a control that must fail.** A test that a match is found
  comes with one where it must not be. A check that only ever passes proves nothing.
- **Never guess.** If Staunch cannot be sure, it refuses or says "unknown".
- **Keep the code readable by an auditor.** Short functions, plain names, a
  comment where the reason is not obvious. `docs/how-it-works.md` maps the code;
  update it when you move things.
- **New standard layers** go in `staunch/layers.py`, with a test that rebuilds
  the layer from its published source and a real mainnet puzzle that uses it.

## Reporting a wrong answer

A wrong MATCH is the worst bug Staunch can have. If you find one, open an issue
with the recipe, the puzzle or coin id, and the report (`--json`).
