# Public Sample Runbook

This runbook is for preparing first public sample posts without publishing secrets,
test fixtures, or generated work artifacts inside the repository.

## Sample Files

Current local sample folder:

```text
work/public-samples/2026-05-28-hqups/
```

Share-ready files:

```text
work/public-samples/2026-05-28-hqups/fukikae-sakura-ja-burned.mp4
work/public-samples/2026-05-28-hqups/fukikae-ren-ja-burned.mp4
```

These files are under `work/`, which is gitignored. Do not commit generated MP4s
unless there is a deliberate release-assets decision.

## Recommended First Post

Lead with Sakura. Keep Ren as a reply or follow-up comparison.

Draft:

```text
Testing FukiKae Studio: local-first video dubbing to Japanese.

Input: local video
Output: Japanese narration + burned Japanese captions
Provider: xAI/Grok only
Mode: local run, no upload pipeline

Voice: Sakura / ja
```

## Safety Checklist

- Use only media you have rights to share.
- Do not post API keys, request/response JSON, or local env files.
- Prefer `*.burned.mp4` for X and social posting.
- Keep source project folders under `/tmp` or `work/`; do not commit them.
- If posting a repo link, confirm `.env`, `env.local.*`, `work/`, and generated
  MP4s remain ignored.

## Product Notes To Observe

- Does Sakura or Ren get better reactions?
- Is the Sage Green subtitle box legible in mobile playback?
- Do people understand "local-first" without extra explanation?
- Does the sample make the product value clear without a UI demo?
