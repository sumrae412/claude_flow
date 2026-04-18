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
