# FukiKae Studio Solo Local Beta Test

This document is the runbook for a one-person, 2-3 run beta test on the developer's own machine.

This is not a public beta. It is a local-first solo beta to validate the current product shape, local Web UI, fixture-backed pipeline, and output artifact flow before any external distribution.

## Scope

In scope:

- Run the local Python CLI and localhost Web UI alpha.
- Use synthetic or local test video files.
- Use sanitized fixtures for STT, dubbing script, and TTS audio.
- Render a local fixture-backed MP4 with FFmpeg.
- Confirm `validation/local_test_report.json` and `output/dubbed.ja.mp4`.
- Record UX friction and product questions.

Out of scope for this solo beta:

- Public beta distribution.
- Hosted SaaS mode.
- Login, payment, team sharing, queues, or cloud storage.
- Live xAI/Grok API calls.
- Reading or storing real API keys.
- Uploading local media.
- Packaging an installer.

## Prerequisites

Run from the repository root:

```bash
cd /Users/louistoyozaki/Documents/GitHub/FukiKae_Studio
```

Expected local tools:

```bash
.venv/bin/python --version
ffmpeg -version
ffprobe -version
```

Baseline checks:

```bash
.venv/bin/python -m pytest tests -q
PYTHONPATH=src .venv/bin/python -m fukikae_studio --help
PYTHONPATH=src .venv/bin/python -m fukikae_studio studio --help
```

Default beta mode is fixture-backed. It does not require `XAI_API_KEY` and must not perform live provider calls.

## Internal beta preflight

Run this once before the internal beta session:

```bash
PYTHONPATH=src .venv/bin/python scripts/internal_beta_check.py
```

Expected result:

- `Internal beta preflight: GO`
- `pytest`, `cli-help`, `studio-help`, `studio-health`, and `local-beta-smoke` all pass
- retained smoke artifacts are available under `/tmp/fukikae-internal-beta-preflight/smoke`
- final MP4 is available at `/tmp/fukikae-internal-beta-preflight/smoke/project/output/dubbed.ja.mp4`
- validation report is available at `/tmp/fukikae-internal-beta-preflight/smoke/project/validation/local_test_report.json`

If this reports `NO-GO`, fix the failing check before starting the beta run.

## Fast smoke command

Use the local beta smoke script when you want a fresh synthetic run without writing artifacts into the repository:

```bash
PYTHONPATH=src .venv/bin/python scripts/local_beta_smoke.py
```

Expected result:

- The script creates a temporary work directory under `/tmp`.
- `validation/local_test_report.json` has `status: complete`.
- `output/dubbed.ja.mp4` exists.
- `ffprobe` reports video, audio, and subtitle streams.

To keep artifacts for manual inspection:

```bash
PYTHONPATH=src .venv/bin/python scripts/local_beta_smoke.py --keep
```

To choose a specific output area:

```bash
PYTHONPATH=src .venv/bin/python scripts/local_beta_smoke.py --workdir /tmp/fukikae-solo-beta-1 --keep
```

## Test run 1: Control fixture-backed pipeline

Goal: prove the current deterministic local pipeline completes once.

1. Run:

   ```bash
   PYTHONPATH=src .venv/bin/python scripts/local_beta_smoke.py --workdir /tmp/fukikae-solo-beta-control --keep
   ```

2. Confirm the script prints:

   - `Validation status: complete`
   - `Final output exists: true`
   - `Stream summary:` with video, audio, and subtitle rows

3. Open or inspect:

   ```text
   /tmp/fukikae-solo-beta-control/project/validation/local_test_report.json
   /tmp/fukikae-solo-beta-control/project/output/dubbed.ja.mp4
   ```

Pass condition:

- The validation report status is `complete`.
- The MP4 exists and has video/audio/subtitle streams.

## Test run 2: Fresh project repeatability

Goal: make sure a second run does not depend on previous artifacts.

1. Run with a different directory:

   ```bash
   PYTHONPATH=src .venv/bin/python scripts/local_beta_smoke.py --workdir /tmp/fukikae-solo-beta-repeat --keep
   ```

2. Confirm the output path is different from Test run 1.
3. Confirm the same pass conditions.

Pass condition:

- A fresh project directory produces a fresh final MP4 without relying on the first run.

## Test run 3: Local Web UI UX pass

Goal: evaluate whether the local browser UI is understandable enough for solo use.

1. Start the local Web UI:

   ```bash
   PYTHONPATH=src .venv/bin/python -m fukikae_studio studio --host 127.0.0.1 --port 8765 --open-browser
   ```

2. In the browser, confirm the page clearly says:

   - local-only
   - fixture-backed
   - no upload
   - no live provider call
   - final output is `output/dubbed.ja.mp4`
   - validation report is `validation/local_test_report.json`

3. Use paths from one of the smoke runs, or create `work/local-smoke` fixtures using the README smoke commands.
4. Check `Execute local FFmpeg final render` if you want the MP4 created.
5. Click `Run local fixture-backed pipeline`.
6. Confirm the result panel shows stage statuses, validation report path, and output MP4 path.

Pass condition:

- The UI makes it clear what to input, what mode is running, and where to find the output.

## Notes to collect while testing

Record short notes after each run:

```text
Run number:
Command/UI path used:
Pass/fail:
Error message, if any:
Was the source video path clear?
Was the project directory clear?
Was fixture-backed vs live API clear?
Was the final MP4 location clear?
Was overwrite behavior clear?
Where should Grok API key settings live later?
Would this be useful as a local app if live API mode is added?
Next fix:
```

## GO / NO-GO for tomorrow's solo beta

GO if all are true:

- `pytest` passes.
- `scripts/local_beta_smoke.py` completes.
- The local Web UI starts on `127.0.0.1`.
- `/health` returns `{"status": "ok", "mode": "local_web_alpha"}`.
- The output MP4 and validation report paths are obvious.
- No live API key is needed.
- No local media upload is performed.

NO-GO if any are true:

- The Web UI does not start.
- The smoke script fails before validation.
- The final MP4 location is unclear.
- The UI makes fixture-backed mode look like live API mode.
- A real API key is required for the default beta path.
- Error messages expose secrets or suggest opening `.env`.

## Future live mode policy

Future live xAI/Grok mode should be BYOK:

- The user enters their own xAI/Grok API key.
- The key is stored locally, preferably via OS secret storage such as macOS Keychain.
- If OS secret storage is unavailable, use encrypted local storage with a clear user-controlled boundary.
- The key must not be stored in a hosted backend or cloud database.
- The key must not be printed in logs, artifacts, crash reports, analytics, or validation output.

This policy is intentionally separate from the current fixture-backed solo beta.
