"""Verification against real mainnet puzzles, each with a control that must fail."""
import subprocess

import pytest
from clvm import SExp

from conftest import CHIA, TIMES, WARP, reveal, write_recipe
from staunch import build, layers, program, verify
from staunch.recipe import RecipeError, load
from staunch.verify import Result


def cat_values():
    """The real CAT coin's three curried values, as recipe values."""
    _, args = program.uncurry(reveal("cat_std"))
    return [{"bytes": args[0].as_atom().hex()}, {"bytes": args[1].as_atom().hex()},
            {"hash": program.tree_hash(args[2]).hex()}]


def test_cat_code_matches_a_real_cat(chia_copy):
    report = verify.verify_puzzle(load(CHIA / "cat_v2.recipe.json"), reveal("cat_std"), TIMES)
    assert report.result == Result.CODE_MATCH
    assert report.location == []          # the CAT2 code is the whole puzzle


def test_cat_with_every_value_pinned_is_a_full_match(chia_copy):
    r = load(write_recipe(chia_copy, "cat_v2", curry=cat_values()))
    report = verify.verify_puzzle(r, reveal("cat_std"), TIMES)
    assert report.result == Result.MATCH, report.details
    assert all("matches" in d for d in report.details)


def test_control_one_changed_curried_value(chia_copy):
    values = cat_values()
    tail = bytearray.fromhex(values[1]["bytes"])
    tail[-1] ^= 1
    values[1] = {"bytes": tail.hex()}
    report = verify.verify_puzzle(load(write_recipe(chia_copy, "cat_v2", curry=values)), reveal("cat_std"), TIMES)
    assert report.result == Result.VALUES_DIFFER
    assert [i for i, d in enumerate(report.details) if "DIFFERS" in d] == [1]


def test_control_wrong_number_of_values(chia_copy):
    report = verify.verify_puzzle(load(write_recipe(chia_copy, "cat_v2", curry=cat_values()[:2])),
                                  reveal("cat_std"), TIMES)
    assert report.result == Result.VALUES_DIFFER


def test_any_slot_is_reported_not_checked(chia_copy):
    values = cat_values()
    values[2] = {"any": True}
    report = verify.verify_puzzle(load(write_recipe(chia_copy, "cat_v2", curry=values)), reveal("cat_std"), TIMES)
    assert report.result == Result.MATCH
    assert "left open" in report.details[2]


def test_control_one_changed_byte_of_source(chia_copy):
    source = chia_copy / "cat_puzzles" / "cat_v2.clsp"
    text = source.read_text()
    assert text.count("(defconstant RING_MORPH_BYTE 0xcb)") == 1
    source.write_text(text.replace("(defconstant RING_MORPH_BYTE 0xcb)", "(defconstant RING_MORPH_BYTE 0xcc)"))
    report = verify.verify_puzzle(load(write_recipe(chia_copy, "cat_v2")), reveal("cat_std"), TIMES)
    assert report.result == Result.NO_MATCH


def test_control_one_changed_byte_of_the_puzzle():
    # Change one atom inside the CAT code itself, keep the real values.
    mod, args = program.uncurry(reveal("cat_std"))
    blob = bytearray(program.to_bytes(mod))
    at = blob.index(bytes([0x81, 0xcb]))          # RING_MORPH_BYTE as a one-byte atom
    blob[at + 1] = 0xcc
    tampered = program.curry(program.from_bytes(bytes(blob)), args)
    report = verify.verify_puzzle(load(CHIA / "cat_v2.recipe.json"), tampered, TIMES)
    assert report.result == Result.NO_MATCH


def test_inner_layer_found_through_the_cat():
    report = verify.verify_puzzle(load(CHIA / "standard_wallet.recipe.json"), reveal("cat_std"), TIMES)
    assert report.result == Result.CODE_MATCH
    assert report.location == ["CAT2, curried value 2"]


def test_singleton_code_matches_a_real_singleton():
    report = verify.verify_puzzle(load(CHIA / "singleton_v1_1.recipe.json"), reveal("singleton"), TIMES)
    assert report.result == Result.CODE_MATCH
    assert report.location == []


