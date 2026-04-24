import json
import subprocess
import sys
from pathlib import Path

def test_run_ab_produces_three_arm_results(tmp_path):
    out = tmp_path / "results.json"
    subprocess.run(
        [sys.executable, str(Path(__file__).parent / "run_ab.py"),
         "--cases-dir", str(Path(__file__).parent / "cases"),
         "--out", str(out), "--dry-run"],
        check=True,
    )
    data = json.loads(out.read_text())
    assert set(data["arms"]) == {"sonnet_solo", "sonnet_advisor_tool", "opus_solo"}
    assert len(data["per_case"]) == 12, (
        f"expected 12 rows (4 cases x 3 arms), got {len(data['per_case'])}"
    )
    for arm in data["arms"]:
        arm_rows = [r for r in data["per_case"] if r["arm"] == arm]
        assert len(arm_rows) == 4, f"expected 4 rows for {arm}, got {len(arm_rows)}"
        assert arm in data["aggregate"], f"{arm} missing from aggregate"


def test_run_ab_trials_multiplies_rows(tmp_path):
    """`--trials 5` produces 5x the rows, each tagged with trial_index."""
    out = tmp_path / "results.json"
    subprocess.run(
        [sys.executable, str(Path(__file__).parent / "run_ab.py"),
         "--cases-dir", str(Path(__file__).parent / "cases"),
         "--out", str(out), "--dry-run", "--trials", "5"],
        check=True,
    )
    data = json.loads(out.read_text())
    assert data["trials"] == 5
    assert len(data["per_case"]) == 60, (
        f"expected 60 rows (4 cases x 3 arms x 5 trials), got {len(data['per_case'])}"
    )
    trial_indices = {r["trial_index"] for r in data["per_case"]}
    assert trial_indices == {0, 1, 2, 3, 4}


def test_run_ab_rejects_zero_trials(tmp_path):
    """--trials 0 is nonsensical; exit with non-zero and a clear message."""
    out = tmp_path / "results.json"
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "run_ab.py"),
         "--cases-dir", str(Path(__file__).parent / "cases"),
         "--out", str(out), "--dry-run", "--trials", "0"],
        capture_output=True, text=True,
    )
    assert proc.returncode != 0
    assert "trials" in proc.stderr
