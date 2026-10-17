import pytest
from clvm import SExp

from staunch import program
from staunch.layers import CAT_V2


def test_int_atom_is_the_shortest_spelling():
    cases = {0: b"", 1: b"\x01", 127: b"\x7f", 128: b"\x00\x80", 255: b"\x00\xff",
             256: b"\x01\x00", -1: b"\xff", -128: b"\x80", -129: b"\xff\x7f"}
    for value, atom in cases.items():
        assert program.int_atom(value) == atom, value
    for value in range(-70000, 70000, 37):
        assert int.from_bytes(program.int_atom(value) or b"\x00", "big", signed=True) == value


def test_tree_hash_of_an_atom_and_a_pair():
    # Values from Chia's own sha256tree: hash(nil), hash(1), hash((1 . 1)).
    assert program.tree_hash(SExp.to(b"")).hex() == \
        "4bf5122f344554c53bde2ebb8cd2b7e3d1600ad631c385a5d7cce23c7785459a"
    assert program.tree_hash(SExp.to(1)).hex() == \
        "9dcf97a184f32623d11a73124ceb99a5709b083721e878a16d78f596718ba7b2"
    one = program.tree_hash(SExp.to(1))
    assert program.tree_hash(SExp.to((1, 1))) == program.pair_hash(one, one)


def test_curry_round_trip_and_hash_from_hashes():
    mod = SExp.to([b"\x02", (b"\x01", b"\x05"), b"\x01"])
    args = [SExp.to(b"\xaa" * 32), SExp.to([1, 2, 3]), SExp.to(b"")]
    curried = program.curry(mod, args)
    back = program.uncurry(curried)
    assert back is not None
    assert program.tree_hash(back[0]) == program.tree_hash(mod)
    assert [program.tree_hash(a) for a in back[1]] == [program.tree_hash(a) for a in args]
    assert program.curried_hash(program.tree_hash(mod), [program.tree_hash(a) for a in args]) == \
        program.tree_hash(curried)
    assert program.curried_hash(program.tree_hash(mod), []) == program.tree_hash(program.curry(mod, []))


def test_uncurry_takes_off_one_curry_only():
    mod = SExp.to(b"\x07")
    inner = program.curry(mod, [SExp.to(1)])
    outer = program.curry(inner, [SExp.to(2)])
    got_mod, got_args = program.uncurry(outer)
    assert program.tree_hash(got_mod) == program.tree_hash(inner)
    assert [a.as_atom() for a in got_args] == [b"\x02"]


@pytest.mark.parametrize("not_curried", [
    SExp.to(b"\x01"),
    SExp.to([b"\x02", (b"\x01", b"\x05")]),                          # no environment
    SExp.to([b"\x02", (b"\x01", b"\x05"), b"\x02"]),                 # environment ends in 2, not 1
    SExp.to([b"\x02", (b"\x01", b"\x05"), b"\x01", b"\x01"]),         # trailing item
    SExp.to([b"\x02", (b"\x01", b"\x05"), [b"\x04", b"\x07", b"\x01"]]),  # argument not quoted
    SExp.to([b"\x03", (b"\x01", b"\x05"), b"\x01"]),                 # not an apply
])
def test_uncurry_refuses_anything_else(not_curried):
    assert program.uncurry(not_curried) is None


def test_from_bytes_refuses_trailing_bytes():
    blob = program.to_bytes(SExp.to([1, 2]))
    assert program.tree_hash(program.from_bytes(blob)) == program.tree_hash(SExp.to([1, 2]))
    with pytest.raises(ValueError):
        program.from_bytes(blob + b"\x80")


def test_layer_constants_are_32_bytes():
    assert len(CAT_V2) == 32
