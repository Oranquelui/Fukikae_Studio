# xAI Endpoint Notes

Verified against public xAI documentation on 2026-05-25. This file records endpoint constants only; it must never contain credentials.

## Base URL

```text
https://api.x.ai/v1
```

## Text generation

```text
POST /v1/responses
```

The default text model used by this MVP skeleton is `grok-4.3`.

## Speech to text

```text
POST /v1/stt
Content-Type: multipart/form-data
```

The documented batch STT example sends fields such as `format`, `language`, optional key terms, and a local audio file.

## Text to speech

```text
POST /v1/tts
Content-Type: application/json
```

The documented TTS request includes `text`, `voice_id`, and `language`. The response body is raw audio bytes. Japanese is supported with language code `ja`.

## Current validation policy

- No live xAI calls during default tests.
- No API key should be printed, persisted, or included in artifact files.
- Tests must use injected transports, mocks, or fixtures.
