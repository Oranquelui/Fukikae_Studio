# FukiKae Studio PRD

## Versionアップ方針: アプリ構成

FukiKae Studioは、当面はPython実装の処理エンジンを維持する。

理由:

- 重い処理の中心はxAI STT、Grok、xAI TTSのAPI待ち時間とFFmpegレンダーであり、Python自体の実行速度は体感時間の主要ボトルネックではない。
- 既存のPython実装には、言語切り替え、字幕生成、FFmpegコマンド生成、macOS Keychain、進捗UI、テストが積み上がっている。
- 全面C++ / C#移植は、現時点では速度改善よりも開発速度低下、配布複雑化、回帰リスクの方が大きい。

## v0.3方針: URL Import + Speaker Tracks

2026-06-26時点の次リリース方針は、`v0.3: URL Import + Speaker Tracks`とする。

FukiKae Studioの次の価値は、単なるローカル動画変換ではなく、次の一連の流れをローカルアプリとして成立させることに置く。

```text
動画URLまたはローカル動画
→ 権利確認つきローカル取り込み
→ xAI STT diarization
→ Grok翻訳 / 吹き替え台本
→ 話者ごとのVoice / 字幕色
→ MP4 + SRT / VTT + 生成メタデータ
```

### 背景

調査では、動画吹き替えユーザーの強い要望は大きく二つに分かれる。

1. 動画素材をまず簡単に取り込みたい。
2. 二人以上が話す動画で、話者ごとの声・字幕・編集単位を保ちたい。

X / Threads / YouTubeなどの動画を保存してから字幕・吹き替えに回したい需要は明確にある。一方で、FukiKae Studioを単なる動画ダウンローダーとして位置づけると、各プラットフォームの利用規約、著作権、ログイン回避、バルク取得のリスクが大きい。

そのためv0.3では、主語を「ダウンロード」ではなく「権利を持つ、または利用許可のある動画素材をローカルに取り込む」に置く。URL入力は便利な入口として提供するが、ログイン突破、Cookie取り込み、年齢制限回避、プロフィール単位の一括取得、第三者コンテンツの再配布支援はしない。

複数話者については、既存のxAI STT呼び出しですでに`diarize=true`を使い、正規化セグメントにも`speaker`を保持している。v0.3ではこの既存データをTTS、字幕、UIまで通し、`SPEAKER_00`、`SPEAKER_01`、`SPEAKER_02`ごとにVoiceと字幕色を割り当てられるようにする。

### v0.3 MVP範囲

v0.3で必ず入れるもの:

- URL入力またはローカルファイル入力を選べる。
- URL入力時は、権利確認チェックを必須にする。
- URL取り込みは単一URLのみ対応する。
- 取り込み後の動画は既存のローカルパイプラインへ渡す。
- xAI STTの話者ラベルを維持する。
- 最大3話者のVoice割り当てを指定できる。
- 最大3話者の字幕色を指定できる。
- TTS manifest、字幕関連manifest、最終run summaryに話者設定を残す。
- MP4、SRT、VTTを引き続き出力する。

v0.3では入れないもの:

- X / Threads / YouTubeなどへのログイン代行。
- Cookieやブラウザセッションを使った非公開・制限付き動画の取得。
- プロフィール、タイムライン、ブックマーク、いいね、メディアタブの一括取得。
- DRM、課金、年齢制限、地域制限、削除済みコンテンツの回避。
- 自動リップシンク生成。
- 本格的なタイムライン編集UI。
- 声のクローン作成。v0.3では既存のxAI Voiceを話者ごとに割り当てる。

### 優先順位

1. **URL Import**: 既存の「ローカルファイルを選ぶ」入口に加えて、単一URLからローカル素材を作る。これはユーザーの最初の詰まりを解消する。
2. **Speaker Voice Mapping**: `speaker`ごとにTTS voiceを選べるようにする。会話動画の品質差に直結する。
3. **Speaker Subtitle Color**: 焼き込み字幕とmanifestで話者色を扱う。二人以上の会話を視覚的に追いやすくする。
4. **Transcript Correction / Segment Retry**: v0.3の後続候補。生成結果の最後の品質調整として、セグメント単位のテキスト修正とTTS再生成を入れる。
5. **YouTube Multi-language Output Support**: v0.3の後続候補。音声トラック単体、タイトル/説明文メモ、アップロード用チェックリストを追加する。

### 成功条件

v0.3は次を満たせば成功とする。

- 初回ユーザーが、ローカル動画または許可済みURLから、10分以内に吹き替えMP4生成を開始できる。
- 二人または三人の会話動画で、話者ごとに異なるVoiceを割り当てられる。
- 焼き込み字幕で話者ごとの色が区別できる。
- 生成物のmanifestから、各セグメントの`speaker`、`voice`、字幕色、元URL由来かローカル由来かを追跡できる。
- URL取り込みが失敗した場合、規約・権利・非対応サイト・yt-dlp未導入のどれに近い失敗かをユーザーが理解できる。

### 実装計画

v0.3の具体タスクは`docs/superpowers/plans/2026-06-26-v0.3-url-import-speaker-tracks.md`に置く。

## 優先する改善

1. Pythonコアは維持する。
2. Macユーザー体験を優先して改善する。
3. 配布版ではPython CLIを隠し、`.app` / DMG / 署名 / notarization / auto-updateを整える。
4. FFmpeg / ffprobeはDMG版へ同梱し、普通のユーザーにHomebrew導入を要求しない。
5. 将来、よりMacアプリらしい体験が必要になった場合は、Swift / SwiftUIの薄い外側を作り、内部のPythonローカル処理エンジンを呼び出す。

## 採用しない方針

- 現時点ではC++への全面移植はしない。
- 現時点ではC# / .NETへの全面移植はしない。
- 独自動画処理エンジンは作らず、FFmpegを使い続ける。
- 一般ユーザー向けの主導線としてHomebrewインストールを要求しない。

## 将来再検討する条件

次のどれかが明確になった場合だけ、部分的なネイティブ化や別言語化を再検討する。

- Python側の処理が実測で主要ボトルネックになった。
- リアルタイム音声処理や低レイテンシ編集など、Pythonでは不利な機能を入れる。
- App Store配布、より深いmacOS統合、ネイティブWebView体験が重要になった。
- 保守対象ユーザーが増え、Python/PyInstaller配布よりSwift外側の方が安定すると判断できる。

## 現時点の推奨アーキテクチャ

```text
Swift / SwiftUI wrapper, optional future
        |
        v
Local Web UI / local app launcher
        |
        v
Python processing engine
        |
        +-- xAI STT / Grok / xAI TTS
        +-- FFmpeg / ffprobe
        +-- subtitles and MP4 assembly
```

まずはPython処理エンジンを維持し、Macアプリとしての初回体験、配布、署名、同梱依存、エラー案内を磨く。
