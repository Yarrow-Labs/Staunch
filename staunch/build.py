"""Compile a Chialisp source, many times, and collect every distinct result.

Two facts about the compiler shape this file:

1. **It is not always deterministic.** `clvm_tools_rs` can turn one source into
   more than one program, because it orders some of its work through hash
   tables seeded at random when the process starts. So every compile runs in a
   new process, as it would on a different machine, and Staunch keeps every
   variant it sees rather than the first.

2. **How you call it matters.** Staunch calls `compile_clvm`, the function
   Chia's own build uses. The `run` command can give different bytes: on
   Chia's own `cat_v2.clsp` it does, while `compile_clvm` reproduces the
   published puzzle exactly. `run` also reports some failures, such as a
   missing include, as text on stdout with exit code 0; `compile_clvm` raises.
"""
from __future__ import annotations

import collections
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

COMPILER = "clvm_tools_rs"

# Run in a fresh Python process for each compile; see point 1 above.
_COMPILE_ONE = r"""
import json, sys
import clvm_tools_rs
source, out, include = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
try:
    clvm_tools_rs.compile_clvm(source, out, include)
except Exception as e:
    print(f"{type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(3)
"""


class BuildError(Exception):
    """The source did not compile."""


@dataclass(frozen=True)
class Variant:
    """One distinct program the source compiled to, and how often."""
    program: bytes   # serialized CLVM
    count: int


def compiler_version() -> str:
    """The installed compiler's version, for example "0.4.0"."""
    return metadata.version(COMPILER)


def compile_once(source: Path, include: list[Path]) -> bytes:
    """Compile `source` in a fresh process and scratch folder; return the program."""
    with tempfile.TemporaryDirectory(prefix="staunch-") as scratch:
        out = Path(scratch) / "out.hex"
        done = subprocess.run(
            [sys.executable, "-c", _COMPILE_ONE, str(source), str(out), json.dumps([str(p) for p in include])],
            capture_output=True, text=True, cwd=scratch,   # the compiler writes a symbol file to its cwd
        )
        if done.returncode != 0:
            raise BuildError(f"compile failed for {source}: {done.stderr.strip()}")
        text = out.read_text().strip()
    try:
        return bytes.fromhex(text)
    except ValueError:
        raise BuildError(f"the compiler wrote something that is not a program for {source}: {text[:200]}") from None


def compile_many(source: Path, include: list[Path], times: int = 16) -> list[Variant]:
    """Compile `times` times; return each distinct program, most common first."""
    if times < 1:
        raise ValueError("compile at least once")
    with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 2)) as pool:
        programs = list(pool.map(lambda _: compile_once(source, include), range(times)))
    return [Variant(p, n) for p, n in collections.Counter(programs).most_common()]
