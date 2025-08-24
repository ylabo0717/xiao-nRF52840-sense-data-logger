# Data Recorder 設計レビュー

最終更新: 2025-08-24

## 要約（Executive Summary）

- 全体方針（採取スレッドと記録処理の分離、UIからの制御、CSVエクスポート）は妥当で、段階的導入プランも現実的。
- 現状コード（`DataBuffer`/Dash UI/受信スレッド）と整合させるには、以下の差分を解消する必要がある。
  - DataBuffer に「インデックス追跡 API（get_samples_since_index）」が未実装（deque＋RLock 構成）。
  - モニタリング/ファイル書き出しの実装は asyncio 前提だが、既存のデータ採取は「別スレッド＋新規イベントループ」を使う構造で、イベントループが複数存在する設計になるリスク。
  - `RecordingSession` が `CSVWriter` と `AsyncFileWriter` を混用しており命名/責務が不整合。
- 実装簡素化と堅牢性を優先して、記録は「専用ワーカースレッド＋同期I/O（バッファリング）＋スレッドセーフキュー」の選択を推奨。必要なら fsync をオプション化。Python 3.12 で十分高性能。
- バックプレッシャ（記録側が遅い時）のポリシー、メタデータの一貫性（平均サンプルレート計測等）、CSVヘッダ互換の明文化を追記すると完成度が上がる。

---

## 現状コードとの整合性レビュー

対象ファイル:

- `reciever/src/xiao_nrf52840_sense_reciever/ble_receiver.py`
  - `DataBuffer`: `deque(maxlen)`＋`RLock`、`append()/get_recent()/get_all()`、`BufferStats` は直近間隔から瞬間レートを算出。
  - `ImuRow` 定義は設計と一致（millis, ax..audioRMS）。
- `reciever/src/.../oscilloscope/app.py`
  - データ採取は別スレッドで `asyncio` ループを立てて実行。UI は Dash のコールバックで `DataBuffer` を参照。
- 差分/ギャップ
  - 設計の「lock-free」「index-based access（get_samples_since_index）」が未提供。deque では古いデータが自然に消えるため、外部に単調増加のグローバルインデックスを露出する仕掛けが必要。
  - 設計では Recorder 側も asyncio ループを持つ想定（`BufferMonitor`, `AsyncFileWriter`）。現状アプリは既に「採取側に独自ループ」を持つため、ループ多重化で煩雑化・デバッグ難化の懸念。

結論: Recorder はスレッドベースに寄せ、UI/採取スレッドとのインターフェースを最小限に保つのが無難。

---

## 設計の強み

- 収集系と記録系の明確な分離（UI も非同期で参照）。
- バッチ書き出し・メタデータ併設など、長時間運用を意識した設計。
- リスク評価と段階導入（Phase 1→3）の粒度が適切。

## 改善提案（重要度順）

1) ループ構成の簡素化（推奨・高）

- 現提案の `BufferMonitor(async)`＋`AsyncFileWriter` は、既存の採取スレッド（独自イベントループ）と併用するとイベントループが2つ以上になり、停止・例外ハンドリング・終了順序が複雑化。
- 代替案（推奨）: 「録音ワーカースレッド」を1本立て、`queue.Queue` で `ImuRow` または事前整形済みCSV行をバッチ転送。ワーカー内は標準の `csv`＋`io.TextIOWrapper(buffered)` で同期書込み、一定件数/秒で flush。UI/採取とは完全分離でシンプル。

1) DataBuffer のインデックスAPI設計（高）

- 必要な契約（Contract）
  - 入力: last_index（呼び出し側が保持）
  - 出力: (rows: List[ImuRow], next_index: int, dropped: bool)
  - 仕様: last_index より古いデータが deque から落ちていた場合は `dropped=True` で「現存する最古から」を返す。これによりロスを検知可能。
- 実装案
  - `DataBuffer` に単調増加の `write_index` を導入。`append` 時に `(row, write_index)` を連動管理し、先頭要素の `base_index` も保持。
  - 取得は `last_index < base_index` の場合に `dropped=True` とし、`list(self._buffer)` のスライスから該当分を返す（O(n) コピーは発生するが 25–100Hz かつバッチで十分）。
  - ロックは短時間（コピーのみ）で、採取スレッドはほぼ非ブロッキングを維持。

1) バックプレッシャと安全策（高）

- 記録キュー長がしきい値超過時の方針を定義（例: ドロップ/停止/圧縮/警告）。初期は「古い記録バッチからドロップ＋UI警告」を推奨。
- ディスク空き監視（`shutil.disk_usage`）を開始前と定期的に実行し、閾値（例: 残り < 500MB）で停止/警告。

1) 命名/責務の整理（中）

- `RecordingSession.file_writer: Optional[CSVWriter]` と `AsyncFileWriter` が混在。どちらかに統一（推奨: `RecordFileWriter`）し、同期/非同期の戦略は内部実装で隠蔽。

1) メタデータの正確化（中）

