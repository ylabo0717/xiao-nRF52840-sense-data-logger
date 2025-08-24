# XIAO nRF52840 Sense データ出力仕様（BLE/CSV）

このドキュメントは、本プロジェクトのファームウェアがBLE経由で出力するCSVデータの仕様を受信側（例: Python + bleak）で実装しやすいようにまとめたものです。

## BLE 接続情報

- デバイス名: `XIAO Sense IMU`
- 役割: Peripheral（本機） - Central（PC/スマホ）が接続
- アドバタイズ: 切断時に自動再開（fast間隔→slow間隔）
- ペアリング/暗号化: なし（平文）

### GATT（NUS 互換）

- Service UUID: `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`
- Characteristics:
  - TX (Notify, Peripheral→Central): `6E400003-B5A3-F393-E0A9-E50E24DCCA9E`
  - RX (Write w/o Response, Central→Peripheral): `6E400002-B5A3-F393-E0A9-E50E24DCCA9E`
- 本ファームはTXでのみ送信。RXは未使用。
- MTU/パケット長: 環境に依存（デフォルト20byte通知）。本ファームは短めのCSV行＋25Hzで運用。

## データ形式（CSV）

- フィールド順（固定、ヘッダ行はBLEでは送信しない）:
  1. `millis` [ms, uint32] 起動からの経過ミリ秒
  2. `ax` [m/s^2, float] 加速度X
  3. `ay` [m/s^2, float] 加速度Y
  4. `az` [m/s^2, float] 加速度Z
  5. `gx` [dps, float] ジャイロX（度/秒）
  6. `gy` [dps, float] ジャイロY
  7. `gz` [dps, float] ジャイロZ
  8. `tempC` [°C, float] IMU内蔵温度
  9. `audioRMS` [counts, float] 直近10ms (160サンプル@16kHz) のPDMサンプルRMS。データ不足時は `-1.0` を出力。

- 値のフォーマット目安: 軸は小数6桁、温度/音声RMSは小数2桁で送出（受信側は自由にパース可能）
- 区切り: カンマ+スペース（`,` と半角スペース）。受信側は空白の有無を許容する実装を推奨。

### 出力例（1行）

```text
123456, 0.012345, 0.067890, 9.812345, 0.123456, -0.234567, 0.345678, 28.15, 42.37
```

## タイミング/同期の扱い

- IMUの読み取りは約100Hz。
- `audioRMS` はPDMリングバッファから直近10ms分（160サンプル@16kHz）を消費して算出した音量指標。
- 1行のCSVは「同時刻付近のIMUサンプル」と「直近10msの音声RMS」を同梱する“粗同期”。厳密なサンプル同期ではありません。
- より厳密に扱いたい場合:
  - 受信側で `millis` による整列を行う
  - `audioRMS=-1.0` 行は欠損として扱う

## 異常/例外ケース

- `audioRMS = -1.0`: PDMデータ不足（起動直後/接続直後など）。
- IMU非検出時はBLEではデータを送らず、USBシリアル側でスキャンログを出力。
- 切断時: アドバタイズ再開。再接続で送信再開。

## PC側実装ヒント（Python + bleak）

- 必要パッケージ: `bleak`（Windows 10+ のBLEスタックが必要）
- 流れ:
  1. デバイス名またはService UUIDでスキャン→アドレス取得
  2. 接続後、TX特性（Notify）を購読
  3. 受信コールバックで `bytes` → UTF-8文字列に変換、`\r\n`区切りで行を組み立て、各行をカンマ区切りでパース
  4. フィールドを型変換（`int(millis)`, `float(ax)` 等）
- 断片化対策: 通知境界で行が分割される場合があるため、アプリ側で受信バッファに蓄積して改行区切りで組み立てること。

### 参考UUID（定数）

```python
NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_CHAR = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # Notify
NUS_RX_CHAR = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Write (unused)
```

## 変更履歴

- v1.0: 初版（IMU + PDM RMS のCSV、BLE 25Hz）

---

補足: USBシリアル側では起動時に以下のヘッダを1回だけ表示します（BLEでは送信しません）。

```text
Output: millis,ax,ay,az,gx,gy,gz,tempC,audioRMS
```
