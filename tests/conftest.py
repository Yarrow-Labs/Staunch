import json
import shutil
from pathlib import Path

import pytest

from staunch import program

FIXTURES = Path(__file__).parent / "fixtures"
CHIA = FIXTURES / "chia_puzzles"
MAINNET = FIXTURES / "mainnet"
TIMES = 4   # compiles per check in tests; the default of 16 is for real use


def reveal(name: str):
    """A puzzle revealed on mainnet: tests/fixtures/mainnet/<name>.json."""
    return program.from_hex(json.loads((MAINNET / f"{name}.json").read_text())["puzzle_reveal"])


def recipe_json(name: str) -> dict:
    return json.loads((CHIA / f"{name}.recipe.json").read_text())


@pytest.fixture
def chia_copy(tmp_path):
    """A writable copy of Chia's puzzle fixtures, for recipes and edits."""
    dest = tmp_path / "chia_puzzles"
    shutil.copytree(CHIA, dest)
    return dest


def write_recipe(folder: Path, name: str, **changes) -> Path:
    raw = recipe_json(name)
    raw.update(changes)
    path = folder / f"{name}.test.json"
    path.write_text(json.dumps(raw))
    return path
