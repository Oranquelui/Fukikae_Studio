import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT = REPO_ROOT / "scripts" / "internal_beta_check.py"


def load_check_module():
    spec = importlib.util.spec_from_file_location("internal_beta_check", CHECK_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_internal_beta_check_builds_local_only_preflight_commands():
    check = load_check_module()

    commands = check.build_preflight_commands(
        repo_root=Path("/repo"),
        python_executable=Path("/repo/.venv/bin/python"),
        workdir=Path("/tmp/fukikae-internal-beta"),
    )

    assert [command.name for command in commands] == [
        "pytest",
        "cli-help",
        "studio-help",
        "local-beta-smoke",
    ]
    assert commands[0].argv == ["/repo/.venv/bin/python", "-m", "pytest", "tests", "-q"]
    assert commands[1].env["PYTHONPATH"] == "/repo/src"
    assert commands[2].env["PYTHONPATH"] == "/repo/src"
    smoke = commands[3]
    assert smoke.argv == [
        "/repo/.venv/bin/python",
        "scripts/local_beta_smoke.py",
        "--workdir",
        "/tmp/fukikae-internal-beta/smoke",
        "--keep",
    ]
    flat_tokens = [token for command in commands for token in command.argv]
    assert not any(token.startswith("http://") or token.startswith("https://") for token in flat_tokens)
    assert ".env" not in " ".join(flat_tokens)


def test_internal_beta_check_default_workdir_is_predictable_tmp_path():
    check = load_check_module()

    assert check.default_workdir() == Path("/tmp/fukikae-internal-beta-preflight")


def test_internal_beta_check_preserves_absolute_tmp_workdir_for_readable_output():
    check = load_check_module()

    assert check.prepare_workdir(Path("/tmp/fukikae-internal-beta-preflight")) == Path(
        "/tmp/fukikae-internal-beta-preflight"
    )


def test_internal_beta_check_reports_go_only_when_all_checks_pass():
    check = load_check_module()

    passed = [
        check.CheckResult("pytest", True, 0),
        check.CheckResult("studio-health", True, 0),
    ]
    failed = passed + [check.CheckResult("local-beta-smoke", False, 1)]

    assert check.preflight_status(passed) == "GO"
    assert check.preflight_status(failed) == "NO-GO"


def test_internal_beta_check_formats_summary_with_artifact_paths():
    check = load_check_module()

    summary = check.format_summary(
        [
            check.CheckResult("pytest", True, 0),
            check.CheckResult("local-beta-smoke", False, 1),
        ],
        workdir=Path("/tmp/fukikae-internal-beta"),
    )

    assert "NO-GO" in summary
    assert "[PASS] pytest" in summary
    assert "[FAIL] local-beta-smoke" in summary
    assert "/tmp/fukikae-internal-beta/smoke/project/output/dubbed.ja.mp4" in summary
    assert "/tmp/fukikae-internal-beta/smoke/project/validation/local_test_report.json" in summary