- サンプルレートは瞬間値ではなく、セッション期間での平均/標準偏差を算出（`total_samples / duration`）。
- タイムゾーンは `datetime.now(timezone.utc).astimezone()` でISO 8601に統一（現仕様OKだが実装で徹底）。

1) CSV フォーマット互換性の明記（中）

- 既存の `print_stream` と完全一致する列順・小数点桁・改行コード（LF）を明確化。ヘッダコメント行の有無をオプション化（他ツール連携を考慮）。

1) テスト容易性（中）

- `MockDataSource` を使った E2E テストケース（1分録画→CSV行数・メタ一致）を Phase 1 で用意。

---

## 具体アーキテクチャ提案（実装簡素版）

- 構成
  - RecorderManager（UI から start/stop/status）
  - RecordingWorkerThread（専用スレッド）
  - RecordFileWriter（同期I/O、内部バッファリングと定期 flush）
  - DataBuffer Indexed Access（上記 API）
- データ経路

 1) 採取スレッド: `DataBuffer.append(row)`（最優先）

 2) Recorder: タイマで 10–20ms ごとに `get_since_index(last_index)` で新着を取得

 3) Writer: バッチ（例: 25件≒1秒 or N行）で書込み＋条件付き flush（N行またはT秒）

- 期待効果
  - イベントループの多重管理を回避、停止順序が単純
  - Python 標準I/Oでも 25–100Hz 相当は十分

補足: 将来 1kHz 級などに拡張する場合のみ `aiofiles` など非同期I/Oやmmap等を再検討。

---

## API スケッチ（提案）

- DataBuffer 追加
  - `def get_since_index(self, last_index: int) -> tuple[list[ImuRow], int, bool]`
  - 内部状態: `self._write_index: int`, `self._base_index: int`, `self._buffer: deque[ImuRow]`
- RecorderManager
  - `start(prefix: str|None=None, duration: float|None=None) -> SessionInfo`
  - `stop() -> SessionInfo`
  - `status() -> RecordingStatus`（is_recording, duration, samples, filename, queue_len など）
- RecordFileWriter
  - `append_rows(rows: list[ImuRow])`
  - `flush(force_fsync: bool=False)`
  - `close()`（close 時に .meta.json を確定書込み）

エラーモード: ディスク枯渇、書込み失敗、バッファオーバーラン、ユーザ停止、強制終了（SIGINT）。

---

## ファイル/フォルダ仕様レビュー

- ディレクトリ: `recordings/YYYY-MM-DD/` は賛成。OS非依存の `Path` を使用。
- ファイル名: `sensor_data_YYYYMMDD_HHMMSS.csv`＋任意 prefix。併設 `.meta.json` は同名で拡張子差し替え。
- CSV ヘッダ: コメント行の先頭 `#` は解析系によっては嫌うため、`--with-comment-header` のようなオプション化が実務的。
- 改行: LF 固定。エンコーディング: UTF-8（BOMなし）。

---

## UI 統合（Dash 3.x / Plotly 6.x 前提）

- 収録パネル: Start/Stop ボタン、状態表示（録音/停止/警告/エラー）、経過時間/件数/平均Hz。
- ダウンロード: 録音完了後に `dcc.Download` でファイルを提供（完了前は不可）。
- 注意: 長時間ウォッチでの `Interval` は 250–1000ms 程度に、UI更新計算コストを抑制。

---

## テスト計画（補強）

- 単体
  - DataBuffer index API: ドロップ検知、境界条件。
  - RecordFileWriter: バッチ/flush/クラッシュ復旧（close 未到達時のファイル検査）。
- 結合
  - MockDataSource で 60 秒録音→行数≒サンプル数、メタの平均Hzが期待範囲（例: 24–26Hz）。
  - バックプレッシャ試験: Writer を意図的に遅延させ、ドロップ発生と UI 警告を検証。
- パフォーマンス
  - 1 時間録音でメモリ定常（<10MB増）を確認。CSV 書込みスループット（>10k 行/秒相当）を測定。

受け入れ基準（例）

- データロス 0%（キュー溢れ時を除き）、UI フリーズ 0、1 時間連続記録で安定、CSV/メタ整合、停止/復帰が確実。

---

## オープンクエスチョン

- コメントヘッダ行は常時付与か、オプションか。
- 録音中のリアルタイム「部分ダウンロード」を許可するか（基本は非推奨）。
- バックプレッシャ時のデフォルト方針（停止/ドロップ/自動ファイルローテーション）。
- `.meta.json` の項目固定か拡張可能か（将来センサー追加時）。

---

## 次アクション（Phase 1 実装指針）

1. `DataBuffer` に index API を追加（上記契約で）。
2. `reciever/src/.../oscilloscope/recorder/` を新設し、`RecorderManager` と `RecordingWorker` を実装。
3. Writer は同期I/O版で先行実装（flush 方針: 1秒 or 100行）。
4. メタ生成とエラー/警告ログ整備（空き容量チェック含む）。
5. MockDataSource での E2E テストを追加。

この方針であれば、既存アーキテクチャに最小の侵襲で安全に録音機能を追加できます。
