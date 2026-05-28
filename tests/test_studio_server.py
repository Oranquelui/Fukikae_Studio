import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import HTTPServer
from pathlib import Path

from fukikae_studio.web.studio import (
    build_studio_url,
    default_studio_form_values,
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
    assert 'id="project-directory-path"' in html
    assert 'data-directory-open-target="project"' in html
    assert "Directory open" in html
    assert "chooseProjectDirectory" in html
    assert "/choose-project-directory?key=abc123" in html
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
    assert "startPipelineRun" in html
    assert "renderProgressGraph" in html
    assert 'id="pipeline-progress-panel"' in html
    assert "準備" in html
    assert "音声認識" in html
    assert "翻訳" in html
    assert "音声生成" in html
    assert "最終レンダー" in html
    assert 'type="password" name="xai_api_key" value=""' in html
    assert "このローカル実行中だけ使用" in html
    assert 'name="execute_ffmpeg"' in html
    assert "同じ出力先を再実行する" in html
    assert 'name="clean_output" checked' in html
    assert "完成後はMP4だけを残す" in html
    assert "work/local-smoke/source.mp4" in html
    assert "実行ステータス" not in html
    assert "まだローカル実行を開始していません" not in html


def test_default_studio_form_values_do_not_prefill_missing_source_video(tmp_path):
    defaults = default_studio_form_values(tmp_path)

    assert defaults["video"] == ""
    html = render_studio_home(defaults, access_key="abc123")
    assert str(tmp_path / "work" / "local-smoke" / "source.mp4") not in html
    assert 'id="source-video-path" type="text" name="video" required' in html


def test_render_studio_home_never_echoes_xai_api_key_defaults():
    html = render_studio_home({"xai_api_key": "unit-test-secret"}, access_key="abc123")

    assert "unit-test-secret" not in html
    assert 'type="password" name="xai_api_key" value=""' in html


def test_render_studio_home_sanitizes_invalid_xai_api_key_errors():
    html = render_studio_home(
        {},
        access_key="abc123",
        error=(
            'xAI request failed with HTTP 400: {"code":"Client specified an invalid argument",'
            '"error":"Incorrect API key provided: xa****mc. You can obtain an API key"}'
        ),
    )

    assert "xAI API Keyが正しくありません" in html
    assert "設定を開いてAPI Keyを確認してください" in html
    assert "Incorrect API key" not in html
    assert "xa****mc" not in html
    assert "<pre>" not in html


def test_render_studio_home_sanitizes_missing_source_video_errors():
    html = render_studio_home(
        {},
        access_key="abc123",
        error="Source video was not found: /tmp/missing-source.mp4",
    )

    assert "ソース動画が見つかりません" in html
    assert "File openで動画を選択してください" in html
    assert "Source video was not found" not in html
    assert "<pre>" not in html


def test_render_studio_home_sanitizes_existing_artifact_errors():
    html = render_studio_home(
        {},
        access_key="abc123",
        error="Refusing to overwrite existing artifact: /tmp/project/input/source.mp4",
    )

    assert "出力先に既存ファイルがあります" in html
    assert "同じ出力先を再実行する" in html
    assert "Refusing to overwrite" not in html
    assert "/tmp/project/input/source.mp4" not in html
    assert "<pre>" not in html


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


def test_choose_project_directory_endpoint_returns_selected_path(tmp_path):
    selected_dir = tmp_path / "selected"
    current_dir = tmp_path / "current"
    calls = []

    def fake_directory_picker(current_path):
        calls.append(current_path)
        return selected_dir

    handler = make_studio_handler({}, access_key="abc123", directory_picker=fake_directory_picker)
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/choose-project-directory?key=abc123",
            data=json.dumps({"current_path": str(current_dir)}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload == {"path": str(selected_dir)}
        assert calls == [str(current_dir)]
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_run_endpoint_preserves_submitted_paths_after_error(tmp_path):
    submitted_video = tmp_path / "selected.mp4"
    submitted_project = tmp_path / "project"

    def failing_pipeline(*args, **kwargs):
        raise FileNotFoundError(f"Source video was not found: {submitted_video}")

    handler = make_studio_handler(
        {"video": "", "project": "work/local-smoke/project"},
        access_key="abc123",
        pipeline_runner=failing_pipeline,
    )
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = urllib.parse.urlencode(
            {
                "run_mode": "fixture",
                "video": str(submitted_video),
                "project": str(submitted_project),
                "stt_fixture_response": str(tmp_path / "stt.json"),
                "dubbing_fixture_response": str(tmp_path / "dubbing.json"),
                "fixture_audio": str(tmp_path / "fixture.wav"),
                "source_lang": "auto",
                "target_lang": "ja",
                "voice": "d0cb9ff07d95",
                "subtitle_output": "both",
                "execute_ffmpeg": "on",
                "overwrite": "on",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/run?key=abc123",
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            html = exc.read().decode("utf-8")
        else:  # pragma: no cover - defensive test branch
            raise AssertionError("Expected the failing pipeline to return HTTP 400")

        assert "ソース動画が見つかりません" in html
        assert str(submitted_video) in html
        assert str(submitted_project) in html
        assert 'name="execute_ffmpeg" checked' in html
        assert 'name="overwrite" checked' in html
        assert "work/local-smoke/source.mp4" not in html
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_run_endpoint_can_start_async_job_and_report_progress(tmp_path):
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"local video")
    project_dir = tmp_path / "project"
    started = threading.Event()
    release = threading.Event()

    def slow_pipeline(project_dir_arg, **kwargs):
        started.set()
        assert release.wait(timeout=5)
        return {
            "validation": {
                "status": "complete",
                "missing_required_artifacts": [],
                "final_output": "output/dubbed.ja.mp4",
                "final_output_exists": True,
            }
        }

    handler = make_studio_handler({}, access_key="abc123", pipeline_runner=slow_pipeline)
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = urllib.parse.urlencode(
            {
                "run_mode": "fixture",
                "video": str(source_video),
                "project": str(project_dir),
                "stt_fixture_response": str(tmp_path / "stt.json"),
                "dubbing_fixture_response": str(tmp_path / "dubbing.json"),
                "fixture_audio": str(tmp_path / "fixture.wav"),
                "source_lang": "auto",
                "target_lang": "ja",
                "voice": "d0cb9ff07d95",
                "subtitle_output": "both",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/run?key=abc123",
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            start_payload = json.loads(response.read().decode("utf-8"))

        assert start_payload["status"] in {"queued", "running"}
        assert start_payload["job_id"]
        assert started.wait(timeout=5)

        status_url = f"http://127.0.0.1:{server.server_address[1]}{start_payload['status_url']}"
        with urllib.request.urlopen(status_url) as response:
            running_payload = json.loads(response.read().decode("utf-8"))
        assert running_payload["status"] == "running"
        assert any(stage["status"] == "running" for stage in running_payload["stage_statuses"])
        assert "unit-test-secret" not in json.dumps(running_payload)

        release.set()
        complete_payload = None
        for _ in range(20):
            with urllib.request.urlopen(status_url) as response:
                complete_payload = json.loads(response.read().decode("utf-8"))
            if complete_payload["status"] == "complete":
                break
        assert complete_payload is not None
        assert complete_payload["status"] == "complete"
        assert complete_payload["result"]["output_mp4"] == str(project_dir / "output" / "dubbed.ja.mp4")
    finally:
        release.set()
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


def test_run_studio_form_can_keep_only_final_mp4_for_web_output(tmp_path):
    source_video = tmp_path / "source.mp4"
    project_dir = tmp_path / "project"

    def fake_pipeline(project_dir_arg, **kwargs):
        for relative in ("input", "media", "stt", "assembly", "script", "tts", "validation", "output"):
            (project_dir_arg / relative).mkdir(parents=True, exist_ok=True)
            (project_dir_arg / relative / "artifact.txt").write_text("artifact", encoding="utf-8")
        (project_dir_arg / "project.json").write_text("{}", encoding="utf-8")
        final_output = project_dir_arg / "output" / "dubbed.ja.burned.mp4"
        final_output.write_bytes(b"final mp4")
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
            "video": str(source_video),
            "project": str(project_dir),
            "stt_fixture_response": str(tmp_path / "stt.json"),
            "dubbing_fixture_response": str(tmp_path / "dubbing.json"),
            "fixture_audio": str(tmp_path / "fixture.wav"),
            "source_lang": "auto",
            "target_lang": "ja",
            "voice": "d0cb9ff07d95",
            "subtitle_output": "burned",
            "clean_output": "on",
        },
        pipeline_runner=fake_pipeline,
    )

    final_mp4 = project_dir / "dubbed.ja.burned.mp4"
    assert result["output_mp4"] == str(final_mp4)
    assert result["validation_report"] == ""
    assert final_mp4.read_bytes() == b"final mp4"
    assert sorted(path.name for path in project_dir.iterdir()) == ["dubbed.ja.burned.mp4"]


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
