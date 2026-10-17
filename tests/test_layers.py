"""The layer table is right, and peeling real mainnet puzzles finds the layers."""
import pytest

from conftest import CHIA, TIMES, reveal
from staunch import build, layers, program
from staunch.recipe import load


@pytest.mark.parametrize("recipe, constant, size", [
    ("cat_v2", layers.CAT_V2, 1672),
    ("singleton_v1_1", layers.SINGLETON_V1_1, 967),
    ("standard_wallet", layers.STANDARD_WALLET, 227),
])
def test_each_constant_rebuilds_from_chia_source(recipe, constant, size):
    r = load(CHIA / f"{recipe}.recipe.json")
    variants = build.compile_many(r.source, r.include, TIMES)
    assert len(variants) == 1, "Chia's own puzzle should compile one way"
    assert len(variants[0].program) == size
    assert program.tree_hash(program.from_bytes(variants[0].program)) == constant


def test_peel_a_cat_held_by_a_wallet():
    got = layers.peel(reveal("cat_std"))
    assert [l.name for l in got] == ["CAT2", "standard wallet"]
    assert len(got[0].facts["asset id (TAIL hash)"]) == 64
    assert len(got[1].facts["synthetic public key"]) == 96


def test_peel_a_singleton_stops_at_its_unknown_inner_puzzle():
    got = layers.peel(reveal("singleton"))
    assert [l.name for l in got] == ["singleton v1_1", "unknown"]
    assert len(got[0].facts["launcher id"]) == 64


def test_peel_a_plain_wallet_coin():
    assert [l.name for l in layers.peel(reveal("std"))] == ["standard wallet"]


def test_a_look_alike_with_the_wrong_argument_count_is_not_peeled():
    # The CAT2 code curried with two values instead of three: not a CAT.
    mod, args = program.uncurry(reveal("cat_std"))
    fake = program.curry(mod, args[:2])
    assert [l.name for l in layers.peel(fake)] == ["unknown"]
