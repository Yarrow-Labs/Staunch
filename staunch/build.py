"""Compile a Chialisp source many times and collect every result.

Why many times: clvm_tools_rs can compile the same source to more than one
program. The cause is hash sets with a random seed per process, so each
compile runs in its own fresh process and its own scratch folder. A
verification that compiled once could report "no match" for a source that
matches one time in two.

Why `compile_clvm` and not the `run` command: they do not always agree. On
Chia's own `cat_v2.clsp`, `run` gives bytes that differ from the published
puzzle, while `compile_clvm` (what Chia's own build uses) reproduces it.
`run` also reports some failures, such as a missing include, as text on
stdout with exit code 0. `compile_clvm` raises.
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

_ONE_COMPILE = r"""
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
    pass


@dataclass(frozen=True)
class Variant:
    program: bytes   # serialized
    count: int


def compiler_version() -> str:
    return metadata.version(COMPILER)


def compile_once(source: Path, include: list[Path]) -> bytes:
    with tempfile.TemporaryDirectory(prefix="staunch-") as scratch:
        out = Path(scratch) / "out.hex"
        done = subprocess.run(
            [sys.executable, "-c", _ONE_COMPILE, str(source), str(out),
             json.dumps([str(p) for p in include])],
            capture_output=True, text=True, cwd=scratch,
            env={**os.environ, "PYTHONHASHSEED": "random"},
        )
        if done.returncode != 0:
            raise BuildError(f"compile failed for {source}: {done.stderr.strip()}")
        text = out.read_text().strip()
    try:
        return bytes.fromhex(text)
    except ValueError:
        raise BuildError(f"compiler wrote something that is not a program for {source}: {text[:200]}")


def compile_many(source: Path, include: list[Path], times: int = 16,
                 workers: int | None = None) -> list[Variant]:
    """Every distinct program from `times` compiles, most common first."""
    if times < 1:
        raise ValueError("times must be at least 1")
    workers = workers or min(8, os.cpu_count() or 2)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda _: compile_once(source, include), range(times)))
    counts = collections.Counter(results)
    return [Variant(program, n) for program, n in counts.most_common()]
