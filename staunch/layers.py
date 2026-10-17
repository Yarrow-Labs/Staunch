"""Chia's standard wrapper layers, recognised by mod hash and peeled off.

Only layers listed here are peeled. Anything else is reported as the
project's own puzzle and never guessed at.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from clvm import SExp

from . import program

# Tree hashes of Chia's published puzzles (Chia-Network/chia_puzzles,
# Apache-2.0). tests/test_layers.py rebuilds each one from source and checks
# these values.
CAT_V2 = bytes.fromhex("37bef360ee858133b69d595a906dc45d01af50379dad515eb9518abb7c1d2a7a")
SINGLETON_V1_1 = bytes.fromhex("7faa3253bfddd1e0decb0906b2dc6247bbc4cf608f58345d173adb63e8b47c9f")
STANDARD_WALLET = bytes.fromhex("e9aaa49f45bad5c889b86ee3341550c155cfdd10c3a6757de618d20612fffd52")


@dataclass
class Layer:
    name: str              # "CAT2", "singleton v1_1", "standard wallet" or "unknown"
    puzzle: SExp
    facts: dict = field(default_factory=dict)

    @property
    def hash(self) -> bytes:
        return program.tree_hash(self.puzzle)


def _atom(sexp: SExp) -> str:
    return sexp.as_atom().hex() if not sexp.listp() else program.tree_hash(sexp).hex()


def peel(puzzle: SExp) -> list[Layer]:
    """Every layer, outermost first. The last is the innermost reached."""
    layers = []
    while True:
        parts = program.uncurry(puzzle)
        mod_hash = program.tree_hash(parts[0]) if parts else None
        args = parts[1] if parts else []
        if mod_hash == CAT_V2 and len(args) == 3:
            layers.append(Layer("CAT2", puzzle, {"asset id (TAIL hash)": _atom(args[1])}))
            puzzle = args[2]
        elif mod_hash == SINGLETON_V1_1 and len(args) == 2:
            facts = {}
            struct = args[0]
            if struct.listp() and struct.rest().listp():
                facts["launcher id"] = _atom(struct.rest().first())
            layers.append(Layer("singleton v1_1", puzzle, facts))
            puzzle = args[1]
        elif mod_hash == STANDARD_WALLET and len(args) == 1:
            layers.append(Layer("standard wallet", puzzle, {"synthetic public key": _atom(args[0])}))
            return layers
        else:
            layers.append(Layer("unknown", puzzle))
            return layers
