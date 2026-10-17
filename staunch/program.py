"""CLVM trees: parse, hash, and take curried programs apart.

Kept small on purpose: everything Staunch concludes rests on these few
functions, so they are written to be read and checked by hand.
"""
from __future__ import annotations

import hashlib
import io

from clvm import SExp
from clvm.EvalError import EvalError
from clvm.serialize import sexp_from_stream, sexp_to_stream

OP_QUOTE = b"\x01"
OP_APPLY = b"\x02"
OP_CONS = b"\x04"


def from_bytes(blob: bytes) -> SExp:
    stream = io.BytesIO(blob)
    sexp = sexp_from_stream(stream, SExp.to)
    if stream.read(1):
        raise ValueError("trailing bytes after the program")
    return sexp


def from_hex(text: str) -> SExp:
    return from_bytes(bytes.fromhex(text.strip().removeprefix("0x")))


def to_bytes(sexp: SExp) -> bytes:
    stream = io.BytesIO()
    sexp_to_stream(sexp, stream)
    return stream.getvalue()


def atom_hash(atom: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + atom).digest()


def pair_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x02" + left + right).digest()


def tree_hash(sexp: SExp) -> bytes:
    """Chia's puzzle hash. Iterative, so a deep tree cannot exhaust the stack."""
    work, done = [sexp], []
    while work:
        node = work.pop()
        if node is None:
            right, left = done.pop(), done.pop()
            done.append(pair_hash(left, right))
        elif node.listp():
            work.extend((None, node.rest(), node.first()))
        else:
            done.append(atom_hash(node.as_atom()))
    return done[0]


def int_atom(value: int) -> bytes:
    """CLVM's shortest two's-complement spelling of an integer."""
    if value == 0:
        return b""
    size = (value.bit_length() + 8) // 8
    blob = value.to_bytes(size, "big", signed=True)
    while len(blob) > 1 and blob[0] == (0xFF if blob[1] & 0x80 else 0x00):
        blob = blob[1:]
    return blob


def _quoted(sexp: SExp) -> SExp | None:
    """X if `sexp` is (q . X), else None."""
    if sexp.listp() and not sexp.first().listp() and sexp.first().as_atom() == OP_QUOTE:
        return sexp.rest()
    return None


def uncurry(sexp: SExp) -> tuple[SExp, list[SExp]] | None:
    """(mod, args) if `sexp` is a curried program, else None.

    A curried program is (a (q . MOD) ENV) with ENV built as
    (c (q . ARG1) (c (q . ARG2) ... 1)). Only the outermost curry is taken
    off: a program curried twice comes back as (once-curried mod, args).
    """
    try:
        op, rest = sexp.first(), sexp.rest()
        if op.listp() or op.as_atom() != OP_APPLY:
            return None
        mod = _quoted(rest.first())
        env, end = rest.rest().first(), rest.rest().rest()
        if mod is None or end.listp() or end.as_atom() != b"":
            return None
        args = []
        while env.listp():
            cons, quoted_arg, tail = env.first(), env.rest().first(), env.rest().rest().first()
            if cons.listp() or cons.as_atom() != OP_CONS or env.rest().rest().rest().listp():
                return None
            arg = _quoted(quoted_arg)
            if arg is None:
                return None
            args.append(arg)
            env = tail
        if env.as_atom() != b"\x01":
            return None
        return mod, args
    except (EvalError, EOFError, ValueError, AttributeError):
        return None


def curried_hash(mod_hash: bytes, arg_hashes: list[bytes]) -> bytes:
    """Tree hash of `mod` curried with args, from hashes alone.

    Lets a recipe name a curried value by its hash, so a project can publish
    "this slot holds the puzzle with hash H" without revealing the puzzle.
    """
    q, a, c, one = (atom_hash(x) for x in (OP_QUOTE, OP_APPLY, OP_CONS, b"\x01"))
    env = one
    for arg in reversed(arg_hashes):
        env = pair_hash(c, pair_hash(pair_hash(q, arg), pair_hash(env, atom_hash(b""))))
    return pair_hash(a, pair_hash(pair_hash(q, mod_hash), pair_hash(env, atom_hash(b""))))


def curry(mod: SExp, args: list[SExp]) -> SExp:
    env = SExp.to(1)
    for arg in reversed(args):
        env = SExp.to([OP_CONS, SExp.to((OP_QUOTE, arg)), env])
    return SExp.to([OP_APPLY, SExp.to((OP_QUOTE, mod)), env])
