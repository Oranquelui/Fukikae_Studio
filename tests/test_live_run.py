import json
from pathlib import Path

from fukikae_studio.pipeline.live_run import run_live_pipeline


def test_run_live_pipeline_uses_real_stt_dubbing_tts_boundaries_with_injected_clients(tmp_path):
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"fake-video")
    project_dir = tmp_path / "project"
    commands = []

    class FakeClient:
        def post_multipart(self, path, fields, files):
            assert path == "/stt"
            assert fields == {"diarize": "true"}
            assert files["file"][0] == "source_audio_for_stt.wav"
            assert files["file"][1] == b"extracted-audio"
            return {
                "segments": [
                    {
                        "start": 0.0,
                        "end": 1.2,
                        "text": "Hello there.",
                        "speaker": 0,
                    }
                ]
            }

        def post_json(self, path, payload):
            assert path == "/responses"
            assert payload["model"] == "grok-test"
            return {
                "output_text": json.dumps(
                    {
                        "segments": [
                            {
                                "id": "seg_0001",
                                "source_start_ms": 0,
                                "source_end_ms": 1200,
                                "target_text": "こんにちは。",
                                "estimated_duration_ms": 900,
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            }

        def post_json_bytes(self, path, payload):
            assert path == "/tts"
            assert payload == {"text": "こんにちは。", "voice_id": "eve", "language": "ja"}
            return b"tts-audio"

    def fake_media_runner(command):
        commands.append(command)
        output_path = Path(command[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if "source_audio_for_stt.wav" in str(output_path):
            output_path.write_bytes(b"extracted-audio")
        else:
            output_path.write_bytes(b"rendered-media")

    result = run_live_pipeline(
        project_dir,
        source_video=source_video,
        client=FakeClient(),
        text_model="grok-test",
        voice="eve",
        target_lang="ja",
        overwrite=True,
        execute_ffmpeg=True,
        media_runner=fake_media_runner,
        duration_probe_ms=lambda path, segment: 900,
    )

    assert result["validation"]["status"] == "complete"
    assert (project_dir / "stt" / "normalized_segments.json").exists()
    assert json.loads((project_dir / "script" / "japanese_dubbing_segments.json").read_text(encoding="utf-8"))[0][
        "target_text"
    ] == "こんにちは。"
    assert (project_dir / "tts" / "segment_0001.mp3").read_bytes() == b"tts-audio"
    assert json.loads((project_dir / "tts" / "xai_tts_manifest.json").read_text(encoding="utf-8"))["segments"][0][
        "output_audio"
    ] == "tts/segment_0001.mp3"
    assert len(commands) == 4
    assert commands[0][-1] == str(project_dir / "media" / "source_audio_for_stt.wav")
    assert commands[-2][-1] == str(project_dir / "output" / "dubbed.ja.mp4")
    assert commands[-1][-1] == str(project_dir / "output" / "dubbed.ja.burned.mp4")


def test_run_live_pipeline_can_render_burned_subtitle_output_only(tmp_path):
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"fake-video")
    project_dir = tmp_path / "project"
    commands = []

    class FakeClient:
        def post_multipart(self, path, fields, files):
            return {
                "segments": [
                    {
                        "start": 0.0,
                        "end": 1.2,
                        "text": "Hello there.",
                        "speaker": 0,
                    }
                ]
            }

        def post_json(self, path, payload):
            return {
                "output_text": json.dumps(
                    {
                        "segments": [
                            {
                                "id": "seg_0001",
                                "source_start_ms": 0,
                                "source_end_ms": 1200,
                                "target_text": "こんにちは。",
                                "estimated_duration_ms": 900,
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            }

        def post_json_bytes(self, path, payload):
            return b"tts-audio"

    def fake_media_runner(command):
        commands.append(command)
        output_path = Path(command[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if "source_audio_for_stt.wav" in str(output_path):
            output_path.write_bytes(b"extracted-audio")
        else:
            output_path.write_bytes(b"rendered-media")

    result = run_live_pipeline(
        project_dir,
        source_video=source_video,
        client=FakeClient(),
        text_model="grok-test",
        voice="eve",
        target_lang="ja",
        overwrite=True,
        execute_ffmpeg=True,
        media_runner=fake_media_runner,
        duration_probe_ms=lambda path, segment: 900,
        subtitle_output="burned",
    )

    assert result["validation"]["status"] == "complete"
    assert result["validation"]["final_output"] == "output/dubbed.ja.burned.mp4"
    assert len(commands) == 3
    assert commands[-1][-1] == str(project_dir / "output" / "dubbed.ja.burned.mp4")
    assert all(command[-1] != str(project_dir / "output" / "dubbed.ja.mp4") for command in commands)


def test_run_live_pipeline_supports_japanese_to_english_dubbing_outputs(tmp_path):
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"fake-video")
    project_dir = tmp_path / "project"
    commands = []

    class FakeClient:
        def __init__(self):
            self.json_calls = []

        def post_multipart(self, path, fields, files):
            assert path == "/stt"
            assert fields == {"format": "true", "diarize": "true", "language": "ja"}
            assert files["file"][1] == b"extracted-audio"
            return {
                "segments": [
                    {
                        "start": 0.0,
                        "end": 1.5,
                        "text": "デモへようこそ。",
                        "speaker": 0,
                    }
                ]
            }

        def post_json(self, path, payload):
            self.json_calls.append(payload)
            assert path == "/responses"
            assert payload["model"] == "grok-4.3"
            prompt = payload["input"][1]["content"]
            if len(self.json_calls) == 1:
                assert "target_lang=en" in prompt
                assert "natural English dubbing" in prompt
            else:
                assert "Review and repair" in prompt
                assert "Welcome to the demo." in prompt
            return {
                "output_text": json.dumps(
                    {
                        "segments": [
                            {
                                "id": "seg_0001",
                                "source_start_ms": 0,
                                "source_end_ms": 1500,
                                "speaker": "SPEAKER_00",
                                "source_text": "デモへようこそ。",
                                "target_text": "Welcome to the demo.",
                                "reading_hint": "",
                                "style_notes": "",
                                "estimated_duration_ms": 1200,
                                "priority": "normal",
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            }

        def post_json_bytes(self, path, payload):
            assert path == "/tts"
            assert payload == {"text": "Welcome to the demo.", "voice_id": "ara", "language": "en"}
            return b"tts-audio"

    def fake_media_runner(command):
        commands.append(command)
        output_path = Path(command[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if "source_audio_for_stt.wav" in str(output_path):
            output_path.write_bytes(b"extracted-audio")
        else:
            output_path.write_bytes(b"rendered-media")

    client = FakeClient()
    result = run_live_pipeline(
        project_dir,
        source_video=source_video,
        client=client,
        text_model="grok-4.3",
        source_lang="ja",
        target_lang="en",
        voice="ara",
        overwrite=True,
        execute_ffmpeg=True,
        media_runner=fake_media_runner,
        duration_probe_ms=lambda path, segment: 1200,
    )

    assert result["validation"]["status"] == "complete"
    assert result["validation"]["final_output"] == "output/dubbed.en.burned.mp4"
    assert json.loads((project_dir / "stt" / "normalized_segments.json").read_text(encoding="utf-8"))[0][
        "source_lang"
    ] == "ja"
    assert json.loads((project_dir / "script" / "english_dubbing_segments.json").read_text(encoding="utf-8"))[0][
        "target_text"
    ] == "Welcome to the demo."
    assert (project_dir / "assembly" / "english_subtitles.srt").exists()
    assert len(client.json_calls) == 2
    assert commands[-2][-1] == str(project_dir / "output" / "dubbed.en.mp4")
    assert commands[-1][-1] == str(project_dir / "output" / "dubbed.en.burned.mp4")
