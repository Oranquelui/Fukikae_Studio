#!/usr/bin/env python3
"""Run the local-only preflight checks for an internal beta session.

This script is intentionally fixture-backed. It does not read `.env`, open a
browser, call live providers, or write generated artifacts inside the repo by
default.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
from http.server import HTTPServer
from pathlib import Path
from subprocess import run
from typing import Mapping, NamedTuple, Optional, Sequence
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fukikae_studio.web.studio import make_studio_handler  # noqa: E402


class PreflightCommand(NamedTuple):
    name: str
    argv: list[str]
    env: Mapping[str, str]


class CheckResult(NamedTuple):
    name: str
    passed: bool
    returncode: int


def default_workdir() -> Path:
    return Path("/tmp/fukikae-internal-beta-preflight")


def prepare_workdir(path: Path) -> Path:
    return path.expanduser()


def build_preflight_commands(
    repo_root: Path,
    python_executable: Path,
    workdir: Path,
) -> list[PreflightCommand]:
    py = str(python_executable)
    src_env = {"PYTHONPATH": str(repo_root / "src")}
    return [
        PreflightCommand("pytest", [py, "-m", "pytest", "tests", "-q"], {}),
        PreflightCommand("cli-help", [py, "-m", "fukikae_studio", "--help"], src_env),
        PreflightCommand("studio-help", [py, "-m", "fukikae_studio", "studio", "--help"], src_env),
        PreflightCommand(
            "local-beta-smoke",
            [
                py,
                "scripts/local_beta_smoke.py",
                "--workdir",
                str(workdir / "smoke"),
                "--keep",
            ],
            {},
        ),
    ]


def run_command_check(command: PreflightCommand, repo_root: Path) -> CheckResult:
    print(f"\n== {command.name} ==")
    env = os.environ.copy()
    env.update(command.env)
    result = run(command.argv, cwd=repo_root, env=env)
    return CheckResult(command.name, result.returncode == 0, result.returncode)


def run_studio_health_check() -> CheckResult:
    print("\n== studio-health ==")
    server = HTTPServer(("127.0.0.1", 0), make_studio_handler({}, "internal-beta-check"))
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
            passed = response.status == 200 and b"local_web_alpha" in response.read()
        return CheckResult("studio-health", passed, 0 if passed else 1)
    except Exception as exc:
        print(f"studio-health failed: {exc}")
        return CheckResult("studio-health", False, 1)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def preflight_status(results: Sequence[CheckResult]) -> str:
    return "GO" if all(result.passed for result in results) else "NO-GO"


def format_summary(results: Sequence[CheckResult], workdir: Path) -> str:
    status = preflight_status(results)
    smoke_project = workdir / "smoke" / "project"
    lines = [
        "",
        f"Internal beta preflight: {status}",
        "",
        "Checks:",
    ]
    for result in results:
        label = "PASS" if result.passed else "FAIL"
        lines.append(f"- [{label}] {result.name} (exit {result.returncode})")
    lines.extend(
        [
            "",
            f"Smoke workdir: {workdir / 'smoke'}",
            f"Validation report: {smoke_project / 'validation' / 'local_test_report.json'}",
            f"Final MP4: {smoke_project / 'output' / 'dubbed.ja.mp4'}",
        ]
    )
    if status == "GO":
        lines.append("GO: local internal beta checks passed.")
    else:
        lines.append("NO-GO: fix failing checks before tonight's internal beta.")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run local-only internal beta preflight checks: tests, CLI help, "
            "localhost health, and fixture-backed MP4 smoke output."
        )
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=default_workdir(),
        help="Directory for generated beta artifacts. Defaults to a temp directory outside the repo.",
    )
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable to use for subprocess checks. Defaults to the current interpreter.",
    )
    parser.add_argument("--skip-pytest", action="store_true", help="Skip the pytest preflight check.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    workdir = prepare_workdir(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    commands = build_preflight_commands(REPO_ROOT, args.python, workdir)
    if args.skip_pytest:
        commands = [command for command in commands if command.name != "pytest"]

    results: list[CheckResult] = []
    for command in commands:
        if command.name == "local-beta-smoke":
            results.append(run_studio_health_check())
        results.append(run_command_check(command, REPO_ROOT))

    print(format_summary(results, workdir))
    return 0 if preflight_status(results) == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
