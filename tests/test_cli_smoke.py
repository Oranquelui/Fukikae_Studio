import json
import os
import subprocess
import sys
from pathlib import Path


def test_python_module_help_displays_cli_usage():
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src") + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [sys.executable, "-m", "fukikae_studio", "--help"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "FukiKae Studio" in result.stdout
    assert "usage:" in result.stdout.lower()
    assert "init" in result.stdout
    assert "run" in result.stdout
    assert "run-live" in result.stdout


def test_run_live_help_displays_env_file_option():
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src") + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [sys.executable, "-m", "fukikae_studio", "run-live", "--help"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--env-file" in result.stdout
    assert "--execute-ffmpeg" in result.stdout
    assert "live xAI" in result.stdout


def test_assemble_command_writes_artifacts_and_prints_manifest_path(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    project_dir = tmp_path / "demo"
    tts_dir = project_dir / "tts"
    script_dir = project_dir / "script"
    tts_dir.mkdir(parents=True)
    script_dir.mkdir(parents=True)
    (tts_dir / "xai_tts_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "language": "ja",
                "segments": [
                    {
                        "id": "seg_0001",
                        "text": "こんにちは",
                        "output_audio": "tts/segment_0001.wav",
                        "duration_ms": 1000,
                        "target_slot_start_ms": 0,
                        "target_slot_end_ms": 1200,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (script_dir / "japanese_dubbing_segments.json").write_text(
        json.dumps(
            [
                {
                    "id": "seg_0001",
                    "source_start_ms": 0,
                    "source_end_ms": 1200,
                    "target_text": "こんにちは",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-m", "fukikae_studio", "assemble", str(project_dir)],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    manifest_path = project_dir / "assembly" / "assembly_manifest.json"
    assert result.stdout.strip() == str(manifest_path)
    assert manifest_path.exists()
    final_plan = json.loads((project_dir / "assembly" / "final_mux_plan.json").read_text(encoding="utf-8"))
    assert final_plan["output"] == str(project_dir / "output" / "dubbed.ja.mp4")
