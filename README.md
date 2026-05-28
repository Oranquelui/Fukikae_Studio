# FukiKae Studio

FukiKae Studio is a local-first CLI MVP for turning a local video file into a Japanese-dubbed MP4.

Current MVP status:

- Local Python CLI with deterministic, fixture-testable stages.
- Implemented local stages: `init`, `inspect`, `extract-audio`, `stt`, `make-script`, `tts`, `assemble`, `validate`, fixture-backed `run`, and local Web UI alpha `studio`.
- `assemble` writes timeline, mix-plan, subtitle, assembly manifest, and final MP4 mux command-plan artifacts.
- `run --execute-ffmpeg` can render local fixture-backed MP4 outputs.
- `studio` starts a localhost form for fixture or live xAI execution, local path selection, voice selection, subtitle output selection, stage status, validation report, and final MP4 path display.
- Default share output is burned captions at `output/dubbed.ja.burned.mp4`; soft subtitles remain available at `output/dubbed.ja.mp4`.
- Default tests and CLI fixture paths do not perform live xAI API calls.
- AI boundary policy: xAI only.
- Primary input is a local video file.

## Development

Use the project-local virtual environment:

```bash
.venv/bin/python -m pytest tests -q
PYTHONPATH=src .venv/bin/python -m fukikae_studio --help
```

## Local fixture smoke test

The default local smoke path uses sanitized fixtures and does not call live xAI APIs. For the fastest repeatable check, run the solo beta smoke script; by default it writes to a temporary directory outside the repository:

```bash
PYTHONPATH=src .venv/bin/python scripts/local_beta_smoke.py
```

To keep artifacts for inspection:

```bash
PYTHONPATH=src .venv/bin/python scripts/local_beta_smoke.py --workdir /tmp/fukikae-local-smoke --keep
```

## Internal beta preflight

Before a local internal beta session, run the preflight check. It runs tests, CLI help, localhost Web health, and a fixture-backed MP4 smoke render while keeping generated artifacts outside the repository:

```bash
PYTHONPATH=src .venv/bin/python scripts/internal_beta_check.py
```

Expected result:

- `Internal beta preflight: GO`
- retained smoke artifacts under `/tmp/fukikae-internal-beta-preflight/smoke`
- final MP4 at `/tmp/fukikae-internal-beta-preflight/smoke/project/output/dubbed.ja.mp4`

## Live xAI local run

For an actual local dubbing run, use `run-live`. Pass the local env file directly; do not `source` it in the shell:

```bash
PYTHONPATH=src .venv/bin/python -m fukikae_studio run-live \
  --env-file ./env.local. \
  --video /path/to/source.mp4 \
  --project /tmp/fukikae-live-run \
  --execute-ffmpeg \
  --overwrite
```

`run-live` loads xAI credentials without printing them, extracts local audio, calls xAI STT, asks Grok for the Japanese dubbing script, synthesizes Japanese TTS, and writes `output/dubbed.ja.mp4`.

Use `--subtitle-output burned`, `--subtitle-output soft`, or `--subtitle-output both`
to choose the final render. The default is `both`, with the burned-caption MP4
treated as the share-ready output.

Manual equivalent:

```bash
mkdir -p work/local-smoke
ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i testsrc=size=320x180:rate=25 \
  -f lavfi -i sine=frequency=440:sample_rate=48000 \
  -t 5 -c:v libx264 -pix_fmt yuv420p -c:a aac \
  work/local-smoke/source.mp4
ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i sine=frequency=880:duration=0.8:sample_rate=16000 \
  -ac 1 -c:a pcm_s16le \
  work/local-smoke/fixture.wav
PYTHONPATH=src .venv/bin/python -m fukikae_studio run \
  --video work/local-smoke/source.mp4 \
  --project work/local-smoke/project \
  --fixture-stt-response tests/fixtures/sample_stt_response.json \
  --fixture-dubbing-response tests/fixtures/sample_dubbing_response.json \
  --fixture-audio work/local-smoke/fixture.wav \
  --execute-ffmpeg
```

Expected result:

- `validation/local_test_report.json` has `status: complete`.
- `output/dubbed.ja.burned.mp4` exists in the selected project directory when using the default subtitle output.
- The burned MP4 contains generated Japanese narration audio and visible Japanese captions. The soft MP4 contains a Japanese subtitle track.

## Local Web UI alpha

The local Web UI alpha is a thin browser form over the same CLI pipeline. It binds to loopback by default and prints a generated access URL in the terminal:

```bash
PYTHONPATH=src .venv/bin/python -m fukikae_studio studio
```

Default bind:

```text
127.0.0.1:8765
```

The form supports:

- local source video path,
- local project directory,
- sanitized STT fixture path,
- sanitized dubbing fixture path,
- local fixture audio path,
- fixture or live xAI run mode,
- local-only xAI API key entry for live mode,
- Sakura/Ren/Eve voice selection,
- burned/soft/both subtitle output selection,
- optional local FFmpeg final render,
- stage status display,
- `validation/local_test_report.json` display,
- final MP4 display.

This alpha does not upload media, create hosted storage, or start a cloud queue.
The xAI API key field is only used for the local live run and is not echoed back
into the page.

## Public docs

- [Solo Local Beta Test](docs/SOLO_BETA_TEST.md)
- [CLI MVP](docs/CLI_MVP.md)
- [App Shape Research](docs/APP_SHAPE_RESEARCH.md)
- [Provider Policy](docs/PROVIDER_POLICY.md)
- [xAI Endpoint Notes](docs/XAI_ENDPOINT_NOTES.md)
- [Public Sample Runbook](docs/PUBLIC_SAMPLE_RUNBOOK.md)
