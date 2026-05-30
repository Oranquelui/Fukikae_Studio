# FukiKae Studio

FukiKae Studioは、ローカル動画を日本語または英語の吹き替えMP4に変換するツールです。  
外国語動画から日本語吹き替え、日本語動画から英語吹き替えを作れます。  
xAI STT、Grok 4.3、xAI TTS、FFmpegを使い、動画処理は自分のPC上で実行します。

![FukiKae Studio 30秒デモ](docs/assets/fukikae-studio-30s-demo.gif)

## 何ができるか

| 入力 | 出力 |
| --- | --- |
| 外国語動画 | 日本語吹き替え + 日本語字幕 |
| 日本語動画 | 英語吹き替え + 英語字幕 |

- 翻訳先言語を`ja` / `en`から選択できます。
- 字幕は「焼き込み字幕 / ソフト字幕 / 両方」から選べます。
- 完成後はMP4だけを残す設定にできます。
- API Keyは画面へ再表示せず、必要な場合だけmacOS Keychainに保存できます。

![FukiKae Studio ローカルWeb UI](docs/assets/studio-local-web-ui.png)

このリポジトリの配布版は、まず内部beta・個人検証向けです。商用SaaSではなく、アプリ自体は無料です。Live xAIモードを使う場合は、ユーザー自身のxAI API Keyが必要で、発生する費用はxAI APIの従量課金です。

## なぜ作ったのか

動画の吹き替えは、AI SaaSにアップロードすれば簡単に試せます。一方で、ニュース素材、顧客素材、未公開動画、制作途中の素材では、アップロード先、保存期間、再利用、チーム権限、月額費用が気になります。

FukiKae Studioは次の目的で作っています。

- ローカル動画をできるだけ外に出さずに、日本語または英語の吹き替えを作る。
- AI SaaSの月額・クレジット制ではなく、ユーザー自身のxAI API使用量だけで検証できるようにする。
- STT、翻訳、TTS、字幕、最終muxを分解し、どこで失敗したか見えるようにする。
- Grokで翻訳文の長さを調整し、元動画の発話タイミングに近い吹き替えを作る。
- 焼き込み字幕とソフト字幕の両方を比較できるようにする。

## 主な機能

- ローカルWeb UI alphaを起動して、ブラウザから動画を選択できます。
- Live xAIモードで、xAI STT、Grok 4.3、xAI TTSを使った日本語または英語の吹き替えを生成できます。
- Sakura female / Japanese、Ren male / Japanese、Eve / Ara / Rex / Sal / LeoなどのxAI Voiceを選択できます。
- 焼き込み字幕、ソフト字幕、両方の出力を選べます。
- デフォルトでは完成MP4だけをローカルプロジェクトディレクトリに残します。

## 料金の考え方

FukiKae Studio自体は無料です。サーバー利用料、月額利用料、FukiKae側の手数料はありません。

Live xAIモードで必要なのは、ユーザー自身のxAI API Keyです。API費用はxAIから直接請求されます。xAI公式Pricingでは、2026-05-28時点で次の価格が公開されています。

| 項目 | 価格 |
| --- | ---: |
| Grok 4.3 input | $1.25 / 1M tokens |
| Grok 4.3 output | $2.50 / 1M tokens |
| xAI Speech to Text REST | $0.10 / hour |
| xAI Text to Speech | $15.00 / 1M characters |

