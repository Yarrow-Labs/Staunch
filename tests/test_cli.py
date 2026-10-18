"""The command line, including --coin against a stand-in for `chia rpc`."""
import json
import stat
import sys

from conftest import CHIA, MAINNET, TIMES
from staunch import program
from staunch.cli import main


def fixture(name):
    return json.loads((MAINNET / f"{name}.json").read_text())


def fake_chia(tmp_path, fx, spent=True):
    """A `chia` command that answers the two RPCs from a mainnet fixture."""
    coin = fx["coin"]
    record = {"coin": coin, "spent_block_index": fx["height"] if spent else 0}
    script = tmp_path / "chia"
    script.write_text(f"""#!{sys.executable}
import json, sys
cmd = sys.argv[3]
if cmd == "get_coin_record_by_name":
    print(json.dumps({{"success": True, "coin_record": {json.dumps(record)}}}))
elif cmd == "get_puzzle_and_solution":
    print(json.dumps({{"success": True, "coin_solution": {{"puzzle_reveal": {json.dumps(fx["puzzle_reveal"])}}}}}))
else:
    sys.exit(1)
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_build_prints_the_mod_hash(capsys):
    assert main(["build", str(CHIA / "cat_v2.recipe.json"), "-n", str(TIMES)]) == 0
    assert capsys.readouterr().out.startswith("37bef360ee858133b69d595a906dc45d01af50379dad515eb9518abb7c1d2a7a")


def test_verify_a_spent_coin_through_the_node(tmp_path, capsys):
    chia = fake_chia(tmp_path, fixture("cat_std"))
    code = main(["verify", str(CHIA / "cat_v2.recipe.json"), "--coin", "ab" * 32, "--chia", chia,
                 "-n", str(TIMES), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["result"] == "code-match" and out["found_at"] == "the whole puzzle"


def test_an_unspent_coin_falls_back_to_its_hash(tmp_path, capsys):
    chia = fake_chia(tmp_path, fixture("std"), spent=False)
    code = main(["verify", str(CHIA / "standard_wallet.recipe.json"), "--coin", "ab" * 32, "--chia", chia,
                 "-n", str(TIMES)])
    out = capsys.readouterr().out
    assert code == 1 and "unspent" in out


def test_control_a_node_whose_reveal_does_not_hash_to_the_coin(tmp_path, capsys):
    fx = fixture("cat_std")
    fx["coin"]["puzzle_hash"] = "0x" + program.tree_hash(program.from_hex(fixture("std")["puzzle_reveal"])).hex()
    chia = fake_chia(tmp_path, fx)
    assert main(["verify", str(CHIA / "cat_v2.recipe.json"), "--coin", "ab" * 32, "--chia", chia]) == 2
    assert "does not hash" in capsys.readouterr().err


def test_no_match_exits_1(capsys):
    reveal = json.loads((MAINNET / "std.json").read_text())["puzzle_reveal"]
    assert main(["verify", str(CHIA / "cat_v2.recipe.json"), "--puzzle", reveal, "-n", str(TIMES)]) == 1
    assert capsys.readouterr().out.startswith("NO MATCH")


def test_a_refusal_exits_2(tmp_path, capsys):
    bad = tmp_path / "r.json"
    bad.write_text(json.dumps({"staunch": 1, "source": "missing.clsp", "compiler": "clvm_tools_rs 0.4.0"}))
    assert main(["verify", str(bad), "--hash", "00" * 32]) == 2
    assert "not found" in capsys.readouterr().err


def test_a_puzzle_hash_of_the_wrong_length_is_refused(capsys):
    assert main(["verify", str(CHIA / "cat_v2.recipe.json"), "--hash", "ab" * 31]) == 2
    assert "32 bytes" in capsys.readouterr().err


def test_the_human_report_reads_clearly(capsys):
    reveal = json.loads((MAINNET / "cat_std.json").read_text())["puzzle_reveal"]
    assert main(["verify", str(CHIA / "cat_v2.recipe.json"), "--puzzle", reveal, "-n", str(TIMES)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("MATCH (code only): Chia CAT v2")
    assert "Code found in: the whole puzzle" in out
    assert "Build: 4 compiles, one program (stable)" in out
