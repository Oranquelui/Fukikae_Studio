import json
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from fukikae_studio.ai.xai_tts import TTS_MANIFEST_ENDPOINT
from fukikae_studio.config import DEFAULT_XAI_TTS_VOICE

AudioSynthesizer = Callable[[Mapping[str, object]], bytes]
DurationProbe = Callable[[Path, Mapping[str, object]], int]


def synthesize_voice_segments(
    project_dir: Path,
    dubbing_segments: Iterable[Mapping[str, object]],
    synthesize_audio: AudioSynthesizer,
    duration_probe_ms: DurationProbe,
    voice: str = DEFAULT_XAI_TTS_VOICE,
    language: str = "ja",
    output_extension: str = "wav",
) -> dict:
    tts_dir = Path(project_dir) / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)
    manifest_segments = []
    extension = output_extension.lstrip(".")
    for index, segment in enumerate(dubbing_segments, start=1):
        segment_id = str(segment["id"])
        output_rel = f"tts/segment_{index:04d}.{extension}"
        output_path = Path(project_dir) / output_rel
        output_path.write_bytes(synthesize_audio(segment))
        manifest_segments.append(
            {
                "id": segment_id,
                "text": str(segment["target_text"]),
                "output_audio": output_rel,
                "duration_ms": duration_probe_ms(output_path, segment),
                "target_slot_start_ms": _required_int(segment["source_start_ms"]),
                "target_slot_end_ms": _required_int(segment["source_end_ms"]),
            }
        )
    manifest = {
        "schema_version": "0.1",
        "provider": "xai",
        "endpoint": TTS_MANIFEST_ENDPOINT,
        "language": language,
        "voice": voice,
        "segments": manifest_segments,
    }
    manifest_path = tts_dir / "xai_tts_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _required_int(value: Any) -> int:
    return int(value)
