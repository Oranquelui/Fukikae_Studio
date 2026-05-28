import cgi
import json
import re
import secrets
import shutil
import webbrowser
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, IO, Mapping, Optional, Sequence
from urllib.parse import parse_qs, quote, urlparse

from fukikae_studio.ai.xai_client import XAIClient
from fukikae_studio.ai.xai_tts import BUILTIN_TTS_VOICES
from fukikae_studio.config import DEFAULT_XAI_BASE_URL, DEFAULT_XAI_TEXT_MODEL, DEFAULT_XAI_TTS_VOICE, XAIConfig
from fukikae_studio.pipeline.live_run import run_live_pipeline
from fukikae_studio.pipeline.local_run import run_fixture_pipeline
from fukikae_studio.pipeline.subtitle_output import DEFAULT_SUBTITLE_OUTPUT, SUBTITLE_OUTPUT_CHOICES

PipelineRunner = Callable[..., Mapping[str, Any]]
LivePipelineRunner = Callable[..., Mapping[str, Any]]
ClientFactory = Callable[[XAIConfig], Any]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_UPLOAD_DIR = Path("work") / "studio-uploads"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
STUDIO_STAGES = (
    "init",
    "stt",
    "make-script",
    "tts",
    "assemble",
    "final-mux",
    "validate",
)


def default_studio_form_values(repo_root: Optional[Path] = None) -> dict:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    return {
        "video": str(root / "work" / "local-smoke" / "source.mp4"),
        "project": str(root / "work" / "local-smoke" / "project"),
        "stt_fixture_response": str(root / "tests" / "fixtures" / "sample_stt_response.json"),
        "dubbing_fixture_response": str(root / "tests" / "fixtures" / "sample_dubbing_response.json"),
        "fixture_audio": str(root / "work" / "local-smoke" / "fixture.wav"),
        "source_lang": "auto",
        "target_lang": "ja",
        "voice": DEFAULT_XAI_TTS_VOICE,
        "subtitle_output": DEFAULT_SUBTITLE_OUTPUT,
        "run_mode": "live",
        "xai_base_url": DEFAULT_XAI_BASE_URL,
        "xai_text_model": DEFAULT_XAI_TEXT_MODEL,
    }


def validate_loopback_host(host: str) -> str:
    normalized = str(host).strip()
    if normalized not in LOOPBACK_HOSTS:
        allowed = ", ".join(sorted(LOOPBACK_HOSTS))
        raise ValueError(
            "FukiKae Studio is local-only in this alpha. "
            f"Use a loopback host ({allowed}); refusing host: {normalized or '<empty>'}"
        )
    return normalized


def build_studio_url(host: str, port: int, access_key: str) -> str:
    query = "key" + "=" + quote(access_key)
    return f"http://{host}:{port}/?{query}"


