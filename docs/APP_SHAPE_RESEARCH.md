# App Shape Research

FukiKae Studio should keep the Python CLI as the local engine. The current alpha adds a localhost Web UI as a thin browser surface over the same fixture-backed pipeline.

## Recommendation

Use this staged shape:

1. v0.1: CLI engine for deterministic local testing.
2. v0.2 alpha: local Web app running on `127.0.0.1`, backed by the same Python pipeline. The first thin alpha exists as `fukikae studio`.
3. Paid beta: package the local Web app for easier installation, then consider a Mac desktop wrapper.
4. Later: optional hosted/cloud mode for teams, queues, sharing, or managed rendering.

The Web app direction is best for user experience, but the immediate implementation should remain local-first. A hosted SaaS should not become the default before privacy, upload cost, storage, queueing, and copyright-operation risks are validated.

## Comparison

| Shape | Fit | Strengths | Risks |
| --- | --- | --- | --- |
| CLI | Best current engine | Easy to test, scriptable, works with Python and FFmpeg, good for deterministic artifacts | Hard for non-engineers, weak progress UI, lower product feel |
| Local Web app | Best next alpha | Browser UI, file picker, stage progress, logs, previews, keeps media local | Needs local server security, job state, browser/file UX decisions |
| Hosted Web app/SaaS | Later option | Lowest install friction, easier billing/team access | Upload/privacy burden, compute/storage cost, queueing, security, takedown/copyright ops |
| Mac desktop app | Later packaging | Native feel for local-first paid product | Code signing, notarization, auto-update, FFmpeg/Python bundling, sandbox/file permissions |

## Why local Web app next

Video dubbing is a long-running media workflow. Users need to see:

- which stage is running,
- whether provider calls are live or fixture-backed,
- generated script/subtitle artifacts,
- FFmpeg render progress,
- final MP4 output location.

A local Web app can provide that without forcing video uploads. The existing CLI should remain the source of truth for the pipeline so the UI does not duplicate media logic.

## Implemented local Web alpha boundary

The first local Web alpha is intentionally thin:

- `fukikae studio` starts a stdlib loopback server.
- The browser form accepts local paths rather than uploading video files.
- The default run path is fixture-backed and calls the existing local pipeline.
- The result view displays stage status, `validation/local_test_report.json`, and `output/dubbed.ja.mp4`.
- Hosted storage, queues, billing, team sharing, and cloud upload remain later cloud-mode concerns.

## Suggested local Web architecture

```text
Browser UI on localhost
→ local Python API server
→ job runner / stage executor
→ existing CLI/pipeline modules
→ project artifacts on local disk
```

Guardrails:

- Bind to `127.0.0.1` by default.
- Use a random local session token for browser access.
- Keep live provider calls opt-in and visible.
- Keep fixture-backed mode available for local testing.
- Do not upload local media unless the user explicitly chooses a cloud mode.
- Treat FFmpeg execution as a local job with progress and logs.

## Research references

- FastAPI WebSockets: https://fastapi.tiangolo.com/advanced/websockets/
- FastAPI Background Tasks: https://fastapi.tiangolo.com/tutorial/background-tasks/
- Celery Introduction: https://docs.celeryq.dev/en/stable/getting-started/introduction.html
- FFmpeg Documentation: https://ffmpeg.org/ffmpeg.html
- FFmpeg Legal/Licensing: https://ffmpeg.org/legal.html
- PyInstaller Documentation: https://pyinstaller.org/en/stable/
- pipx Documentation: https://pipx.pypa.io/stable/
- uv Tools: https://docs.astral.sh/uv/concepts/tools/
- Apple Notarization: https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution
- Apple Developer ID: https://developer.apple.com/developer-id/
- Apple App Sandbox: https://developer.apple.com/documentation/security/app_sandbox
- Electron Code Signing: https://www.electronjs.org/docs/latest/tutorial/code-signing
- Tauri Sidecars: https://v2.tauri.app/develop/sidecar/
- MDN File System Access API: https://developer.mozilla.org/en-US/docs/Web/API/Window/showOpenFilePicker
- Stripe Checkout: https://docs.stripe.com/payments/checkout
