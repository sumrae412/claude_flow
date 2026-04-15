import json
import pathlib


def test_curmudgeon_registered():
    r = json.loads(pathlib.Path("reviewer-registry.json").read_text())
    ids = {x["id"] for x in r["reviewers"]}
    assert "curmudgeon-review" in ids, "curmudgeon entry missing"
    curm = next(x for x in r["reviewers"] if x["id"] == "curmudgeon-review")
    assert curm["tier"] == "always"
    assert curm["cascade_tier"] == 2
    assert curm.get("runner") == "codex-cli"
