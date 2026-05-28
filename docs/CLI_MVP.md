# FukiKae Studio CLI MVP

This document tracks the local-first CLI surface for the MVP.

## Current help command

```bash
PYTHONPATH=src python -m fukikae_studio --help
```

The CLI exposes deterministic local stages and fixture-backed paths. Default tests and fixture-backed CLI paths do not call live xAI APIs.

## Implemented local stages

```text
local video file
→ init local project
→ inspect command plan
→ extract-audio command plan
→ stt fixture normalization
→ make-script fixture parsing
→ tts fixture audio manifest
→ assemble artifacts and final MP4 mux command plan
→ optional local FFmpeg render
→ validate local artifacts
→ localhost Web UI alpha for running the fixture-backed path
```

`fukikae run ... --execute-ffmpeg` can create a local fixture-backed MP4 at:

```text
output/dubbed.ja.mp4
```

## Project artifact layout

`fukikae init --video input.mp4 --project ./work/demo` writes:

- `project.json`
- `input/source.mp4`

`fukikae assemble ./work/demo` reads:

- `tts/xai_tts_manifest.json`
- `script/japanese_dubbing_segments.json`

It writes:

- `assembly/narration_timeline.json`
- `assembly/mix_plan.json`
- `assembly/japanese_subtitles.srt`
- `assembly/japanese_subtitles.vtt`
- `assembly/subtitle_manifest.json`
- `assembly/final_mux_plan.json`
- `assembly/assembly_manifest.json`

`fukikae validate ./work/demo` writes:

- `validation/local_test_report.json`

The final mux plan points to deterministic output path `output/dubbed.ja.mp4` and uses explicit non-overwrite FFmpeg flags by default.

## Target primary path

```text
local video file
→ inspect
→ extract-audio
→ stt
→ make-script
→ tts
→ assemble
→ validate
→ dubbed MP4
```

## CLI commands

```bash
fukikae init --video input.mp4 --target-lang ja --source-lang auto --project ./work/demo
fukikae inspect ./work/demo
fukikae extract-audio ./work/demo
fukikae stt ./work/demo --fixture-response tests/fixtures/sample_stt_response.json
fukikae make-script ./work/demo --fixture-response tests/fixtures/sample_dubbing_response.json
fukikae tts ./work/demo --fixture-audio ./local-fixture.wav --voice eve
fukikae assemble ./work/demo
fukikae validate ./work/demo
fukikae studio
fukikae studio --host 127.0.0.1 --port 8765
fukikae run \
  --video input.mp4 \
  --project ./work/demo \
  --target-lang ja \
  --source-lang auto \
  --fixture-stt-response tests/fixtures/sample_stt_response.json \
  --fixture-dubbing-response tests/fixtures/sample_dubbing_response.json \
  --fixture-audio ./local-fixture.wav \
  --execute-ffmpeg
```

All implementation must remain fixture/mock-testable by default. Live xAI calls are not part of the default validation path.

## Local fixture smoke test

This smoke test creates synthetic local media, runs the fixture-backed pipeline, renders the MP4 with local FFmpeg, and validates the output.

```bash
rm -rf work/local-smoke
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

Expected output:

```text
work/local-smoke/project/validation/local_test_report.json
```

Expected validation report fields:

```json
{
  "status": "complete",
  "missing_required_artifacts": [],
  "final_output": "output/dubbed.ja.mp4",
  "final_output_exists": true
}
```

Optional stream verification:

```bash
ffprobe -v error -print_format json -show_streams work/local-smoke/project/output/dubbed.ja.mp4
```

Expected streams:

- video stream copied from the local source MP4,
- AAC Japanese narration audio stream,
- `mov_text` subtitle stream with `jpn` language metadata.

## Local Web UI alpha

`fukikae studio` starts a loopback-only browser form over the same fixture-backed pipeline:

```bash
PYTHONPATH=src .venv/bin/python -m fukikae_studio studio
```

The command prints a generated access URL in the terminal. The browser form accepts local paths for the source video, project directory, sanitized fixtures, and fixture audio. After running, it displays stage statuses, the validation report path, and the final MP4 path.

Default local Web UI behavior remains fixture-backed. It does not upload media, create hosted storage, start a cloud queue, or perform live provider calls.

## App shape direction

The recommended product shape is:

```text
CLI engine now
→ localhost Web app alpha now
→ packaged local app / Mac wrapper after demand validation
→ optional hosted cloud mode later
```

See [App Shape Research](APP_SHAPE_RESEARCH.md) for the CLI, local Web app, hosted SaaS, and Mac desktop comparison.
