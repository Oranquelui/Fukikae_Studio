import json
import os
import subprocess
import sys
import threading
import urllib.request
from http.server import HTTPServer
from pathlib import Path

from fukikae_studio.web.studio import (
    build_studio_url,
    make_studio_handler,
    render_studio_home,
    run_studio_form,
    validate_loopback_host,
)


def test_render_studio_home_exposes_local_fixture_backed_controls():
    defaults = {
        "video": "work/local-smoke/source.mp4",
        "project": "work/local-smoke/project",
        "stt_fixture_response": "tests/fixtures/sample_stt_response.json",
        "dubbing_fixture_response": "tests/fixtures/sample_dubbing_response.json",
        "fixture_audio": "work/local-smoke/fixture.wav",
    }

    html = render_studio_home(defaults, access_key="abc123")

    assert "FukiKae Studio ローカルWeb Alpha" in html
    assert "background: #ffffff" in html
    assert "内部betaモード" in html
    assert "ローカル限定" in html
    assert "Live xAIモードでは、xAI STT・Grok・xAI TTSを使います" in html
    assert "Fixtureモードでは、ローカルJSONとWAVを使います" in html
    assert "外部アップロードなし" in html
    assert "ライブAPI呼び出しなし" in html
    assert "APIキー不要" in html
    assert 'action="/run?key=abc123"' in html
    assert 'name="video"' in html
    assert 'id="source-video-path"' in html
    assert 'id="source-video-file"' in html
    assert 'type="file"' in html
    assert 'accept="video/*,.mp4,.mov,.m4v,.mkv,.webm"' in html
    assert 'data-file-open-target="video"' in html
    assert "File open" in html
    assert "openSourceVideoPicker" in html
    assert "uploadSourceVideo" in html
    assert "/upload-source-video?key=abc123" in html
    assert "/choose-source-video" not in html
    assert 'name="project"' in html
    assert '<select name="voice">' in html
    assert '<option value="d0cb9ff07d95" selected>Sakura 女性 / 日本語</option>' in html
    assert '<option value="b1a7441b97a1">Ren 男性 / 日本語</option>' in html
    assert '<option value="eve">Eve 女性 / 多言語</option>' in html
    assert '<select name="subtitle_output">' in html
    assert '<option value="both" selected>両方</option>' in html
    assert '<option value="burned">焼き込み字幕（共有用）</option>' in html
    assert '<option value="soft">ソフト字幕（編集用）</option>' in html
    assert '<select name="run_mode">' in html
    assert '<option value="live" selected>Live xAIモード</option>' in html
    assert '<option value="fixture">Fixture betaモード</option>' in html
    assert 'data-mode-section="fixture"' in html
    assert '<section class="notice" data-mode-section="live">' not in html
    assert '<details class="settings-panel" data-mode-section="live">' in html
    assert "<summary>設定</summary>" in html
    assert "<h2>Live xAI設定</h2>" in html
    assert "toggleModeSections" in html
    assert 'type="password" name="xai_api_key" value=""' in html
    assert "このローカル実行中だけ使用" in html
    assert 'name="execute_ffmpeg"' in html
    assert "work/local-smoke/source.mp4" in html


def test_render_studio_home_never_echoes_xai_api_key_defaults():
    html = render_studio_home({"xai_api_key": "unit-test-secret"}, access_key="abc123")

    assert "unit-test-secret" not in html
    assert 'type="password" name="xai_api_key" value=""' in html


def test_render_studio_home_shows_concise_result_without_raw_json():
    html = render_studio_home(
        {},
        access_key="abc123",
        last_result={
            "status": "complete",
            "validation_report": "/FukiKae/project/validation/local_test_report.json",
            "output_mp4": "/FukiKae/project/output/dubbed.ja.burned.mp4",
            "stage_statuses": [{"stage": "validate", "status": "complete"}],
        },
    )

    assert "実行結果" in html
    assert "出力MP4" in html
    assert "/FukiKae/project/output/dubbed.ja.burned.mp4" in html
    assert "<pre>" not in html
    assert "出力artifact" not in html