def test_control_wrong_code_for_the_coin():
    report = verify.verify_puzzle(load(CHIA / "cat_v2.recipe.json"), reveal("std"), TIMES)
    assert report.result == Result.NO_MATCH
    assert "not anywhere in this puzzle" in report.details[-1]


# --- searching inside wrappers ------------------------------------------------

def test_nft_state_layer_found_inside_the_singleton():
    report = verify.verify_puzzle(load(CHIA / "nft_state_layer.recipe.json"), reveal("nft"), TIMES)
    assert report.result == Result.CODE_MATCH
    assert report.location == ["singleton v1_1, curried value 1"]


def test_nft_ownership_layer_found_two_wrappers_down():
    report = verify.verify_puzzle(load(CHIA / "nft_ownership_layer.recipe.json"), reveal("nft"), TIMES)
    assert report.result == Result.CODE_MATCH
    assert report.location == ["singleton v1_1, curried value 1", "NFT state layer, curried value 3"]


def test_plot_nft_found_inside_the_older_singleton():
    report = verify.verify_puzzle(load(CHIA / "pool_member.recipe.json"), reveal("plot_nft"), TIMES)
    assert report.result == Result.CODE_MATCH
    assert report.location == ["singleton v1 (older), curried value 1"]


def test_control_code_not_in_the_nft():
    report = verify.verify_puzzle(load(CHIA / "pool_member.recipe.json"), reveal("nft"), TIMES)
    assert report.result == Result.NO_MATCH


def wallet(key: bytes) -> SExp:
    r = load(CHIA / "standard_wallet.recipe.json")
    return program.curry(program.from_bytes(build.compile_once(r.source, r.include)), [SExp.to(key)])


def test_the_shallowest_of_equal_matches_is_reported():
    holder = SExp.to([b"\x01", b"\x09"])           # any program; not a known puzzle
    puzzle = program.curry(holder, [wallet(b"\xaa" * 48), program.curry(holder, [wallet(b"\xbb" * 48)])])
    report = verify.verify_puzzle(load(CHIA / "standard_wallet.recipe.json"), puzzle, TIMES)
    assert report.result == Result.CODE_MATCH
    assert len(report.location) == 1 and report.location[0].endswith("curried value 0")


def test_a_deeper_full_match_beats_a_shallower_partial_one(chia_copy):
    holder = SExp.to([b"\x01", b"\x09"])
    puzzle = program.curry(holder, [wallet(b"\xaa" * 48), program.curry(holder, [wallet(b"\xbb" * 48)])])
    r = load(write_recipe(chia_copy, "standard_wallet", curry=[{"bytes": "bb" * 48}]))
    report = verify.verify_puzzle(r, puzzle, TIMES)
    assert report.result == Result.MATCH
    assert len(report.location) == 2


def test_the_search_is_bounded(monkeypatch):
    monkeypatch.setattr(verify, "MAX_PLACES", 1)
    report = verify.verify_puzzle(load(CHIA / "nft_ownership_layer.recipe.json"), reveal("nft"), TIMES)
    assert report.result == Result.NO_MATCH
    assert any("search stopped" in w for w in report.warnings)


# --- by hash ---------------------------------------------------------------

def wallet_pk():
    return program.uncurry(reveal("std"))[1][0].as_atom().hex()


def test_hash_of_a_wallet_coin_with_its_key_pinned(chia_copy):
    r = load(write_recipe(chia_copy, "standard_wallet", curry=[{"bytes": wallet_pk()}]))
    report = verify.verify_hash(r, program.tree_hash(reveal("std")), TIMES)
    assert report.result == Result.MATCH


def test_control_hash_with_the_wrong_key(chia_copy):
    pk = bytearray.fromhex(wallet_pk())
    pk[0] ^= 1
    r = load(write_recipe(chia_copy, "standard_wallet", curry=[{"bytes": pk.hex()}]))
    assert verify.verify_hash(r, program.tree_hash(reveal("std")), TIMES).result == Result.NO_MATCH


def test_hash_of_the_bare_code():
    report = verify.verify_hash(load(CHIA / "cat_v2.recipe.json"), layers.CAT_V2, TIMES)
    assert report.result == Result.CODE_MATCH


