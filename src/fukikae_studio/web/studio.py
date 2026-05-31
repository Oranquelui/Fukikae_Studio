import cgi
import json
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, IO, Mapping, Optional, Sequence
from urllib.parse import parse_qs, quote, urlparse

from fukikae_studio.ai.xai_client import XAIClient
from fukikae_studio.ai.xai_tts import BUILTIN_TTS_VOICES
from fukikae_studio.config import DEFAULT_XAI_BASE_URL, DEFAULT_XAI_TEXT_MODEL, DEFAULT_XAI_TTS_VOICE, XAIConfig
from fukikae_studio.pipeline.language_artifacts import normalize_target_language
from fukikae_studio.pipeline.live_run import run_live_pipeline
from fukikae_studio.pipeline.subtitle_output import DEFAULT_SUBTITLE_OUTPUT, SUBTITLE_OUTPUT_CHOICES

LivePipelineRunner = Callable[..., Mapping[str, Any]]
ClientFactory = Callable[[XAIConfig], Any]
DirectoryPicker = Callable[[Optional[str]], Optional[Path]]
APIKeyLoader = Callable[[], str]
APIKeySaver = Callable[[str], None]
APIKeyDeleter = Callable[[], None]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_UPLOAD_DIR = Path("work") / "studio-uploads"
XAI_KEYCHAIN_SERVICE = "FukiKae Studio xAI API Key"
XAI_KEYCHAIN_ACCOUNT = "default"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
GENERATED_PROJECT_ARTIFACTS = (
    "input",
    "media",
    "stt",
    "assembly",
    "output",
    "script",
    "tts",
    "validation",
    "project.json",
)
STUDIO_STAGES = (
    "init",
    "stt",
    "make-script",
    "tts",
    "assemble",
    "final-mux",
    "validate",
)
STUDIO_STAGE_LABELS = {
    "init": "準備",
    "stt": "音声認識",
    "make-script": "翻訳",
    "tts": "音声生成",
    "assemble": "組み立て",
    "final-mux": "最終レンダー",
    "validate": "検証",
}
STUDIO_STAGE_ESTIMATE_SECONDS = 4.0


