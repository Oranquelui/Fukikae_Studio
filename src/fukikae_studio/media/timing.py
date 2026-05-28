from typing import Any, Mapping


def build_narration_timeline(tts_manifest: Mapping[str, object]) -> dict:
    segments_value = tts_manifest.get("segments", [])
    segments = segments_value if isinstance(segments_value, list) else []
    clips = []
    warnings = []
    for index, segment in enumerate(segments):
        start_ms = _required_int(segment["target_slot_start_ms"])
        slot_end_ms = _required_int(segment["target_slot_end_ms"])
        duration_ms = _required_int(segment["duration_ms"])
        next_start_ms = None
        if index + 1 < len(segments):
            next_start_ms = _required_int(segments[index + 1]["target_slot_start_ms"])
        atempo = 1.0
        if next_start_ms is not None:
            available_ms = max(1, next_start_ms - start_ms)
        else:
            available_ms = duration_ms
        if next_start_ms is not None and duration_ms > available_ms:
            atempo = duration_ms / available_ms
        effective_duration_ms = int(round(duration_ms / atempo))
        end_ms = start_ms + effective_duration_ms
        status = "fits"
        if atempo > 1.0:
            status = "tempo_fit"
        elif end_ms > slot_end_ms:
            if next_start_ms is not None and end_ms > next_start_ms:
                status = "needs_review"
                warnings.append(f"{segment['id']} overlaps next segment; shorten script or review timing")
            else:
                status = "spillover"
                warnings.append(f"{segment['id']} exceeds source slot but does not overlap next segment")
        delay_filter = f"adelay={start_ms}|{start_ms}"
        if atempo > 1.0:
            delay_filter = f"atempo={atempo:.4f},{delay_filter}"
        clips.append(
            {
                "id": str(segment["id"]),
                "audio": str(segment["output_audio"]),
                "start_ms": start_ms,
                "end_ms": end_ms,
                "slot_end_ms": slot_end_ms,
                "raw_duration_ms": duration_ms,
                "effective_duration_ms": effective_duration_ms,
                "atempo": round(atempo, 4),
                "status": status,
                "delay_filter": delay_filter,
            }
        )
    return {
        "schema_version": "0.1",
        "timing_strategy": "preserve_source_start",
        "clips": clips,
        "warnings": warnings,
    }


def build_audio_mix_plan(timeline: Mapping[str, object]) -> dict:
    clips_value = timeline.get("clips", [])
    clips = clips_value if isinstance(clips_value, list) else []
    return {
        "inputs": [str(clip["audio"]) for clip in clips],
        "filters": [str(clip["delay_filter"]) for clip in clips],
        "output": "assembly/narration_track.wav",
    }


def _required_int(value: Any) -> int:
    return int(value)
