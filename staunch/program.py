"""CLVM values: parse them, hash them, and take curried programs apart.

Everything Staunch concludes rests on the functions in this file, so they are
kept short enough to check by hand against Chia's definitions:

- A puzzle hash is the *tree hash* of the program:
  an atom hashes as sha256(0x01 + atom), a pair as sha256(0x02 + left + right).
- *Currying* bakes values into a program. Curried, MOD with values A and B is

      (a (q . MOD) (c (q . A) (c (q . B) 1)))

  that is: "apply MOD to an environment that starts with A, then B, then the
  caller's solution".
"""
from __future__ import annotations

import hashlib
import io

from clvm import SExp
from clvm.serialize import sexp_from_stream, sexp_to_stream

# The three CLVM operators that make up a curried program.
OP_QUOTE = b"\x01"   # q
OP_APPLY = b"\x02"   # a
OP_CONS = b"\x04"    # c
NIL = b""
SOLUTION = b"\x01"   # in an environment, atom 1 stands for "the whole solution"


# --- reading and writing ------------------------------------------------------

def from_bytes(blob: bytes) -> SExp:
    """Parse a serialized CLVM value. Refuses trailing bytes."""
    stream = io.BytesIO(blob)
    sexp = sexp_from_stream(stream, SExp.to)
    if stream.read(1):
        raise ValueError("trailing bytes after the program")
    return sexp


def from_hex(text: str) -> SExp:
    """Parse a serialized CLVM value written in hex, with or without 0x."""
    return from_bytes(bytes.fromhex(text.strip().removeprefix("0x")))


def to_bytes(sexp: SExp) -> bytes:
    stream = io.BytesIO()
    sexp_to_stream(sexp, stream)
    return stream.getvalue()


def int_atom(value: int) -> bytes:
    """The atom CLVM uses for an integer: shortest big-endian two's complement."""
    if value == 0:
        return NIL
    # Bits needed for the magnitude, plus one for the sign. For a negative
    # number, ~value (= -value - 1) gives the magnitude two's complement needs.
    magnitude_bits = (value if value > 0 else ~value).bit_length()
    return value.to_bytes(magnitude_bits // 8 + 1, "big", signed=True)


# --- hashing -------------------------------------------------------------------

def atom_hash(atom: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + atom).digest()


def pair_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x02" + left + right).digest()


def tree_hash(sexp: SExp) -> bytes:
    """Chia's puzzle hash of a value.

    Walks the tree with an explicit stack rather than recursion, so a deeply
    nested program from the chain cannot crash it.
    """
    to_visit, hashes = [sexp], []
    while to_visit:
        node = to_visit.pop()
        if node is None:                       # both children of a pair are hashed
            right, left = hashes.pop(), hashes.pop()
            hashes.append(pair_hash(left, right))
        elif node.listp():
            to_visit.extend((None, node.rest(), node.first()))
        else:
            hashes.append(atom_hash(node.as_atom()))
    return hashes[0]


# --- currying ------------------------------------------------------------------

def curry(mod: SExp, values: list[SExp]) -> SExp:
    """MOD with `values` curried in, built exactly as Chia builds it."""
    env = SExp.to(SOLUTION)
    for value in reversed(values):
        env = SExp.to([OP_CONS, SExp.to((OP_QUOTE, value)), env])
    return SExp.to([OP_APPLY, SExp.to((OP_QUOTE, mod)), env])


def curried_hash(mod_hash: bytes, value_hashes: list[bytes]) -> bytes:
    """The tree hash `curry` would give, computed from hashes alone.

    This is what lets a recipe name a curried value by its hash only: the
    result is the same as hashing the full program.
    """
    q, a, c, nil = atom_hash(OP_QUOTE), atom_hash(OP_APPLY), atom_hash(OP_CONS), atom_hash(NIL)

    def three_item_list(first: bytes, second: bytes, third: bytes) -> bytes:
        return pair_hash(first, pair_hash(second, pair_hash(third, nil)))

    env = atom_hash(SOLUTION)
    for value in reversed(value_hashes):
        env = three_item_list(c, pair_hash(q, value), env)
    return three_item_list(a, pair_hash(q, mod_hash), env)


def _atom_is(sexp: SExp, atom: bytes) -> bool:
    return not sexp.listp() and sexp.as_atom() == atom


def _three_items(sexp: SExp) -> tuple[SExp, SExp, SExp] | None:
    """(x y z) if `sexp` is exactly a three-item list, else None."""
    items = []
    while sexp.listp() and len(items) < 4:
        items.append(sexp.first())
        sexp = sexp.rest()
    if len(items) == 3 and _atom_is(sexp, NIL):
        return items[0], items[1], items[2]
    return None


def _unquote(sexp: SExp) -> SExp | None:
    """X if `sexp` is (q . X), else None."""
    if sexp.listp() and _atom_is(sexp.first(), OP_QUOTE):
        return sexp.rest()
    return None


def uncurry(sexp: SExp) -> tuple[SExp, list[SExp]] | None:
    """(MOD, values) if `sexp` is exactly what `curry` builds, else None.

    Strict on purpose: anything that is not the standard shape, down to the
    last terminator, is not treated as curried. Only the outermost curry is
    removed, so a program curried twice comes back as (once-curried MOD, values);
    `uncurry_steps` removes them all.
    """
    outer = _three_items(sexp)
    if outer is None or not _atom_is(outer[0], OP_APPLY):
        return None
    mod = _unquote(outer[1])
    if mod is None:
        return None
    values, env = [], outer[2]
    while not _atom_is(env, SOLUTION):
        link = _three_items(env)
        if link is None or not _atom_is(link[0], OP_CONS):
            return None
        value = _unquote(link[1])
        if value is None:
            return None
        values.append(value)
        env = link[2]
    return mod, values


def uncurry_steps(sexp: SExp) -> list[tuple[SExp, list[SExp]]]:
    """Every way to read `sexp` as code with values curried in, outermost first.

    A program can be curried in steps: curry(curry(CODE, A), B). It runs CODE
    with A's values and then B's, exactly as curry(CODE, A + B) would, so it is
    read three ways: (sexp, []), (curry(CODE, A), B) and (CODE, A + B).
    """
    readings, values = [(sexp, [])], []
    while (curried := uncurry(sexp)) is not None:
        sexp, values = curried[0], curried[1] + values
        readings.append((sexp, values))
    return readings