def render_studio_home(
    defaults: Mapping[str, object],
    access_key: str,
    last_result: Optional[Mapping[str, object]] = None,
    error: Optional[str] = None,
) -> str:
    result_html = _render_result(last_result) if last_result is not None else _render_empty_result()
    error_html = f'<section class="error"><h2>Error</h2><pre>{escape(error)}</pre></section>' if error else ""
    action = f"/run?key={quote(access_key)}"
    source_video_upload_url = json.dumps(f"/upload-source-video?key={quote(access_key)}")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>FukiKae Studio ローカルWeb Alpha</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 2rem; line-height: 1.45; color: #17202a; background: #ffffff; }}
    main {{ max-width: 960px; margin: 0 auto; }}
    label {{ display: block; font-weight: 700; margin-top: 1rem; }}
    input[type="text"], input[type="password"], select {{ width: 100%; padding: 0.55rem; font-size: 1rem; box-sizing: border-box; }}
    .row {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; }}
    .row-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
    .path-picker {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0.5rem; align-items: center; }}
    .path-picker button {{ margin-top: 0; white-space: nowrap; }}
    .field-status {{ min-height: 1.4em; margin: 0.35rem 0 0; color: #475569; }}
    .visually-hidden {{ position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }}
    .notice, .result, .error {{ border-radius: 12px; padding: 1rem; margin: 1rem 0; }}
    .notice {{ background: #eef6ff; border: 1px solid #b9ddff; }}
    .result {{ background: #f6f8fa; border: 1px solid #d8dee4; }}
    .error {{ background: #fff1f0; border: 1px solid #ffccc7; }}
    .settings-panel {{ background: #f6f8fa; border: 1px solid #d8dee4; border-radius: 12px; margin: 1rem 0; }}
    .settings-panel > summary {{ cursor: pointer; font-weight: 700; padding: 0.85rem 1rem; }}
    .settings-panel > summary::after {{ content: "+"; float: right; }}
    .settings-panel[open] > summary::after {{ content: "-"; }}
    .settings-body {{ border-top: 1px solid #d8dee4; padding: 1rem; }}
    .settings-body h2 {{ margin-top: 0; }}
    button {{ margin-top: 1rem; padding: 0.7rem 1.1rem; font-weight: 700; }}
    code, pre {{ background: #f6f8fa; padding: 0.15rem 0.3rem; border-radius: 4px; }}
    [hidden] {{ display: none !important; }}
  </style>
  <script>
    function toggleModeSections() {{
      const selector = document.querySelector('select[name="run_mode"]');
      const mode = selector ? selector.value : "live";
      document.querySelectorAll("[data-mode-section]").forEach((section) => {{
        section.hidden = section.getAttribute("data-mode-section") !== mode;
      }});
    }}
    function setVideoPickerStatus(message) {{
      const status = document.getElementById("source-video-picker-status");
      if (status) {{
        status.textContent = message;
      }}
    }}
    function openSourceVideoPicker() {{
      const fileInput = document.getElementById("source-video-file");
      if (fileInput) {{
        fileInput.click();
      }}
    }}
    async function uploadSourceVideo(fileInput) {{
      const input = document.querySelector('input[name="video"]');
      const button = document.querySelector('[data-file-open-target="video"]');
      const file = fileInput && fileInput.files ? fileInput.files[0] : null;
      if (!input || !button || !file) {{
        return;
      }}
      const originalLabel = button.textContent;
      button.disabled = true;
      button.textContent = "取り込み中...";
      setVideoPickerStatus("");
      try {{
        const formData = new FormData();
        formData.append("source_video", file);
        const response = await fetch({source_video_upload_url}, {{
          method: "POST",
          headers: {{ "Accept": "application/json" }},
          body: formData
        }});
        const payload = await response.json();
        if (!response.ok) {{
          throw new Error(payload.error || "動画のローカル取り込みに失敗しました。");
        }}
        if (payload.path) {{
          input.value = payload.path;
          setVideoPickerStatus("ローカルに取り込みました。");
        }} else {{
          setVideoPickerStatus("選択をキャンセルしました。");
        }}
      }} catch (error) {{
        setVideoPickerStatus(error.message || "動画のローカル取り込みに失敗しました。");
      }} finally {{
        button.disabled = false;
        button.textContent = originalLabel;
        if (fileInput) {{
          fileInput.value = "";
        }}
      }}
    }}
    window.addEventListener("DOMContentLoaded", () => {{
      const selector = document.querySelector('select[name="run_mode"]');
      if (selector) {{
        selector.addEventListener("change", toggleModeSections);
      }}
      toggleModeSections();
    }});
  </script>
</head>
<body>
<main>
  <h1>FukiKae Studio ローカルWeb Alpha</h1>
  <p><strong>内部betaモード</strong> - このマシン上のローカルパスだけを使います。</p>
  <section class="notice">
    <p>このAlphaはデフォルトで<strong>ローカル限定</strong>・<strong>fixture実行</strong>です。localhostで動作し、既存CLIパイプラインを使います。</p>
    <ul>
      <li><strong>外部アップロードなし</strong>: 選択した動画はlocalhostへローカル取り込みされ、このマシン内に残ります。</li>
      <li><strong>Live xAIモード</strong>: Live xAIモードでは、xAI STT・Grok・xAI TTSを使います。APIキーはこのローカル実行中だけ使用し、ページへ再表示しません。</li>
      <li><strong>Fixtureモード</strong>: Fixtureモードでは、ローカルJSONとWAVを使います。APIキー不要で、ライブAPI呼び出しなしです。</li>
    </ul>
  </section>
  {error_html}
  <form method="post" action="{escape(action)}">
    <div class="row-2">
      <div>
        <label>実行モード</label>
        <select name="run_mode">
          {_render_run_mode_options(_default(defaults, 'run_mode', 'live'))}
        </select>
      </div>
      <div>
        <label>字幕出力</label>
        <select name="subtitle_output">
          {_render_subtitle_output_options(_default(defaults, 'subtitle_output', DEFAULT_SUBTITLE_OUTPUT))}
        </select>
      </div>
    </div>

    <label for="source-video-path">ソース動画パス（ローカルファイル）</label>
    <div class="path-picker">
      <input id="source-video-path" type="text" name="video" value="{_default(defaults, 'video')}">
      <button type="button" data-file-open-target="video" onclick="openSourceVideoPicker()">File open</button>
    </div>
    <input id="source-video-file" class="visually-hidden" type="file" accept="video/*,.mp4,.mov,.m4v,.mkv,.webm" onchange="uploadSourceVideo(this)">
    <p id="source-video-picker-status" class="field-status" role="status" aria-live="polite"></p>

    <label>プロジェクトディレクトリ（出力先）</label>
    <input type="text" name="project" value="{_default(defaults, 'project')}">

    <section class="notice" data-mode-section="fixture">
      <h2>Fixture入力</h2>
      <p>Fixtureモードでは、ローカルJSONとWAVを資源として使います。Live xAIモードではこの欄は不要です。</p>
      <label>STT fixtureレスポンス（ライブAPIなし）</label>
      <input type="text" name="stt_fixture_response" value="{_default(defaults, 'stt_fixture_response')}">

      <label>吹き替えfixtureレスポンス（ライブAPIなし）</label>
      <input type="text" name="dubbing_fixture_response" value="{_default(defaults, 'dubbing_fixture_response')}">

      <label>Fixture TTS音声（ローカルWAV）</label>
      <input type="text" name="fixture_audio" value="{_default(defaults, 'fixture_audio')}">
    </section>

    <details class="settings-panel" data-mode-section="live">
      <summary>設定</summary>
      <div class="settings-body">
        <h2>Live xAI設定</h2>
        <p>Live xAIモードでは、ソース動画から音声を抽出し、xAI STT・Grok・xAI TTSで日本語吹き替えを生成します。Fixtureファイルは使いません。</p>
        <label>xAI APIキー</label>
        <input type="password" name="xai_api_key" value="" autocomplete="off">
        <div class="row-2">
          <div>
            <label>xAI Base URL</label>
            <input type="text" name="xai_base_url" value="{_default(defaults, 'xai_base_url', DEFAULT_XAI_BASE_URL)}">
          </div>
          <div>
            <label>Grokモデル</label>
            <input type="text" name="xai_text_model" value="{_default(defaults, 'xai_text_model', DEFAULT_XAI_TEXT_MODEL)}">
          </div>
        </div>
      </div>
    </details>

    <div class="row">
      <div>
        <label>元言語</label>
        <input type="text" name="source_lang" value="{_default(defaults, 'source_lang', 'auto')}">
      </div>
      <div>
        <label>翻訳先言語</label>
        <input type="text" name="target_lang" value="{_default(defaults, 'target_lang', 'ja')}">
      </div>
      <div>
        <label>Voice</label>
        <select name="voice">
          {_render_voice_options(_default(defaults, 'voice', DEFAULT_XAI_TTS_VOICE))}
        </select>
      </div>
    </div>

    <label><input type="checkbox" name="execute_ffmpeg"> ローカルFFmpegで最終レンダーを実行</label>
    <label><input type="checkbox" name="overwrite"> 既存artifactの上書きを許可</label>
    <button type="submit">ローカルパイプラインを実行</button>
  </form>

  {result_html}
</main>
</body>
</html>
"""


def run_studio_form(
    form: Mapping[str, object],
    pipeline_runner: PipelineRunner = run_fixture_pipeline,
    live_pipeline_runner: LivePipelineRunner = run_live_pipeline,
    client_factory: ClientFactory = XAIClient,
) -> dict:
    project_dir = Path(_required_form_value(form, "project"))
    execute_ffmpeg = _form_bool(form, "execute_ffmpeg")
    run_mode = _form_value(form, "run_mode", "fixture")
    subtitle_output = _form_value(form, "subtitle_output", DEFAULT_SUBTITLE_OUTPUT)
    if run_mode == "live":
        config = XAIConfig(
            api_key=_required_form_value(form, "xai_api_key"),
            base_url=_form_value(form, "xai_base_url", DEFAULT_XAI_BASE_URL),
            text_model=_form_value(form, "xai_text_model", DEFAULT_XAI_TEXT_MODEL),
            stt_language=_form_value(form, "source_lang", "auto"),
            tts_voice=_form_value(form, "voice", DEFAULT_XAI_TTS_VOICE),
            tts_language=_form_value(form, "target_lang", "ja"),
        )
        result = live_pipeline_runner(
            project_dir,
            source_video=Path(_required_form_value(form, "video")),
            client=client_factory(config),
            text_model=config.text_model,
            source_lang=config.stt_language,
            target_lang=config.tts_language,
            voice=config.tts_voice,
            overwrite=_form_bool(form, "overwrite"),
            execute_ffmpeg=execute_ffmpeg,
            subtitle_output=subtitle_output,
        )
    else:
        result = pipeline_runner(
            project_dir,
            source_video=Path(_required_form_value(form, "video")),
            stt_fixture_response=Path(_required_form_value(form, "stt_fixture_response")),
            dubbing_fixture_response=Path(_required_form_value(form, "dubbing_fixture_response")),
            fixture_audio=Path(_required_form_value(form, "fixture_audio")),
            source_lang=_form_value(form, "source_lang", "auto"),
            target_lang=_form_value(form, "target_lang", "ja"),
            voice=_form_value(form, "voice", DEFAULT_XAI_TTS_VOICE),
            overwrite=_form_bool(form, "overwrite"),
            execute_ffmpeg=execute_ffmpeg,
            subtitle_output=subtitle_output,
        )
    return _build_run_summary(project_dir, result, execute_ffmpeg=execute_ffmpeg)


def save_uploaded_source_video(file_obj: IO[bytes], original_filename: str, upload_dir: Path) -> Path:
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_upload_filename(original_filename)
    destination = _unique_upload_path(upload_dir, filename)
    with destination.open("wb") as output:
        shutil.copyfileobj(file_obj, output)
    return destination


def _safe_upload_filename(original_filename: str) -> str:
    source_name = Path(original_filename or "source_video.mp4").name
    source_path = Path(source_name)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", source_path.stem).strip("._-") or "source_video"
    suffix = re.sub(r"[^A-Za-z0-9.]+", "", source_path.suffix).lower() or ".mp4"
    return f"{stem[:80]}{suffix[:16]}"


def _unique_upload_path(upload_dir: Path, filename: str) -> Path:
    candidate = upload_dir / filename
    if not candidate.exists():
        return candidate
    path = Path(filename)
    for index in range(2, 10000):
        candidate = upload_dir / f"{path.stem}-{index}{path.suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("保存先ファイル名を確保できませんでした。")


def make_studio_handler(
    defaults: Mapping[str, object],
    access_key: str,
    pipeline_runner: PipelineRunner = run_fixture_pipeline,
    upload_dir: Optional[Path] = None,
):
    source_upload_dir = Path(upload_dir) if upload_dir is not None else Path.cwd() / DEFAULT_UPLOAD_DIR

    class StudioHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._send_json({"status": "ok", "mode": "local_web_alpha"})
                return
            if parsed.path != "/" or not self._is_authorized(parsed.query):
                self._send_text("Forbidden\n", status=403, content_type="text/plain; charset=utf-8")
                return
            self._send_text(render_studio_home(defaults, access_key), content_type="text/html; charset=utf-8")

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if not self._is_authorized(parsed.query):
                self._send_text("Forbidden\n", status=403, content_type="text/plain; charset=utf-8")
                return
            if parsed.path == "/upload-source-video":
                try:
                    saved_path = self._save_uploaded_source_video(source_upload_dir)
                    self._send_json({"path": str(saved_path), "filename": saved_path.name})
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=400)
                return
            if parsed.path != "/run":
                self._send_text("Forbidden\n", status=403, content_type="text/plain; charset=utf-8")
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            form = {key: values[-1] for key, values in parse_qs(body, keep_blank_values=True).items()}
            try:
                result = run_studio_form(form, pipeline_runner=pipeline_runner)
                self._send_text(
                    render_studio_home(defaults, access_key, last_result=result),
                    content_type="text/html; charset=utf-8",
                )
            except Exception as exc:  # pragma: no cover - defensive server boundary
                self._send_text(
                    render_studio_home(defaults, access_key, error=str(exc)),
                    status=400,
                    content_type="text/html; charset=utf-8",
                )

        def log_message(self, format: str, *args: object) -> None:
            return

        def _is_authorized(self, query: str) -> bool:
            return parse_qs(query).get("key", [""])[-1] == access_key

        def _save_uploaded_source_video(self, upload_dir: Path) -> Path:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                raise ValueError("動画ファイルが選択されていません。")
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                    "CONTENT_LENGTH": str(length),
                },
            )
            field = form["source_video"] if "source_video" in form else None
            if isinstance(field, list):
                field = field[0] if field else None
            if field is None or not getattr(field, "filename", ""):
                raise ValueError("動画ファイルが選択されていません。")
            return save_uploaded_source_video(field.file, str(field.filename), upload_dir)

        def _send_json(self, payload: Mapping[str, object], status: int = 200) -> None:
            self._send_text(json.dumps(payload, indent=2) + "\n", status=status, content_type="application/json")

        def _send_text(self, text: str, status: int = 200, content_type: str = "text/plain") -> None:
            encoded = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return StudioHandler


def run_studio_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    defaults: Optional[Mapping[str, object]] = None,
    access_key: Optional[str] = None,
    open_browser: bool = False,
) -> str:
    host = validate_loopback_host(host)
    form_defaults = dict(defaults or default_studio_form_values())
    session_key = access_key or secrets.token_urlsafe(16)
    server = HTTPServer((host, port), make_studio_handler(form_defaults, session_key))
    actual_port = int(server.server_address[1])
    url = build_studio_url(host, actual_port, session_key)
    print(f"FukiKae Studio Local Web Alpha: {url}")
    print("Bind address is local-only by default. Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return url


def _build_run_summary(project_dir: Path, result: Mapping[str, Any], execute_ffmpeg: bool) -> dict:
    validation = dict(result.get("validation", {}))
    status = str(validation.get("status", "unknown"))
    final_output = str(validation.get("final_output", "output/dubbed.ja.mp4"))
    final_output_exists = bool(validation.get("final_output_exists", False))
    return {
        "status": status,
        "validation_report": str(project_dir / "validation" / "local_test_report.json"),
        "output_mp4": str(project_dir / final_output),
        "final_output_exists": final_output_exists,
        "missing_required_artifacts": list(validation.get("missing_required_artifacts", [])),
        "stage_statuses": _stage_statuses(status, execute_ffmpeg=execute_ffmpeg, final_output_exists=final_output_exists),
    }


def _stage_statuses(status: str, execute_ffmpeg: bool, final_output_exists: bool) -> list:
    if status == "failed":
        return [
            {"stage": stage, "status": "failed" if stage == "validate" else "complete"}
            for stage in STUDIO_STAGES
        ]
    final_mux_status = "complete" if final_output_exists else "ready" if not execute_ffmpeg else "failed"
    return [
        {"stage": stage, "status": final_mux_status if stage == "final-mux" else "complete"}
        for stage in STUDIO_STAGES
    ]


def _render_result(result: Mapping[str, object]) -> str:
    stages = result.get("stage_statuses", [])
    rows = "\n".join(
        f"<li><strong>{escape(str(stage.get('stage', 'unknown')))}</strong>: {escape(str(stage.get('status', 'unknown')))}</li>"
        for stage in stages
        if isinstance(stage, Mapping)
    )
    return f"""<section class="result">
  <h2>実行結果</h2>
  <p>ステータス: <strong>{escape(str(result.get('status', 'unknown')))}</strong></p>
  <p>出力MP4: <code>{escape(str(result.get('output_mp4', 'output/dubbed.ja.mp4')))}</code></p>
  <p>検証レポート: <code>{escape(str(result.get('validation_report', 'validation/local_test_report.json')))}</code></p>
  <ul>{rows}</ul>
</section>"""


def _render_empty_result() -> str:
    return """<section class="result">
  <h2>実行ステータス</h2>
  <p>このブラウザセッションでは、まだローカル実行を開始していません。</p>
  <p>実行後、このパネルにステータス、出力MP4、検証レポートが表示されます。</p>
</section>"""


def _default(defaults: Mapping[str, object], key: str, fallback: str = "") -> str:
    return escape(str(defaults.get(key, fallback)), quote=True)


def _render_voice_options(selected_voice: str) -> str:
    known_voice_ids = {str(voice["voice_id"]) for voice in BUILTIN_TTS_VOICES}
    options = []
    for voice in BUILTIN_TTS_VOICES:
        voice_id = str(voice["voice_id"])
        name = str(voice["name"])
        gender = _voice_gender_label(str(voice["gender"]))
        language = _voice_language_label(str(voice["language"]))
        selected = " selected" if voice_id == selected_voice else ""
        options.append(
            f'<option value="{escape(voice_id, quote=True)}"{selected}>'
            f"{escape(name)} {escape(gender)} / {escape(language)}</option>"
        )
    if selected_voice and selected_voice not in known_voice_ids:
        options.append(
            f'<option value="{escape(selected_voice, quote=True)}" selected>'
            f"{escape(selected_voice)} カスタム</option>"
        )
    return "\n          ".join(options)


def _render_run_mode_options(selected_mode: str) -> str:
    labels = {
        "fixture": "Fixture betaモード",
        "live": "Live xAIモード",
    }
    return "\n          ".join(
        f'<option value="{escape(mode, quote=True)}"{" selected" if mode == selected_mode else ""}>'
        f"{escape(label)}</option>"
        for mode, label in labels.items()
    )


def _render_subtitle_output_options(selected_mode: str) -> str:
    labels = {
        "both": "両方",
        "burned": "焼き込み字幕（共有用）",
        "soft": "ソフト字幕（編集用）",
    }
    selected = selected_mode if selected_mode in SUBTITLE_OUTPUT_CHOICES else DEFAULT_SUBTITLE_OUTPUT
    return "\n          ".join(
        f'<option value="{escape(mode, quote=True)}"{" selected" if mode == selected else ""}>'
        f"{escape(labels[mode])}</option>"
        for mode in SUBTITLE_OUTPUT_CHOICES
    )


def _voice_gender_label(value: str) -> str:
    return {
        "female": "女性",
        "male": "男性",
    }.get(value, value)


def _voice_language_label(value: str) -> str:
    return {
        "ja": "日本語",
        "multilingual": "多言語",
    }.get(value, value)


def _required_form_value(form: Mapping[str, object], key: str) -> str:
    value = _form_value(form, key, "")
    if not value:
        raise ValueError(f"Missing required form field: {key}")
    return value


def _form_value(form: Mapping[str, object], key: str, default: str) -> str:
    value = form.get(key, default)
    if isinstance(value, (list, tuple)):
        return str(value[-1]) if value else default
    return str(value)


def _form_bool(form: Mapping[str, object], key: str) -> bool:
    value = form.get(key)
    if isinstance(value, (list, tuple)):
        value = value[-1] if value else ""
    return str(value).lower() in {"1", "true", "yes", "on"}
