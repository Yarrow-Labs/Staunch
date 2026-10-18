"""Chia's standard wrapper layers: recognised by mod hash and peeled off.

Many coins are wrapped. A token held in a wallet is a CAT2 layer around a
standard wallet puzzle; a singleton is a top layer around the project's own
puzzle. `peel` unwraps the layers listed here, outermost first, and stops at
the first puzzle it does not recognise. That puzzle is reported as "unknown",
never guessed at.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from clvm import SExp

from . import program

# Mod hashes of Chia's published puzzles (Chia-Network/chia_puzzles, Apache-2.0).
# tests/test_layers.py rebuilds each one from Chia's source and checks it.
CAT_V2 = bytes.fromhex("37bef360ee858133b69d595a906dc45d01af50379dad515eb9518abb7c1d2a7a")
SINGLETON_V1_1 = bytes.fromhex("7faa3253bfddd1e0decb0906b2dc6247bbc4cf608f58345d173adb63e8b47c9f")
STANDARD_WALLET = bytes.fromhex("e9aaa49f45bad5c889b86ee3341550c155cfdd10c3a6757de618d20612fffd52")


@dataclass(eq=False)   # layers are compared by identity, never by value
class Layer:
    name: str                 # "CAT2", "singleton v1_1", "standard wallet" or "unknown"
    puzzle: SExp              # this layer's whole puzzle, including everything inside it
    facts: dict[str, str] = field(default_factory=dict)   # shown in reports

    @property
    def hash(self) -> bytes:
        return program.tree_hash(self.puzzle)


def _hex(value: SExp) -> str:
    """An atom as hex; a pair (which a well-formed layer never has here) by its tree hash."""
    return program.tree_hash(value).hex() if value.listp() else value.as_atom().hex()


def peel(puzzle: SExp) -> list[Layer]:
    """Every layer of `puzzle`, outermost first."""
    layers = []
    while True:
        curried = program.uncurry(puzzle)
        mod_hash, values = (program.tree_hash(curried[0]), curried[1]) if curried else (None, [])

        if mod_hash == CAT_V2 and len(values) == 3:
            # curried: (CAT mod hash, TAIL hash, inner puzzle)
            layers.append(Layer("CAT2", puzzle, {"asset id (TAIL hash)": _hex(values[1])}))
            puzzle = values[2]
        elif mod_hash == SINGLETON_V1_1 and len(values) == 2:
            # curried: (singleton struct, inner puzzle); struct = (mod hash . (launcher id . launcher hash))
            struct, facts = values[0], {}
            if struct.listp() and struct.rest().listp():
                facts["launcher id"] = _hex(struct.rest().first())
            layers.append(Layer("singleton v1_1", puzzle, facts))
            puzzle = values[1]
        elif mod_hash == STANDARD_WALLET and len(values) == 1:
            # curried: (synthetic public key); the innermost layer of an ordinary wallet coin
            layers.append(Layer("standard wallet", puzzle, {"synthetic public key": _hex(values[0])}))
            return layers
        else:
            layers.append(Layer("unknown", puzzle))
            return layers