def test_hash_of_the_bare_code_with_curry_empty_is_a_full_match(chia_copy):
    r = load(write_recipe(chia_copy, "cat_v2", curry=[]))
    assert verify.verify_hash(r, layers.CAT_V2, TIMES).result == Result.MATCH


def test_control_hash_of_the_bare_code_when_values_are_expected(chia_copy):
    r = load(write_recipe(chia_copy, "cat_v2", curry=cat_values()))
    assert verify.verify_hash(r, layers.CAT_V2, TIMES).result == Result.VALUES_DIFFER


def test_a_wrapped_hash_cannot_be_unwrapped_and_says_so():
    report = verify.verify_hash(load(CHIA / "standard_wallet.recipe.json"),
                                program.tree_hash(reveal("cat_std")), TIMES)
    assert report.result == Result.NO_MATCH
    assert "cannot be unwrapped" in report.details[0]


# --- code curried in steps -------------------------------------------------

def wallet_code() -> SExp:
    r = load(CHIA / "standard_wallet.recipe.json")
    return program.from_bytes(build.compile_once(r.source, r.include))


def in_two_steps() -> SExp:
    """The wallet code curried with one value, then with another on top."""
    return program.curry(program.curry(wallet_code(), [SExp.to(b"\x11" * 32)]), [SExp.to(b"\x22" * 48)])


def test_code_curried_in_two_steps_is_found():
    report = verify.verify_puzzle(load(CHIA / "standard_wallet.recipe.json"), in_two_steps(), TIMES)
    assert report.result == Result.CODE_MATCH
    assert report.location == []
    assert "2 steps" in report.details[0]
    assert len(report.details) == 3                     # the note, then both values in order


def test_values_from_every_step_are_checked_in_order(chia_copy):
    r = load(write_recipe(chia_copy, "standard_wallet", curry=[{"bytes": "11" * 32}, {"bytes": "22" * 48}]))
    assert verify.verify_puzzle(r, in_two_steps(), TIMES).result == Result.MATCH


def test_control_values_from_two_steps_in_the_wrong_order(chia_copy):
    r = load(write_recipe(chia_copy, "standard_wallet", curry=[{"bytes": "22" * 48}, {"bytes": "11" * 32}]))
    assert verify.verify_puzzle(r, in_two_steps(), TIMES).result == Result.VALUES_DIFFER


def test_three_steps_inside_a_wrapper(chia_copy):
    three = program.curry(in_two_steps(), [SExp.to(b"\x33")])
    puzzle = program.curry(SExp.to([b"\x01", b"\x09"]), [three])
    r = load(write_recipe(chia_copy, "standard_wallet",
                          curry=[{"bytes": "11" * 32}, {"bytes": "22" * 48}, {"bytes": "33"}]))
    report = verify.verify_puzzle(r, puzzle, TIMES)
    assert report.result == Result.MATCH
    assert len(report.location) == 1 and "3 steps" in report.details[0]


def test_a_precurried_mod_takes_the_outer_values_only(chia_copy):
    """A published mod with values baked in: `precurry` names them, `curry` the rest."""
    r = load(write_recipe(chia_copy, "standard_wallet",
                          precurry=[{"bytes": "11" * 32}], curry=[{"bytes": "22" * 48}]))
    report = verify.verify_puzzle(r, in_two_steps(), TIMES)
    assert report.result == Result.MATCH
    assert len(report.details) == 1                     # one step on top of the published mod


def test_control_a_wrong_precurry_is_not_the_code(chia_copy):
    r = load(write_recipe(chia_copy, "standard_wallet", precurry=[{"bytes": "99" * 32}]))
    assert verify.verify_puzzle(r, in_two_steps(), TIMES).result == Result.NO_MATCH


@pytest.mark.parametrize("recipe, coin, location", [
    ("portal_receiver", "warp_portal", ["singleton v1_1, curried value 1"]),
    ("message_coin", "warp_message_coin", []),
    ("burn_inner_puzzle", "warp_burn", ["CAT2, curried value 2"]),
])
def test_warp_green_puzzles_curried_in_two_steps_on_mainnet(recipe, coin, location):
    report = verify.verify_puzzle(load(WARP / f"{recipe}.recipe.json"), reveal(coin), TIMES)
    assert report.result == Result.CODE_MATCH
    assert report.location == location
    assert "2 steps" in report.details[0]