def test_upload_source_video_endpoint_saves_browser_selected_file(tmp_path):
    upload_dir = tmp_path / "uploads"
    handler = make_studio_handler({}, access_key="abc123", upload_dir=upload_dir)
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        boundary = "----fukikae-test-boundary"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="source_video"; filename="sample video.mp4"\r\n'
            "Content-Type: video/mp4\r\n"
            "\r\n"
            "local video bytes"
            "\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/upload-source-video?key=abc123",
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
        saved_video = upload_dir / "sample_video.mp4"
        assert payload == {"path": str(saved_video), "filename": "sample_video.mp4"}
        assert saved_video.read_bytes() == b"local video bytes"
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_run_studio_form_uses_fixture_pipeline_and_returns_stage_statuses(tmp_path):
    calls = []
    source_video = tmp_path / "source.mp4"
    project_dir = tmp_path / "project"
    stt_fixture = tmp_path / "sample_stt_response.json"
    dubbing_fixture = tmp_path / "sample_dubbing_response.json"
    fixture_audio = tmp_path / "fixture.wav"

    def fake_pipeline(project_dir_arg, **kwargs):
        calls.append((project_dir_arg, kwargs))
        return {
            "validation": {
                "status": "complete",
                "missing_required_artifacts": [],
                "final_output": "output/dubbed.ja.mp4",
                "final_output_exists": True,
            }
        }

    result = run_studio_form(
        {
            "video": str(source_video),
            "project": str(project_dir),
            "stt_fixture_response": str(stt_fixture),
            "dubbing_fixture_response": str(dubbing_fixture),
            "fixture_audio": str(fixture_audio),
            "source_lang": "auto",
            "target_lang": "ja",
            "voice": "b1a7441b97a1",
            "subtitle_output": "burned",
            "execute_ffmpeg": "on",
        },
        pipeline_runner=fake_pipeline,
    )

    assert calls == [
        (
            project_dir,
            {
                "source_video": source_video,
                "stt_fixture_response": stt_fixture,
                "dubbing_fixture_response": dubbing_fixture,
                "fixture_audio": fixture_audio,
                "source_lang": "auto",
                "target_lang": "ja",
                "voice": "b1a7441b97a1",
                "subtitle_output": "burned",
                "overwrite": False,
                "execute_ffmpeg": True,
            },
        )
    ]
    assert result["status"] == "complete"
    assert result["output_mp4"] == str(project_dir / "output" / "dubbed.ja.mp4")
    assert result["validation_report"] == str(project_dir / "validation" / "local_test_report.json")
    assert result["stage_statuses"] == [
        {"stage": "init", "status": "complete"},
        {"stage": "stt", "status": "complete"},
        {"stage": "make-script", "status": "complete"},
        {"stage": "tts", "status": "complete"},
        {"stage": "assemble", "status": "complete"},
        {"stage": "final-mux", "status": "complete"},
        {"stage": "validate", "status": "complete"},
    ]


def test_run_studio_form_can_run_live_pipeline_with_ephemeral_xai_key(tmp_path):
    calls = []
    configs = []
    source_video = tmp_path / "source.mp4"
    project_dir = tmp_path / "project"

    class FakeClient:
        pass

    def fake_client_factory(config):
        configs.append(config)
        return FakeClient()

    def fake_live_pipeline(project_dir_arg, **kwargs):
        calls.append((project_dir_arg, kwargs))
        return {
            "validation": {
                "status": "complete",
                "missing_required_artifacts": [],
                "final_output": "output/dubbed.ja.burned.mp4",
                "final_output_exists": True,
            }
        }

    result = run_studio_form(
        {
            "run_mode": "live",
            "video": str(source_video),
            "project": str(project_dir),
            "source_lang": "auto",
            "target_lang": "ja",
            "voice": "d0cb9ff07d95",
            "subtitle_output": "both",
            "xai_api_key": "unit-test-secret",
            "xai_base_url": "https://api.x.ai/v1",
            "xai_text_model": "grok-test",
            "execute_ffmpeg": "on",
            "overwrite": "on",
        },
        live_pipeline_runner=fake_live_pipeline,
        client_factory=fake_client_factory,
    )

    assert configs[0].api_key == "unit-test-secret"
    assert calls == [
        (
            project_dir,
            {
                "source_video": source_video,
                "client": configs and calls[0][1]["client"],
                "text_model": "grok-test",
                "source_lang": "auto",
                "target_lang": "ja",
                "voice": "d0cb9ff07d95",
                "overwrite": True,
                "execute_ffmpeg": True,
                "subtitle_output": "both",
            },
        )
    ]
    assert isinstance(calls[0][1]["client"], FakeClient)
    assert result["status"] == "complete"
    assert result["output_mp4"] == str(project_dir / "output" / "dubbed.ja.burned.mp4")
    assert "unit-test-secret" not in str(result)


def test_build_studio_url_uses_loopback_host_and_access_key():
    expected = "http://127.0.0.1:8765/?" + "key" + "=" + "abc123"
    assert build_studio_url("127.0.0.1", 8765, "abc123") == expected


def test_validate_loopback_host_allows_only_local_browser_hosts():
    assert validate_loopback_host("127.0.0.1") == "127.0.0.1"
    assert validate_loopback_host("localhost") == "localhost"
    assert validate_loopback_host("::1") == "::1"

    for host in ["0.0.0.0", "192.168.1.10", "example.com", ""]:
        try:
            validate_loopback_host(host)
        except ValueError as exc:
            assert "local-only" in str(exc)
        else:  # pragma: no cover - assertion branch
            raise AssertionError(f"host should have been rejected: {host}")


def test_studio_command_rejects_non_loopback_host_without_traceback():
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src") + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [sys.executable, "-m", "fukikae_studio", "studio", "--host", "0.0.0.0", "--port", "0"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "local-only" in result.stderr
    assert "Traceback" not in result.stderr


def test_studio_command_help_exposes_localhost_web_alpha():
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src") + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [sys.executable, "-m", "fukikae_studio", "studio", "--help"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "localhost Web UI alpha" in result.stdout
    assert "127.0.0.1" in result.stdout
    assert "fixture-backed" in result.stdout
