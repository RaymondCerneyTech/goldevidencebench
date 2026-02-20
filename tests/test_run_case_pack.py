from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _run_powershell_file(script: Path, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if not powershell:
        pytest.skip("pwsh/powershell executable is required for run_case_pack integration tests")
    return subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd),
    )


def test_run_case_pack_server_adapter_skip_steps_do_not_crash_report_join(tmp_path: Path) -> None:
    repo_root = _repo_root()
    temp_repo = tmp_path / "repo"
    scripts_dir = temp_repo / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    shutil.copyfile(repo_root / "scripts" / "run_case_pack.ps1", scripts_dir / "run_case_pack.ps1")

    (scripts_dir / "run_rag_benchmark.ps1").write_text(
        """param(
    [string]$Preset = "strict",
    [string]$Adapter = "",
    [string]$OutRoot = "",
    [int]$MaxRows = 24,
    [string]$ModelPath = ""
)
New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null
$summary = @{
    means = @{
        value_acc = 1.0
        cite_f1 = 1.0
        retrieval_hit_rate = 1.0
    }
}
$summary | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $OutRoot "summary.json")
exit 0
""",
        encoding="utf-8",
    )

    (scripts_dir / "generate_case_pack_onepager.py").write_text(
        """from __future__ import annotations
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--run-dir", required=True)
args = parser.parse_args()
Path(args.run_dir).mkdir(parents=True, exist_ok=True)
Path(args.run_dir, "case_pack_onepager.md").write_text("# onepager\\n", encoding="utf-8")
""",
        encoding="utf-8",
    )

    out_root = temp_repo / "runs" / "case_pack_test"
    script = scripts_dir / "run_case_pack.ps1"
    result = _run_powershell_file(
        script,
        [
            "-Adapter",
            "goldevidencebench.adapters.llama_server_adapter:create_adapter",
            "-OutRoot",
            str(out_root),
            "-SkipOpenBook",
        ],
        cwd=temp_repo,
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    combined = f"{result.stdout}\n{result.stderr}"
    assert "Cannot bind argument to parameter 'Path' because it is an empty string" not in combined

    summary = _read_json(out_root / "case_pack_summary.json")
    report_text = (out_root / "case_pack_report.md").read_text(encoding="utf-8-sig")

    assert summary["status"] == "PASS"
    by_name = {step["name"]: step for step in summary["steps"]}
    assert by_name["regression_case"]["status"] == "SKIP"
    assert by_name["bad_actor_demo"]["status"] == "SKIP"
    assert "artifacts: skipped (adapter does not expose retrieval drift diagnostics or step disabled)" in report_text
    assert "holdout gate: skipped (adapter does not expose retrieval drift diagnostics or step disabled)" in report_text
