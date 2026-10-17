"""Read a coin from a Chia full node through the `chia rpc` command.

A spent coin gives its revealed puzzle. An unspent one has shown only its
puzzle hash, so that is all there is to compare.
"""
from __future__ import annotations

import json
import subprocess

from clvm import SExp

from . import program


class FetchError(Exception):
    pass


def _rpc(chia: str, command: str, args: dict) -> dict:
    try:
        done = subprocess.run([chia, "rpc", "full_node", command, json.dumps(args)],
                              capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        raise FetchError(f"no `{chia}` command; install chia-blockchain or pass --chia") from None
    if done.returncode != 0:
        raise FetchError(f"chia rpc {command} failed: {(done.stderr or done.stdout).strip()}")
    reply = json.loads(done.stdout)
    if not reply.get("success"):
        raise FetchError(f"chia rpc {command}: {reply.get('error', reply)}")
    return reply


def coin(coin_id: str, chia: str = "chia") -> tuple[SExp | None, bytes]:
    """(revealed puzzle or None if unspent, puzzle hash)."""
    coin_id = "0x" + coin_id.removeprefix("0x")
    record = _rpc(chia, "get_coin_record_by_name", {"name": coin_id})["coin_record"]
    puzzle_hash = bytes.fromhex(record["coin"]["puzzle_hash"].removeprefix("0x"))
    if not record.get("spent_block_index"):
        return None, puzzle_hash
    spend = _rpc(chia, "get_puzzle_and_solution",
                 {"coin_id": coin_id, "height": record["spent_block_index"]})["coin_solution"]
    puzzle = program.from_hex(spend["puzzle_reveal"])
    if program.tree_hash(puzzle) != puzzle_hash:
        raise FetchError("the node's puzzle reveal does not hash to the coin's puzzle hash")
    return puzzle, puzzle_hash