出典: [xAI Pricing](https://docs.x.ai/developers/pricing)、[xAI Models](https://docs.x.ai/developers/models)

### 目安

10分の一般的なナレーション動画を例にすると、概算は次のようになります。

| 処理 | 仮定 | 概算 |
| --- | --- | ---: |
| STT | 10分 = 0.166時間 | 約$0.017 |
| Grok 4.3 | input 8k tokens / output 6k tokens | 約$0.025 |
| TTS | 日本語3,000から6,000文字 | 約$0.045から$0.090 |
| 合計 | 1回生成、リトライなし | 約$0.09から$0.13 |

60分動画なら、内容量が同程度に比例すると仮定して約$0.54から$0.78程度が一つの目安です。実際の費用は、発話量、翻訳の長さ、リトライ回数、モデル設定、xAI側の最新価格で変わります。

## 必要なもの

- macOSまたはLinux
- Python 3.9以上
- FFmpeg / ffprobe
- xAI API Key（Live xAIモードのみ）

macOSでFFmpegがない場合:

```bash
brew install ffmpeg
```

## インストール

GitHubからcloneします。

```bash
gh repo clone Oranquelui/Fukikae_Studio
cd Fukikae_Studio
```

GitHub CLIを使わない場合:

```bash
git clone https://github.com/Oranquelui/Fukikae_Studio.git
cd Fukikae_Studio
```

Python仮想環境を作ります。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e . pytest
```

動作確認:

```bash
PYTHONPATH=src .venv/bin/python -m pytest
```

## 起動

ローカルWeb UIを起動します。

```bash
PYTHONPATH=src .venv/bin/python -m fukikae_studio studio
```

ターミナルに表示されたURLを開きます。

```text
http://127.0.0.1:8765/?key=...
```

## 使い方

画面で行うこと:

1. `File open`でソース動画を選ぶ。
2. `Directory open`でプロジェクトディレクトリ（出力先）を選ぶ。
3. `設定`を開いてxAI API Keyを入力する。必要なら`API KeyをこのMacに保存`でmacOS Keychainへ保存できます。
4. 元言語と翻訳先言語を選ぶ。日本語動画から英語吹き替えを作る場合は、元言語を`ja`、翻訳先言語を`en`にします。
5. Voiceを選ぶ。英語吹き替えでは`ara`、`rex`、`sal`、`leo`、`eve`などを選べます。
6. 字幕出力を選ぶ。
7. `ローカルFFmpegで最終レンダーを実行`をONにする。
8. `ローカルパイプラインを実行`を押す。

`File open`で選んだ動画は外部にアップロードされません。localhostの`work/studio-uploads/`へローカルコピーされ、そのコピー先パスがフォームへ入ります。
`Directory open`はmacOSのフォルダ選択ダイアログを使い、選んだ出力先パスだけをローカルフォームへ入れます。

`設定を保存`はBase URL、Grokモデル、言語、Voice、字幕出力、チェックボックス設定だけをブラウザに保存します。API Keyはブラウザ保存せず、保存する場合はmacOS Keychainへ入れます。保存済みAPI Keyがある場合、API Key欄が空でもローカル実行時にサーバー側で読み込みます。

## 出力ファイル

デフォルトでは`完成後はMP4だけを残す`がONです。プロジェクトディレクトリ直下に、完成MP4だけが残ります。

| ファイル | 内容 |
| --- | --- |
| `dubbed.ja.burned.mp4` | 焼き込み字幕つきMP4 |
| `dubbed.ja.mp4` | ソフト字幕つきMP4 |
| `dubbed.en.burned.mp4` | 英語の焼き込み字幕つきMP4 |
| `dubbed.en.mp4` | 英語のソフト字幕つきMP4 |

中間artifactを確認したい場合は、`完成後はMP4だけを残す`をOFFにしてください。

## Voice

現在のUIでは次を選べます。

| 表示 | voice_id | language |
| --- | --- | --- |
| Sakura 女性 / 日本語 | `d0cb9ff07d95` | `ja` |
| Ren 男性 / 日本語 | `b1a7441b97a1` | `ja` |
| Eve 女性 / 多言語 | `eve` | `multilingual` |
| Ara 中性 / 多言語 | `ara` | `multilingual` |
| Rex 中性 / 多言語 | `rex` | `multilingual` |
| Sal 中性 / 多言語 | `sal` | `multilingual` |
| Leo 中性 / 多言語 | `leo` | `multilingual` |

## 注意

- このalphaはローカル実行前提です。
- localhost以外へのbindは拒否します。
- API Keyは画面へ再表示しません。
- API Keyを含むファイル、`work/`、`test_temp/`、`.venv/`は配布対象外です。
- 生成結果の品質は、入力音声、STT品質、翻訳長、TTS voice、FFmpeg環境に左右されます。
- xAIの料金とモデル提供状況は変わる可能性があります。最新情報は[xAI Pricing](https://docs.x.ai/developers/pricing)を確認してください。

## 開発者向けドキュメント

- [Solo Local Beta Test](docs/SOLO_BETA_TEST.md)
- [App Shape Research](docs/APP_SHAPE_RESEARCH.md)
- [Provider Policy](docs/PROVIDER_POLICY.md)
- [xAI Endpoint Notes](docs/XAI_ENDPOINT_NOTES.md)
- [Public Sample Runbook](docs/PUBLIC_SAMPLE_RUNBOOK.md)

## ライセンス

FukiKae StudioはMIT Licenseで公開しています。個人利用、改変、再配布、商用利用が可能です。詳しくは[LICENSE](LICENSE)を確認してください。
