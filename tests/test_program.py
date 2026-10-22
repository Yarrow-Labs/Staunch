import pytest
from clvm import SExp
from clvm.operators import OPERATOR_LOOKUP
from clvm.run_program import run_program

from staunch import program


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


def test_uncurry_steps_reads_every_step():
    code = SExp.to(b"\x07")
    inner = program.curry(code, [SExp.to(1)])
    outer = program.curry(inner, [SExp.to(2), SExp.to(3)])
    got = [(program.tree_hash(c), [v.as_atom() for v in vs]) for c, vs in program.uncurry_steps(outer)]
    assert got == [(program.tree_hash(outer), []),
                   (program.tree_hash(inner), [b"\x02", b"\x03"]),
                   (program.tree_hash(code), [b"\x01", b"\x02", b"\x03"])]


def test_code_curried_in_steps_runs_as_if_curried_once():
    """Why `uncurry_steps` lists values in that order: the code receives them so."""
    lists_its_first_four_arguments = SExp.to([4, 2, [4, 5, [4, 11, [4, 23, 0]]]])
    two_steps = program.curry(program.curry(lists_its_first_four_arguments, [SExp.to(1)]), [SExp.to(2)])
    one_step = program.curry(lists_its_first_four_arguments, [SExp.to(1), SExp.to(2)])
    solution = SExp.to([3, 4])
    got = [run_program(p, solution, OPERATOR_LOOKUP)[1] for p in (two_steps, one_step)]
    assert got[0] == got[1] == SExp.to([1, 2, 3, 4])


@pytest.mark.parametrize("not_curried", [
    SExp.to(b"\x01"),
    SExp.to([b"\x02", (b"\x01", b"\x05")]),                          # no environment
    SExp.to([b"\x02", (b"\x01", b"\x05"), b"\x02"]),                 # environment ends in 2, not 1
    SExp.to([b"\x02", (b"\x01", b"\x05"), b"\x01", b"\x01"]),         # trailing item
    SExp.to([b"\x02", (b"\x01", b"\x05"), [b"\x04", b"\x07", b"\x01"]]),  # argument not quoted
    SExp.to([b"\x03", (b"\x01", b"\x05"), b"\x01"]),                 # not an apply
    SExp.to((b"\x02", ((b"\x01", b"\x05"), (b"\x01", b"\x09")))),     # junk where the list should end
    SExp.to([b"\x02", (b"\x01", b"\x05"),
             (b"\x04", ((b"\x01", b"\x07"), (b"\x01", b"\x09")))]),  # a link ends in junk
    SExp.to([b"\x02", (b"\x01", b"\x05"),
             [b"\x04", (b"\x01", b"\x07"), b"\x01", b"\x01"]]),      # a link has four items
])
def test_uncurry_refuses_anything_else(not_curried):
    assert program.uncurry(not_curried) is None


def test_from_bytes_refuses_trailing_bytes():
    blob = program.to_bytes(SExp.to([1, 2]))
    assert program.tree_hash(program.from_bytes(blob)) == program.tree_hash(SExp.to([1, 2]))
    with pytest.raises(ValueError):
        program.from_bytes(blob + b"\x80")


def test_a_puzzle_over_the_limit_is_refused():
    blob = program.to_bytes(SExp.to([1, 2, 3]))
    assert program.from_bytes(blob, max_bytes=len(blob)) == program.from_bytes(blob)
    with pytest.raises(ValueError, match="the limit is"):
        program.from_bytes(blob, max_bytes=len(blob) - 1)
    with pytest.raises(ValueError, match="the limit is"):
        program.from_hex(blob.hex(), max_bytes=len(blob) - 1)


def test_no_limit_unless_one_is_given():
    assert program.from_bytes(program.to_bytes(SExp.to(list(range(1, 30000)))))   # far past the default
