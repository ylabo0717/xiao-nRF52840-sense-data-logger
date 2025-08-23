# Oscilloscope Visualization Design Review

## 目的

- `oscilloscope-visualization-design.md` の内容を現状実装と突き合わせてレビューし、リスク/不整合/改善提案を明確化。

## 要約（TL;DR）

- 単位不一致（Accel: g? vs m/s², Gyro: deg/s vs rad/s）が最大の手戻り要因。先に方針確定が必要。
- Audio RMS のスケールと欠損値（-1）の扱いが未定義。描画・スケール・凡例に反映を。
- 受信は async（bleak）で Dash は同期。ブリッジ（deque+RLock/停止・再接続手順）を設計に明記。
- 更新方式は extendData+デシメーションで軽量化。ポーリング15Hzとレイテンシ<100msの整合を再定義。

## 主な指摘事項

### 1) データ仕様の不一致・不足

- 加速度/ジャイロの単位
  - ドキュメント: Accel m/s², Gyro rad/s。
  - 実装（sender）: `LSM6DS3` 出力は Accel=g（多くのSeeed実装既定）、Gyro=deg/s（変数名 `*_dps`）。CSVは変換なし。
  - 提案: どちらかに統一。
    - 変換して出力: g→m/s²(×9.80665), deg/s→rad/s(×π/180)；または
    - ドキュメント側を g / deg/s に修正しUIラベルも合わせる。
- Audio RMS
  - 実装: 16bit PDM生値のRMS。未充足時は `-1.0` を出力。
  - ドキュメント: 欠損値/レンジ/正規化の記述なし（UIモックの0.1/0.05は実スケールと不整合）。
  - 提案: 欠損値 `-1` は非表示orギャップ扱い。スケールは「そのまま（16bitスケール）」か「FS=32768で0〜1に正規化」のどちらかを明記。
- タイムスタンプ
  - `millis` はデバイス起点の相対時刻。再起動/オーバーフロー（約49.7日）で不連続あり。
  - 提案: 不連続検出時の起点リセット方針を明記（例: 大きな逆行/ジャンプでウィンドウ再基準）。

### 2) アーキテクチャの明確化

- DataSource 抽象
  - ドキュメント: `DataSource` 抽象クラス。
  - 実装（receiver）: `stream_rows()` の async generator（クラス化されていない）。
  - 提案: `BleDataSource(DataSource)` の薄いラッパーを追加し `start/stop/is_connected/get_data_stream` を提供。
- async↔Dash ブリッジ
  - 提案: バックグラウンドスレッドで asyncio ループを起動→`collections.deque(maxlen=N)+threading.RLock` に投入。
  - 停止・例外時のハンドリング（タスクキャンセル、センチネル投入、再接続ポリシー）を明記。

### 3) パフォーマンス/可視化

- 更新方式
  - 提案: Plotly `extendData`（必要最小の增分更新）＋ `uirevision` でユーザ操作を保持。
- デシメーション
  - 表示窓に応じた可変間引き（5sは全点、30/60sは等間引き）。NumPyで高速スライス。
- バッファ/窓
  - 既定 `maxlen=1000` は25Hzで約40s。60s窓対応なら `maxlen≈1500@25Hz` に自動調整。
- レイテンシ目標
  - `BLE 100ms周期` + `Dash 15Hz` では最悪>100msになりうる。
  - 提案: 目標を「中央値<100ms/最大<200ms」に再定義、またはクライアント側間隔短縮（負荷と相談）。

### 4) UI/設定

- 軸/レイアウト
  - IMU 3軸のy共有/リンクx軸、Audioは正規化or目盛注記。
- 設定永続化
  - 時間窓・オートスケール・表示選択を `dcc.Store` やローカルストレージに保存。
- エクスポート
  - ヘッダ付きCSV、現ウィンドウ/全バッファ選択、PC時刻メタ付与。

### 5) セキュリティ/運用

- ローカルバインド（127.0.0.1）を明記。外部ライブラリの利用（Dash/bleak）は「外部依存なし」の表現を調整。
- ログレベル/ローテーション、BLE切断時の再試行間隔/上限の仕様化。

### 6) 命名

- ディレクトリ綴り: `reciever` → `receiver`。リネームは将来作業として注記。

## ドキュメント反映の具体修正案

- Current Data Structure
  - 単位の確定（変換する/しないの選択と根拠）。
  - AudioRMS: 欠損値=-1、スケール（生値or正規化）の明記。
- Performance Requirements
  - バッファサイズ=時間窓×サンプルレートで算出。レイテンシ目標の再定義。
- System/Thread Architecture
  - async受信→スレッドセーフdequeブリッジ、停止・再接続の状態遷移図を追記。
- Web Interface
  - `extendData` 採用、`uirevision`、デシメーション戦略、可視プロットのみ更新（Lazy）。

## 次アクション（優先度順）

1. 単位（Accel/Gyro）と Audio RMS のスケール/欠損ポリシーを確定。
2. 設計ドキュメントへ上記を反映。UIラベル/凡例も準備。
3. `BleDataSource` ラッパー＋`deque` バッファ層を実装（MockDataSourceも同時に）。
4. Dash最小骨格（extendData、リンクx軸、uirevision）でスモーク動作。
5. デシメーションと時間窓に応じた `maxlen` 自動調整。
6. エクスポート/設定永続化は小粒で追加。

## 備考（実装との整合）

- CSV項目順は sender/receiver と一致（`millis,ax,ay,az,gx,gy,gz,tempC,audioRMS`）。
- `audioRMS=-1` の欠損値は receiver 側で「スキップ可能」な設計になっている（可視化側の扱いを要定義）。