# --- an unstable source -------------------------------------------------

def test_two_variants_are_reported_and_either_can_match(monkeypatch):
    r = load(CHIA / "standard_wallet.recipe.json")
    real = build.compile_once(r.source, r.include)
    other = program.to_bytes(SExp.to([b"\x01", b"\x01"]))
    outputs = iter([other, real, other, other])
    monkeypatch.setattr(build, "compile_once", lambda source, include: next(outputs))
    report = verify.verify_puzzle(r, reveal("std"), 4)
    assert report.result == Result.CODE_MATCH
    assert [v.count for v in report.build.variants] == [3, 1]
    assert report.variant == 1
    assert any("unstable" in w for w in report.warnings)
    assert any("variant 2" in w for w in report.warnings)


# --- refusals -------------------------------------------------------------

def test_refuses_a_different_compiler_version(chia_copy):
    r = load(write_recipe(chia_copy, "cat_v2", compiler="clvm_tools_rs 0.1.48"))
    with pytest.raises(RecipeError, match="0.1.48"):
        verify.verify_puzzle(r, reveal("cat_std"), TIMES)


def test_refuses_a_missing_include(chia_copy):
    r = load(write_recipe(chia_copy, "cat_v2", include=["."]))
    with pytest.raises(build.BuildError, match="cat_truths"):
        verify.verify_puzzle(r, reveal("cat_std"), TIMES)


def git(folder, *args):
    subprocess.run(["git", "-C", str(folder), *args], check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(folder), "PATH": "/usr/bin:/bin"})


def test_commit_is_checked(chia_copy, tmp_path):
    git(chia_copy, "init", "-q")
    git(chia_copy, "add", ".")
    git(chia_copy, "commit", "-qm", "fixture")
    head = subprocess.run(["git", "-C", str(chia_copy), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    outside = tmp_path / "recipes"
    outside.mkdir()
    good = load(write_recipe(outside, "cat_v2", commit=head), root=chia_copy)
    assert verify.preflight(good) == []
    wrong = load(write_recipe(outside, "cat_v2", commit="0" * 40), root=chia_copy)
    with pytest.raises(RecipeError, match="checkout is at"):
        verify.preflight(wrong)
    (chia_copy / "cat_puzzles" / "cat_v2.clsp").write_text("(mod () 1)")
    with pytest.raises(RecipeError, match="uncommitted"):
        verify.preflight(good)


def test_without_git_the_commit_is_a_warning(chia_copy, tmp_path):
    r = load(write_recipe(chia_copy, "cat_v2", commit="0" * 40))
    if subprocess.run(["git", "-C", str(chia_copy), "rev-parse"], capture_output=True).returncode == 0:
        pytest.skip("the temporary folder is inside a git checkout")
    assert any("not a git checkout" in w for w in verify.preflight(r))


@pytest.mark.parametrize("bad, message", [
    ({"staunch": 2}, "must be 1"),
    ({"surprise": 1}, "unknown fields"),
    ({"curry": [{"hash": "00"}]}, "32 bytes"),
    ({"curry": [{"int": "5"}]}, "JSON integer"),
    ({"curry": [{"any": False}]}, "any"),
    ({"curry": [{"int": 1, "bytes": "01"}]}, "exactly one key"),
    ({"curry": [{"bytes": 7}]}, "hex string"),
    ({"curry": [{"program": "ff01"}]}, "serialized program"),
    ({"curry": {"int": 1}}, "list of values"),
    ({"source": "../outside.clsp"}, "outside the checkout"),
    ({"include": ["/etc"]}, "outside the checkout"),
    ({"include": "."}, "list of folders"),
    ({"name": 5}, "must be a string"),
])
def test_recipe_errors(chia_copy, bad, message):
    with pytest.raises(RecipeError, match=message):
        load(write_recipe(chia_copy, "cat_v2", **bad))