def default_studio_form_values(repo_root: Optional[Path] = None) -> dict:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    return {
        "video": "",
        "project": str(root / "work" / "local-smoke" / "project"),
        "source_lang": "auto",
        "target_lang": "ja",
        "voice": DEFAULT_XAI_TTS_VOICE,
        "subtitle_output": DEFAULT_SUBTITLE_OUTPUT,
        "xai_base_url": DEFAULT_XAI_BASE_URL,
        "xai_text_model": DEFAULT_XAI_TEXT_MODEL,
        "clean_output": True,
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
    error_html = _render_error(error) if error else ""
    action = f"/run?key={quote(access_key)}"
    source_video_upload_url = json.dumps(f"/upload-source-video?key={quote(access_key)}")
    project_directory_choose_url = json.dumps(f"/choose-project-directory?key={quote(access_key)}")
    xai_api_key_status_url = json.dumps(f"/xai-api-key-status?key={quote(access_key)}")
    xai_api_key_save_url = json.dumps(f"/save-xai-api-key?key={quote(access_key)}")
    xai_api_key_delete_url = json.dumps(f"/delete-xai-api-key?key={quote(access_key)}")
    stage_labels_json = json.dumps(STUDIO_STAGE_LABELS, ensure_ascii=False)
    initial_stage_statuses_json = json.dumps(_initial_progress_stage_statuses(), ensure_ascii=False)
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
    .settings-actions {{ display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; margin-top: 1rem; }}
    .settings-actions button {{ margin-top: 0; }}
    .progress-panel {{ background: #f8fbff; border: 1px solid #b9ddff; border-radius: 12px; padding: 1rem; margin: 1rem 0; }}
    .progress-panel h2 {{ margin-top: 0; }}
    .progress-graph {{ display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 0.5rem; margin-top: 1rem; }}
    .progress-step {{ border: 1px solid #d8dee4; border-radius: 8px; background: #ffffff; padding: 0.7rem 0.5rem; min-height: 4.25rem; display: grid; gap: 0.35rem; align-content: center; text-align: center; }}
    .progress-dot {{ width: 0.75rem; height: 0.75rem; border-radius: 999px; background: #cbd5e1; margin: 0 auto; }}
    .progress-label {{ font-weight: 700; font-size: 0.88rem; }}
    .progress-status {{ color: #475569; font-size: 0.82rem; }}
    .progress-step[data-status="running"] {{ border-color: #00c853; box-shadow: 0 0 0 2px rgba(0, 200, 83, 0.14); }}
    .progress-step[data-status="running"] .progress-dot {{ background: #00c853; }}
    .progress-step[data-status="complete"] {{ border-color: #8ee4af; background: #f1fff7; }}
    .progress-step[data-status="complete"] .progress-dot {{ background: #00a66a; }}
    .progress-step[data-status="failed"] {{ border-color: #ffccc7; background: #fff7f6; }}
    .progress-step[data-status="failed"] .progress-dot {{ background: #d93025; }}
    button {{ margin-top: 1rem; padding: 0.7rem 1.1rem; font-weight: 700; }}
    code, pre {{ background: #f6f8fa; padding: 0.15rem 0.3rem; border-radius: 4px; }}
    @media (max-width: 720px) {{
      .row, .row-2 {{ grid-template-columns: 1fr; }}
      .progress-graph {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    [hidden] {{ display: none !important; }}
  </style>
  <script>
    const STUDIO_STAGE_LABELS = {stage_labels_json};
    const INITIAL_STAGE_STATUSES = {initial_stage_statuses_json};
    const STATUS_LABELS = {{
      queued: "待機中",
      running: "実行中",
      complete: "完了",
      ready: "準備完了",
      failed: "失敗",
      pending: "待機中"
    }};
    let runStatusTimer = null;
    const SETTINGS_STORAGE_KEY = "fukikae.studio.settings.v1";
    const SAVED_TEXT_FIELDS = ["xai_base_url", "xai_text_model", "source_lang", "target_lang", "voice", "subtitle_output"];
    const SAVED_CHECKBOX_FIELDS = ["execute_ffmpeg", "overwrite", "clean_output"];

    function statusLabel(status) {{
      return STATUS_LABELS[status] || status || "unknown";
    }}
    function renderProgressGraph(stages) {{
      const graph = document.getElementById("pipeline-progress-graph");
      if (!graph) {{
        return;
      }}
      graph.replaceChildren();
      (stages || INITIAL_STAGE_STATUSES).forEach((stage) => {{
        const item = document.createElement("div");
        const status = stage.status || "pending";
        item.className = "progress-step";
        item.dataset.status = status;

        const dot = document.createElement("span");
        dot.className = "progress-dot";
        dot.setAttribute("aria-hidden", "true");

        const label = document.createElement("span");
        label.className = "progress-label";
        label.textContent = stage.label || STUDIO_STAGE_LABELS[stage.stage] || stage.stage || "stage";

        const state = document.createElement("span");
        state.className = "progress-status";
        state.textContent = statusLabel(status);

        item.append(dot, label, state);
        graph.append(item);
      }});
    }}
    function setRunButtonBusy(isBusy) {{
      const button = document.querySelector('#pipeline-run-form button[type="submit"]');
      if (!button) {{
        return;
      }}
      button.disabled = isBusy;
      button.textContent = isBusy ? "実行中..." : "ローカルパイプラインを実行";
    }}
    function showProgressPanel(payload) {{
      const panel = document.getElementById("pipeline-progress-panel");
      const message = document.getElementById("pipeline-progress-message");
      if (!panel) {{
        return;
      }}
      panel.hidden = false;
      if (message) {{
        message.textContent = payload.message || "ローカルパイプラインを実行しています。";
      }}
      renderProgressGraph(payload.stage_statuses || INITIAL_STAGE_STATUSES);
    }}
    function hideAsyncPanels() {{
      const asyncError = document.getElementById("async-error-panel");
      const asyncResult = document.getElementById("async-result-panel");
      if (asyncError) {{
        asyncError.hidden = true;
      }}
      if (asyncResult) {{
        asyncResult.hidden = true;
      }}
    }}
    function showAsyncError(message) {{
      const panel = document.getElementById("async-error-panel");
      const text = document.getElementById("async-error-message");
      if (!panel || !text) {{
        return;
      }}
      text.textContent = message || "実行に失敗しました。";
      panel.hidden = false;
      setRunButtonBusy(false);
    }}
    function showAsyncResult(result) {{
      const panel = document.getElementById("async-result-panel");
      if (!panel || !result) {{
        return;
      }}
      const status = document.getElementById("async-result-status");
      const output = document.getElementById("async-result-output");
      const report = document.getElementById("async-result-report");
      if (status) {{
        status.textContent = result.status || "unknown";
      }}
      if (output) {{
        output.textContent = result.output_mp4 || "";
      }}
      if (report) {{
        report.textContent = result.validation_report || "";
      }}
      const reportRow = document.getElementById("async-result-report-row");
      if (reportRow) {{
        reportRow.hidden = !result.validation_report;
      }}
      panel.hidden = false;
      setRunButtonBusy(false);
    }}
    async function pollRunStatus(statusUrl) {{
      try {{
        const response = await fetch(statusUrl, {{ headers: {{ "Accept": "application/json" }} }});
        const payload = await response.json();
        if (!response.ok) {{
          throw new Error(payload.error || "進捗を取得できませんでした。");
        }}
        showProgressPanel(payload);
        if (payload.status === "complete") {{
          clearTimeout(runStatusTimer);
          showAsyncResult(payload.result);
          return;
        }}
        if (payload.status === "failed") {{
          clearTimeout(runStatusTimer);
          showAsyncError(payload.error || "実行に失敗しました。");
          return;
        }}
        runStatusTimer = setTimeout(() => pollRunStatus(statusUrl), payload.poll_ms || 1000);
      }} catch (error) {{
        clearTimeout(runStatusTimer);
        showAsyncError(error.message || "進捗を取得できませんでした。");
      }}
    }}
    async function startPipelineRun(event) {{
      event.preventDefault();
      const form = event.currentTarget;
      if (!form.reportValidity()) {{
        return;
      }}
      clearTimeout(runStatusTimer);
      hideAsyncPanels();
      setRunButtonBusy(true);
      showProgressPanel({{
        message: "ローカルパイプラインを開始しています。",
        stage_statuses: INITIAL_STAGE_STATUSES
      }});
      const progressPanel = document.getElementById("pipeline-progress-panel");
      if (progressPanel) {{
        progressPanel.scrollIntoView({{ behavior: "smooth", block: "start" }});
      }}
      try {{
        const response = await fetch(form.action, {{
          method: "POST",
          headers: {{ "Accept": "application/json" }},
          body: new URLSearchParams(new FormData(form))
        }});
        const payload = await response.json();
        if (!response.ok) {{
          throw new Error(payload.error || "ローカルパイプラインを開始できませんでした。");
        }}
        showProgressPanel(payload);
        pollRunStatus(new URL(payload.status_url, window.location.href).toString());
      }} catch (error) {{
        clearTimeout(runStatusTimer);
        showAsyncError(error.message || "ローカルパイプラインを開始できませんでした。");
      }}
    }}
    function pipelineForm() {{
      return document.getElementById("pipeline-run-form");
    }}
    function setSettingsStatus(message) {{
      const status = document.getElementById("settings-save-status");
      if (status) {{
        status.textContent = message;
      }}
    }}
    function setXaiApiKeyStatus(message) {{
      const status = document.getElementById("xai-api-key-save-status");
      if (status) {{
        status.textContent = message;
      }}
    }}
    function loadSavedStudioSettings() {{
      const form = pipelineForm();
      if (!form) {{
        return;
      }}
      let saved = null;
      try {{
        saved = JSON.parse(localStorage.getItem(SETTINGS_STORAGE_KEY) || "null");
      }} catch (error) {{
        saved = null;
      }}
      if (!saved || typeof saved !== "object") {{
        return;
      }}
      SAVED_TEXT_FIELDS.forEach((name) => {{
        const field = form.elements[name];
        if (field && Object.prototype.hasOwnProperty.call(saved, name)) {{
          field.value = saved[name] || "";
        }}
      }});
      SAVED_CHECKBOX_FIELDS.forEach((name) => {{
        const field = form.elements[name];
        if (field && Object.prototype.hasOwnProperty.call(saved, name)) {{
          field.checked = Boolean(saved[name]);
        }}
      }});
    }}
    function saveStudioSettings() {{
      const form = pipelineForm();
      if (!form) {{
        return;
      }}
      const settings = {{}};
      SAVED_TEXT_FIELDS.forEach((name) => {{
        const field = form.elements[name];
        if (field) {{
          settings[name] = field.value;
        }}
      }});
      SAVED_CHECKBOX_FIELDS.forEach((name) => {{
        const field = form.elements[name];
        if (field) {{
          settings[name] = Boolean(field.checked);
        }}
      }});
      localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
      setSettingsStatus("設定を保存しました。");
    }}
    async function refreshXaiApiKeyStatus() {{
      try {{
        const response = await fetch({xai_api_key_status_url}, {{ headers: {{ "Accept": "application/json" }} }});
        const payload = await response.json();
        if (!response.ok) {{
          throw new Error(payload.error || "保存状態を確認できませんでした。");
        }}
        setXaiApiKeyStatus(payload.saved ? "保存済みAPI Keyがあります。" : "保存済みAPI Keyはありません。");
      }} catch (error) {{
        setXaiApiKeyStatus(error.message || "保存状態を確認できませんでした。");
      }}
    }}
    async function saveXaiApiKey() {{
      const form = pipelineForm();
      const field = form ? form.elements["xai_api_key"] : null;
      const apiKey = field ? field.value.trim() : "";
      if (!apiKey) {{
        setXaiApiKeyStatus("保存するAPI Keyを入力してください。");
        return;
      }}
      try {{
        const response = await fetch({xai_api_key_save_url}, {{
          method: "POST",
          headers: {{ "Accept": "application/json", "Content-Type": "application/json" }},
          body: JSON.stringify({{ xai_api_key: apiKey }})
        }});
        const payload = await response.json();
        if (!response.ok) {{
          throw new Error(payload.error || "API Keyを保存できませんでした。");
        }}
        field.value = "";
        setXaiApiKeyStatus("API KeyをこのMacに保存しました。");
      }} catch (error) {{
        setXaiApiKeyStatus(error.message || "API Keyを保存できませんでした。");
      }}
    }}
    async function deleteXaiApiKey() {{
      try {{
        const response = await fetch({xai_api_key_delete_url}, {{
          method: "POST",
          headers: {{ "Accept": "application/json", "Content-Type": "application/json" }},
          body: JSON.stringify({{}})
        }});
        const payload = await response.json();
        if (!response.ok) {{
          throw new Error(payload.error || "保存済みAPI Keyを削除できませんでした。");
        }}
        setXaiApiKeyStatus("保存済みAPI Keyを削除しました。");
      }} catch (error) {{
        setXaiApiKeyStatus(error.message || "保存済みAPI Keyを削除できませんでした。");
      }}
    }}
    function setVideoPickerStatus(message) {{
      const status = document.getElementById("source-video-picker-status");
      if (status) {{
        status.textContent = message;
      }}
    }}
    function setProjectDirectoryPickerStatus(message) {{
      const status = document.getElementById("project-directory-picker-status");
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
    async function chooseProjectDirectory() {{
      const input = document.querySelector('input[name="project"]');
      const button = document.querySelector('[data-directory-open-target="project"]');
      if (!input || !button) {{
        return;
      }}
      const originalLabel = button.textContent;
      button.disabled = true;
      button.textContent = "選択中...";
      setProjectDirectoryPickerStatus("");
      try {{
        const response = await fetch({project_directory_choose_url}, {{
          method: "POST",
          headers: {{ "Accept": "application/json", "Content-Type": "application/json" }},
          body: JSON.stringify({{ current_path: input.value }})
        }});
        const payload = await response.json();
        if (!response.ok) {{
          throw new Error(payload.error || "出力先フォルダの選択に失敗しました。");
        }}
        if (payload.path) {{
          input.value = payload.path;
          setProjectDirectoryPickerStatus("出力先を選択しました。");
        }} else {{
          setProjectDirectoryPickerStatus("選択をキャンセルしました。");
        }}
      }} catch (error) {{
        setProjectDirectoryPickerStatus(error.message || "出力先フォルダの選択に失敗しました。");
      }} finally {{
        button.disabled = false;
        button.textContent = originalLabel;
      }}
    }}
    window.addEventListener("DOMContentLoaded", () => {{
      const form = document.getElementById("pipeline-run-form");
      if (form) {{
        loadSavedStudioSettings();
        form.addEventListener("submit", startPipelineRun);
      }}
      refreshXaiApiKeyStatus();
      renderProgressGraph(INITIAL_STAGE_STATUSES);
    }});
  </script>
</head>
<body>
<main>
  <h1>FukiKae Studio ローカルWeb Alpha</h1>
  <p><strong>ローカル実行モード</strong> - このマシン上のローカルパスだけを使います。</p>
  <section class="notice">
    <p>このAlphaは<strong>ローカル限定</strong>で動作し、xAI STT・Grok・xAI TTSで吹き替えを生成します。</p>
    <ul>
      <li><strong>外部アップロードなし</strong>: 選択した動画はlocalhostへローカル取り込みされ、このマシン内に残ります。</li>
      <li><strong>Live xAIモード</strong>: Live xAIモードでは、xAI STT・Grok・xAI TTSを使います。APIキーはこのローカル実行中だけ使用し、ページへ再表示しません。</li>
    </ul>
  </section>
  {error_html}
  <section id="async-error-panel" class="error" hidden>
    <h2>エラー</h2>
    <p id="async-error-message"></p>
  </section>

  <section id="pipeline-progress-panel" class="progress-panel" hidden>
    <h2>実行中</h2>
    <p id="pipeline-progress-message">待機中</p>
    <div id="pipeline-progress-graph" class="progress-graph" aria-label="実行ステージ"></div>
  </section>

  <section id="async-result-panel" class="result" hidden>
    <h2>実行結果</h2>
    <p>ステータス: <strong id="async-result-status"></strong></p>
    <p>出力MP4: <code id="async-result-output"></code></p>
    <p id="async-result-report-row">検証レポート: <code id="async-result-report"></code></p>
  </section>

  <form id="pipeline-run-form" method="post" action="{escape(action)}">
    <input type="hidden" name="run_mode" value="live">
    <div class="row-2">
      <div>
        <label>字幕出力</label>
        <select name="subtitle_output">
          {_render_subtitle_output_options(_default(defaults, 'subtitle_output', DEFAULT_SUBTITLE_OUTPUT))}
        </select>
      </div>
    </div>

    <label for="source-video-path">ソース動画パス（ローカルファイル）</label>
    <div class="path-picker">
      <input id="source-video-path" type="text" name="video" required value="{_default(defaults, 'video')}">
      <button type="button" data-file-open-target="video" onclick="openSourceVideoPicker()">File open</button>
    </div>
    <input id="source-video-file" class="visually-hidden" type="file" accept="video/*,.mp4,.mov,.m4v,.mkv,.webm" onchange="uploadSourceVideo(this)">
    <p id="source-video-picker-status" class="field-status" role="status" aria-live="polite"></p>

    <label for="project-directory-path">プロジェクトディレクトリ（出力先）</label>
    <div class="path-picker">
      <input id="project-directory-path" type="text" name="project" value="{_default(defaults, 'project')}">
      <button type="button" data-directory-open-target="project" onclick="chooseProjectDirectory()">Directory open</button>
    </div>
    <p id="project-directory-picker-status" class="field-status" role="status" aria-live="polite"></p>

    <details class="settings-panel">
      <summary>設定</summary>
      <div class="settings-body">
        <h2>Live xAI設定</h2>
        <p>Live xAIモードでは、ソース動画から音声を抽出し、xAI STT・Grok・xAI TTSで吹き替えを生成します。</p>
        <label>xAI APIキー</label>
        <input type="password" name="xai_api_key" value="" autocomplete="off">
        <div class="settings-actions">
          <button type="button" onclick="saveXaiApiKey()">API KeyをこのMacに保存</button>
          <button type="button" onclick="deleteXaiApiKey()">保存済みAPI Keyを削除</button>
        </div>
        <p id="xai-api-key-save-status" class="field-status" role="status" aria-live="polite"></p>
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
        <div class="settings-actions">
          <button type="button" onclick="saveStudioSettings()">設定を保存</button>
        </div>
        <p id="settings-save-status" class="field-status" role="status" aria-live="polite"></p>
      </div>
    </details>

    <div class="row">
      <div>
        <label>元言語</label>
        <input type="text" name="source_lang" value="{_default(defaults, 'source_lang', 'auto')}">
      </div>
      <div>
        <label>翻訳先言語</label>
        <select name="target_lang">
          {_render_target_language_options(_default(defaults, 'target_lang', 'ja'))}
        </select>
      </div>
      <div>
        <label>Voice</label>
        <select name="voice">
          {_render_voice_options(_default(defaults, 'voice', DEFAULT_XAI_TTS_VOICE))}
        </select>
      </div>
    </div>

    <label><input type="checkbox" name="execute_ffmpeg"{_checked(defaults, 'execute_ffmpeg')}> ローカルFFmpegで最終レンダーを実行</label>
    <label><input type="checkbox" name="overwrite"{_checked(defaults, 'overwrite')}> 同じ出力先を再実行する（既存ファイルを上書き）</label>
    <label><input type="checkbox" name="clean_output"{_checked(defaults, 'clean_output', default=True)}> 完成後はMP4だけを残す</label>
    <button type="submit">ローカルパイプラインを実行</button>
  </form>

  {result_html}
</main>
</body>
</html>
"""


def run_studio_form(
    form: Mapping[str, object],
    live_pipeline_runner: LivePipelineRunner = run_live_pipeline,
    client_factory: ClientFactory = XAIClient,
    api_key_loader: Optional[APIKeyLoader] = None,
) -> dict:
    project_dir = Path(_required_form_value(form, "project"))
    execute_ffmpeg = _form_bool(form, "execute_ffmpeg")
    subtitle_output = _form_value(form, "subtitle_output", DEFAULT_SUBTITLE_OUTPUT)
    target_lang = normalize_target_language(_form_value(form, "target_lang", "ja"))
    key_loader = api_key_loader or load_xai_api_key_from_keychain
    api_key = _form_value(form, "xai_api_key", "").strip() or key_loader().strip()
    config = XAIConfig(
        api_key=api_key,
        base_url=_form_value(form, "xai_base_url", DEFAULT_XAI_BASE_URL),
        text_model=_form_value(form, "xai_text_model", DEFAULT_XAI_TEXT_MODEL),
        stt_language=_form_value(form, "source_lang", "auto"),
        tts_voice=_form_value(form, "voice", DEFAULT_XAI_TTS_VOICE),
        tts_language=target_lang,
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
    summary = _build_run_summary(project_dir, result, execute_ffmpeg=execute_ffmpeg)
    if _form_bool(form, "clean_output"):
        summary = _keep_only_final_mp4(project_dir, summary, overwrite=_form_bool(form, "overwrite"))
    return summary


class RunJobStore:
    def __init__(
        self,
        live_pipeline_runner: LivePipelineRunner = run_live_pipeline,
        client_factory: ClientFactory = XAIClient,
        api_key_loader: Optional[APIKeyLoader] = None,
    ) -> None:
        self._live_pipeline_runner = live_pipeline_runner
        self._client_factory = client_factory
        self._api_key_loader = api_key_loader or load_xai_api_key_from_keychain
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def start(self, form: Mapping[str, object]) -> dict:
        job_id = secrets.token_urlsafe(12)
        now = time.monotonic()
        job = {
            "job_id": job_id,
            "status": "queued",
            "message": "ローカルパイプラインを開始しています。",
            "started_at": now,
            "updated_at": now,
            "result": None,
            "error": None,
            "failed_stage": None,
        }
        with self._lock:
            self._jobs[job_id] = job
        thread = threading.Thread(target=self._run_job, args=(job_id, dict(form)), daemon=True)
        thread.start()
        snapshot = self.snapshot(job_id)
        if snapshot is None:  # pragma: no cover - defensive boundary
            raise RuntimeError("ジョブを開始できませんでした。")
        return snapshot

    def snapshot(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return _public_job_snapshot(dict(job))

    def _run_job(self, job_id: str, form: Mapping[str, object]) -> None:
        self._update(job_id, status="running", message="ローカルパイプラインを実行しています。")
        try:
            result = run_studio_form(
                form,
                live_pipeline_runner=self._live_pipeline_runner,
                client_factory=self._client_factory,
                api_key_loader=self._api_key_loader,
            )
        except Exception as exc:  # pragma: no cover - exercised through server boundary tests
            self._update(
                job_id,
                status="failed",
                error=_friendly_error_message(str(exc)),
                failed_stage=_estimated_active_stage_index(self._started_at(job_id)),
                message="ローカルパイプラインが停止しました。",
            )
            return
        self._update(job_id, status="complete", result=result, message="ローカルパイプラインが完了しました。")

    def _started_at(self, job_id: str) -> float:
        with self._lock:
            job = self._jobs.get(job_id, {})
            return float(job.get("started_at", time.monotonic()))

    def _update(self, job_id: str, **changes: object) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.update(changes)
            job["updated_at"] = time.monotonic()


def save_uploaded_source_video(file_obj: IO[bytes], original_filename: str, upload_dir: Path) -> Path:
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_upload_filename(original_filename)
    destination = _unique_upload_path(upload_dir, filename)
    with destination.open("wb") as output:
        shutil.copyfileobj(file_obj, output)
    return destination


def choose_project_directory(current_path: Optional[str] = None) -> Optional[Path]:
    if sys.platform != "darwin":
        raise RuntimeError("Directory openは現在macOSのローカル実行でのみ利用できます。")
    command = [
        "osascript",
        "-e",
        'POSIX path of (choose folder with prompt "出力先フォルダを選択してください")',
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode == 0:
        selected_path = completed.stdout.strip()
        return Path(selected_path) if selected_path else None
    stderr = completed.stderr.strip()
    if "User canceled" in stderr or "(-128)" in stderr:
        return None
    raise RuntimeError(stderr or "出力先フォルダの選択に失敗しました。")


def load_xai_api_key_from_keychain() -> str:
    if sys.platform != "darwin":
        return ""
    completed = subprocess.run(
        [
            "security",
            "find-generic-password",
            "-a",
            XAI_KEYCHAIN_ACCOUNT,
            "-s",
            XAI_KEYCHAIN_SERVICE,
            "-w",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def save_xai_api_key_to_keychain(api_key: str) -> None:
    cleaned = api_key.strip()
    if not cleaned:
        raise ValueError("xAI API Keyを入力してください。")
    if sys.platform != "darwin":
        raise RuntimeError("API Key保存は現在macOSのローカル実行でのみ利用できます。")
    completed = subprocess.run(
        [
            "security",
            "add-generic-password",
            "-a",
            XAI_KEYCHAIN_ACCOUNT,
            "-s",
            XAI_KEYCHAIN_SERVICE,
            "-w",
            cleaned,
            "-U",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "API Keyの保存に失敗しました。")


def delete_xai_api_key_from_keychain() -> None:
    if sys.platform != "darwin":
        raise RuntimeError("API Key削除は現在macOSのローカル実行でのみ利用できます。")
    completed = subprocess.run(
        [
            "security",
            "delete-generic-password",
            "-a",
            XAI_KEYCHAIN_ACCOUNT,
            "-s",
            XAI_KEYCHAIN_SERVICE,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode not in {0, 44}:
        raise RuntimeError(completed.stderr.strip() or "保存済みAPI Keyの削除に失敗しました。")


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
    live_pipeline_runner: LivePipelineRunner = run_live_pipeline,
    client_factory: ClientFactory = XAIClient,
    api_key_loader: Optional[APIKeyLoader] = None,
    api_key_saver: Optional[APIKeySaver] = None,
    api_key_deleter: Optional[APIKeyDeleter] = None,
    upload_dir: Optional[Path] = None,
    directory_picker: DirectoryPicker = choose_project_directory,
    job_store: Optional[RunJobStore] = None,
):
    source_upload_dir = Path(upload_dir) if upload_dir is not None else Path.cwd() / DEFAULT_UPLOAD_DIR
    key_loader = api_key_loader or load_xai_api_key_from_keychain
    key_saver = api_key_saver or save_xai_api_key_to_keychain
    key_deleter = api_key_deleter or delete_xai_api_key_from_keychain
    jobs = job_store or RunJobStore(
        live_pipeline_runner=live_pipeline_runner,
        client_factory=client_factory,
        api_key_loader=key_loader,
    )

    class StudioHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._send_json({"status": "ok", "mode": "local_web_alpha"})
                return
            if parsed.path == "/run-status":
                if not self._is_authorized(parsed.query):
                    self._send_json({"error": "Forbidden"}, status=403)
                    return
                job_id = parse_qs(parsed.query).get("job_id", [""])[-1]
                snapshot = jobs.snapshot(job_id)
                if snapshot is None:
                    self._send_json({"error": "実行ジョブが見つかりません。"}, status=404)
                    return
                self._send_json(snapshot)
                return
            if parsed.path == "/xai-api-key-status":
                if not self._is_authorized(parsed.query):
                    self._send_json({"error": "Forbidden"}, status=403)
                    return
                self._send_json({"saved": bool(key_loader().strip())})
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
            if parsed.path == "/choose-project-directory":
                try:
                    selected_path = directory_picker(self._project_directory_current_path())
                    if selected_path is None:
                        self._send_json({"cancelled": True})
                    else:
                        self._send_json({"path": str(selected_path)})
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=400)
                return
            if parsed.path == "/save-xai-api-key":
                try:
                    payload = self._json_body()
                    key_saver(str(payload.get("xai_api_key", "")))
                    self._send_json({"saved": True})
                except Exception as exc:
                    self._send_json({"error": _friendly_error_message(str(exc))}, status=400)
                return
            if parsed.path == "/delete-xai-api-key":
                try:
                    key_deleter()
                    self._send_json({"deleted": True, "saved": False})
                except Exception as exc:
                    self._send_json({"error": _friendly_error_message(str(exc))}, status=400)
                return
            if parsed.path != "/run":
                self._send_text("Forbidden\n", status=403, content_type="text/plain; charset=utf-8")
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            form = {key: values[-1] for key, values in parse_qs(body, keep_blank_values=True).items()}
            render_defaults = _merge_submitted_form_defaults(defaults, form)
            if self._accepts_json():
                try:
                    snapshot = jobs.start(form)
                    payload = dict(snapshot)
                    payload["status_url"] = f"/run-status?key={quote(access_key)}&job_id={quote(str(snapshot['job_id']))}"
                    self._send_json(payload, status=202)
                except Exception as exc:  # pragma: no cover - defensive server boundary
                    self._send_json({"error": _friendly_error_message(str(exc))}, status=400)
                return
            try:
                result = run_studio_form(
                    form,
                    live_pipeline_runner=live_pipeline_runner,
                    client_factory=client_factory,
                    api_key_loader=key_loader,
                )
                self._send_text(
                    render_studio_home(render_defaults, access_key, last_result=result),
                    content_type="text/html; charset=utf-8",
                )
            except Exception as exc:  # pragma: no cover - defensive server boundary
                self._send_text(
                    render_studio_home(render_defaults, access_key, error=str(exc)),
                    status=400,
                    content_type="text/html; charset=utf-8",
                )

        def log_message(self, format: str, *args: object) -> None:
            return

        def _is_authorized(self, query: str) -> bool:
            return parse_qs(query).get("key", [""])[-1] == access_key

        def _accepts_json(self) -> bool:
            return "application/json" in self.headers.get("Accept", "").lower()

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

        def _project_directory_current_path(self) -> Optional[str]:
            payload = self._json_body()
            if not isinstance(payload, Mapping):
                return None
            current_path = payload.get("current_path")
            if current_path is None:
                return None
            return str(current_path)

        def _json_body(self) -> Mapping[str, object]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            return payload if isinstance(payload, Mapping) else {}

        def _send_json(self, payload: Mapping[str, object], status: int = 200) -> None:
            self._send_text(json.dumps(payload, indent=2) + "\n", status=status, content_type="application/json")

        def _send_text(self, text: str, status: int = 200, content_type: str = "text/plain") -> None:
            encoded = text.encode("utf-8")
            try:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            except BrokenPipeError:
                return

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


def _keep_only_final_mp4(project_dir: Path, summary: Mapping[str, Any], overwrite: bool = False) -> dict:
    clean_summary = dict(summary)
    if not bool(clean_summary.get("final_output_exists", False)):
        return clean_summary
    project = Path(project_dir)
    final_output = Path(str(clean_summary.get("output_mp4", "")))
    if not final_output.exists() or final_output.suffix.lower() != ".mp4":
        return clean_summary
    if not _path_is_inside(project, final_output):
        return clean_summary

    destination = project / final_output.name
    if final_output.resolve(strict=False) != destination.resolve(strict=False):
        if destination.exists() and overwrite:
            destination.unlink()
        elif destination.exists():
            destination = _unique_final_mp4_path(destination)
        shutil.copy2(final_output, destination)

    for relative_path in GENERATED_PROJECT_ARTIFACTS:
        generated_path = project / relative_path
        if generated_path.resolve(strict=False) == destination.resolve(strict=False):
            continue
        _remove_generated_artifact(project, generated_path)
    for stale_mp4 in project.glob("dubbed.*.mp4"):
        if stale_mp4.resolve(strict=False) == destination.resolve(strict=False):
            continue
        _remove_generated_artifact(project, stale_mp4)

    clean_summary["output_mp4"] = str(destination)
    clean_summary["validation_report"] = ""
    clean_summary["clean_output"] = True
    return clean_summary


def _unique_final_mp4_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 10000):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError("完成MP4の保存先ファイル名を確保できませんでした。")


def _remove_generated_artifact(project_dir: Path, path: Path) -> None:
    if not path.exists():
        return
    if not _path_is_inside(project_dir, path):
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _path_is_inside(project_dir: Path, path: Path) -> bool:
    project_root = project_dir.resolve(strict=False)
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(project_root)
    except ValueError:
        return False
    return True


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


def _public_job_snapshot(job: Mapping[str, Any]) -> dict:
    status = str(job.get("status", "queued"))
    result = job.get("result")
    payload = {
        "job_id": str(job.get("job_id", "")),
        "status": status,
        "message": str(job.get("message", "")),
        "poll_ms": 1000,
        "stage_statuses": _job_stage_statuses(job),
    }
    if status == "complete" and isinstance(result, Mapping):
        payload["result"] = dict(result)
    if status == "failed":
        payload["error"] = str(job.get("error") or "実行に失敗しました。")
    return payload


def _job_stage_statuses(job: Mapping[str, Any]) -> list:
    status = str(job.get("status", "queued"))
    result = job.get("result")
    if status == "complete" and isinstance(result, Mapping):
        stages = result.get("stage_statuses")
        if isinstance(stages, Sequence):
            return [_label_stage_status(stage) for stage in stages if isinstance(stage, Mapping)]
    return _estimated_progress_stage_statuses(
        started_at=float(job.get("started_at", time.monotonic())),
        job_status=status,
        failed_stage=job.get("failed_stage"),
    )


def _initial_progress_stage_statuses() -> list:
    return [
        {
            "stage": stage,
            "label": STUDIO_STAGE_LABELS.get(stage, stage),
            "status": "running" if index == 0 else "pending",
        }
        for index, stage in enumerate(STUDIO_STAGES)
    ]


def _estimated_progress_stage_statuses(started_at: float, job_status: str, failed_stage: object = None) -> list:
    if job_status == "queued":
        active_index = 0
    else:
        active_index = _estimated_active_stage_index(started_at)
    failed_index = int(failed_stage) if isinstance(failed_stage, int) else active_index
    statuses = []
    for index, stage in enumerate(STUDIO_STAGES):
        if job_status == "failed" and index == failed_index:
            status = "failed"
        elif index < active_index or (job_status == "failed" and index < failed_index):
            status = "complete"
        elif index == active_index and job_status in {"queued", "running"}:
            status = "running"
        else:
            status = "pending"
        statuses.append({"stage": stage, "label": STUDIO_STAGE_LABELS.get(stage, stage), "status": status})
    return statuses


def _estimated_active_stage_index(started_at: float) -> int:
    elapsed = max(0.0, time.monotonic() - started_at)
    return min(int(elapsed / STUDIO_STAGE_ESTIMATE_SECONDS), len(STUDIO_STAGES) - 1)


def _label_stage_status(stage: Mapping[str, object]) -> dict:
    stage_name = str(stage.get("stage", "unknown"))
    return {
        "stage": stage_name,
        "label": STUDIO_STAGE_LABELS.get(stage_name, stage_name),
        "status": str(stage.get("status", "unknown")),
    }


def _render_result(result: Mapping[str, object]) -> str:
    stages = result.get("stage_statuses", [])
    rows = "\n".join(
        f"<li><strong>{escape(str(stage.get('stage', 'unknown')))}</strong>: {escape(str(stage.get('status', 'unknown')))}</li>"
        for stage in stages
        if isinstance(stage, Mapping)
    )
    validation_report = str(result.get("validation_report", ""))
    validation_html = (
        f'  <p>検証レポート: <code>{escape(validation_report)}</code></p>\n'
        if validation_report
        else ""
    )
    return f"""<section class="result">
  <h2>実行結果</h2>
  <p>ステータス: <strong>{escape(str(result.get('status', 'unknown')))}</strong></p>
  <p>出力MP4: <code>{escape(str(result.get('output_mp4', 'output/dubbed.ja.mp4')))}</code></p>
{validation_html.rstrip()}
  <ul>{rows}</ul>
</section>"""


def _render_error(error: str) -> str:
    message = _friendly_error_message(error)
    return f"""<section class="error">
  <h2>エラー</h2>
  <p>{escape(message)}</p>
</section>"""


def _friendly_error_message(error: str) -> str:
    raw_error = str(error)
    normalized = raw_error.lower()
    if "refusing to overwrite existing artifact" in normalized:
        return "出力先に既存ファイルがあります。同じ出力先を再実行する場合は「同じ出力先を再実行する」をONにしてください。"
    if "source video was not found" in normalized:
        return "ソース動画が見つかりません。File openで動画を選択してください。"
    if "incorrect api key" in normalized:
        return "xAI API Keyが正しくありません。設定を開いてAPI Keyを確認してください。"
    if "xai_api_key is required" in normalized:
        return "xAI API Keyを入力してください。設定を開いてAPI Keyを入力してください。"
    if "xai request failed" in normalized:
        return "xAI APIの呼び出しに失敗しました。API Key、モデル名、ネットワーク状態を確認してください。"
    return raw_error


def _render_empty_result() -> str:
    return ""


def _merge_submitted_form_defaults(defaults: Mapping[str, object], form: Mapping[str, object]) -> dict:
    merged = dict(defaults)
    for key in (
        "subtitle_output",
        "video",
        "project",
        "source_lang",
        "target_lang",
        "voice",
        "xai_base_url",
        "xai_text_model",
    ):
        if key in form:
            merged[key] = str(form[key])
    for key in ("execute_ffmpeg", "overwrite", "clean_output"):
        merged[key] = _form_bool(form, key)
    return merged


def _default(defaults: Mapping[str, object], key: str, fallback: str = "") -> str:
    return escape(str(defaults.get(key, fallback)), quote=True)


def _checked(defaults: Mapping[str, object], key: str, default: bool = False) -> str:
    if key not in defaults:
        return " checked" if default else ""
    return " checked" if _form_bool(defaults, key) else ""


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


def _render_target_language_options(selected_language: str) -> str:
    labels = {
        "ja": "日本語",
        "en": "英語",
    }
    selected = selected_language if selected_language in labels else "ja"
    return "\n          ".join(
        f'<option value="{escape(language, quote=True)}"{" selected" if language == selected else ""}>'
        f"{escape(label)}</option>"
        for language, label in labels.items()
    )


def _voice_gender_label(value: str) -> str:
    return {
        "female": "女性",
        "male": "男性",
        "neutral": "中性",
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
