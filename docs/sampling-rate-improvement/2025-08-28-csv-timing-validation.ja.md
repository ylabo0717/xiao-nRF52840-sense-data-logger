# 2025-08-28 記録CSVのタイミング検証レポート

- 対象ファイル: `receiver/recordings/2025-08-28/sensor_data_20250828_150907.csv`
- 目的: 送信間隔を 40ms（目標 ~25Hz）に設定した後、受信・記録された CSV の実効レートとジッタを確認する。

## 検証手順（再現可能）

1. 解析スクリプト（PowerShell）

	- 位置: `receiver/scripts/analyze_csv_timing.ps1`
	- 機能: `millis` 列の差分（ms）から平均・分位点・実効レート（Hz）を算出し、しきい値を超えるジッタの割合を出力。

2. 実行コマンド（PowerShell）

	```powershell
	pwsh -NoProfile -File "c:\\Users\\0145201616\\sandbox\\xiao-nRF52840-sense-data-logger\\receiver\\scripts\\analyze_csv_timing.ps1" "c:\\Users\\0145201616\\sandbox\\xiao-nRF52840-sense-data-logger\\receiver\\recordings\\2025-08-28\\sensor_data_20250828_150907.csv"
	```

## 実行結果（要約）

- rows=358, intervals=357, duration_ms=17732
- delta_ms: avg=49.669, min=42, p50=44, p90=59, p95=77, p99=165, max=167
- rate_hz: by_avg=20.133, by_span=20.133
- jitter: over_88ms=12 (3.36% of intervals)

## 解釈

- 単位の確認: 送信側ファームは `formatCsvLine(... millis(), ...)` で `millis()` をそのまま出力しており、単位はミリ秒（ms）で正しい（`sender/src/main.cpp`）。
- 間隔の分布: 中央値が約 44ms、平均が約 49.7ms。ときどき 2〜4 倍の間隔（~59/77/165ms）が混在し、Windows 中央側の接続イベント間隔・スケジューリングの影響が支配的。
- 実効レート: 平均差分ベース・スパンベースともに ~20.1Hz。送信側を 40ms にしても、中央側が ~45–50ms 程度で動いていると 1 イベント=1行の現状では ~20Hz 近傍に頭打ちとなる。

## 結論と次の一手（インターフェースは維持）

- A2（バッチ送信）: 1 通知/接続イベントで CSV を 2 行（LF 区切り）まとめて送る。受信側は改修不要（LF 区切りで既に行分割）。これにより、接続イベント間隔が ~50ms でも内容レートは ~40Hz 相当まで引き上げ可能。
- A1 間隔微調整のみでは中央側の接続間隔を超えられないため、目標 ~25Hz 以上の「内容レート」達成にはバッチ化が現実的。
- 参考: 中央（OS/ドライバ）由来の接続間隔交渉は環境差が大きく、送信側のみで制御しきれないことがある。

## 付録: スクリプト出力ログ

```text
file="c:\\Users\\0145201616\\sandbox\\xiao-nRF52840-sense-data-logger\\receiver\\recordings\\2025-08-28\\sensor_data_20250828_150907.csv" rows=358 intervals=357 duration_ms=17732

delta_ms: avg=49.669 min=42 p50=44 p90=59 p95=77 p99=165 max=167

rate_hz: by_avg=20.133 by_span=20.133

jitter: over_88ms=12 (3.36% of intervals)
```

---

補足: 送信側ファームの該当箇所（`sender/src/main.cpp`）

- 送信間隔の定数: `static const uint32_t BLE_TX_INTERVAL_MS  = 40;`
- CSV の `millis` 出力: `formatCsvLine(line, sizeof(line), (unsigned long)millis(), ...)`

今後は A2 バッチ送信を実装し、同様の手順で再計測・ドキュメント化します。
