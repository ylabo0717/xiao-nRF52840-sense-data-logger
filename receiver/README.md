# XIAO nRF52840 Sense Receiver (BLE/CSV)

このリポジトリは、XIAO nRF52840 Sense が BLE (Nordic UART Service 互換) で送出する CSV テレメトリを PC 側で受信する Python ツールを提供します。`bleak` を用いて Windows の BLE スタック上で動作します。

## Getting Started

以下は Windows + PowerShell 想定です。他 OS の場合は適宜読み替えてください。

### 1) uv をインストール

uv は Python パッケージ/環境/ツール管理の高速CLIです。

```pwsh
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

インストール確認:

```pwsh
uv --version
```

### 2) 依存の同期（開発時 or ローカル実行）

リポジトリ直下で仮想環境と依存関係を同期します。

```pwsh
uv sync
```

### 3) コマンドの実行方法（2通り）

1. リポジトリ内の仮想環境から実行

```pwsh
# ヘッダ無し・audioRMS の欠損行を除外して受信
uv run xiao-nrf52840-sense-receiver --no-header --drop-missing-audio

# 受信が5秒以上途絶えたら終了（ハング防止）
uv run xiao-nrf52840-sense-receiver --idle-timeout 5

# CSV をファイル保存
uv run xiao-nrf52840-sense-receiver > out.csv
```

1. ツール（global-like）として実行

一度だけローカルのパッケージをツール登録します。

```pwsh
uv tool install .
```

以後、どこからでも以下のように実行できます。

```pwsh
uvx xiao-nrf52840-sense-receiver --no-header --drop-missing-audio

# 受信が10秒以上途絶えたら終了
uvx xiao-nrf52840-sense-receiver --idle-timeout 10
```

### オプション

- `--address <MAC>`: BLE アドレス直指定（スキャンを回避）
- `--device-name <NAME>`: スキャンで優先的に探すデバイス名（既定: `XIAO Sense IMU`）
- `--scan-timeout <sec>`: スキャンのタイムアウト秒数（既定: 10.0）
- `--no-header`: 出力の先頭ヘッダ行を抑止
- `--drop-missing-audio`: `audioRMS=-1.0` の行を除外
- `--idle-timeout <sec>`: 受信が指定秒数途絶えたらエラー終了（未指定で無制限）

## BLE 受信の前提条件（Windows）

以下が満たされていないとスキャン/接続に失敗します。

- Windows の「Bluetooth」がオン
- Windows の「位置情報サービス」がオン（BLE スキャンに必要）
- ローカルログインの PowerShell で実行（リモートデスクトップ経由だと失敗する場合あり）
- WSL/仮想環境内ではなく Windows ネイティブで実行
- Bluetooth アダプタが有効で、ドライバが正しく認識
- XIAO デバイスが切断状態でアドバタイズ中

## トラブルシュート

- エラー: `Failed to start scanner. Is Bluetooth turned on?`
  - 上の前提条件を確認。特に「位置情報サービス」をオンにする
  - デバイスマネージャーで Bluetooth アダプタの状態/ドライバを確認
  - 既知のアドレスが分かるなら `--address` で直接接続を試す

- `対象デバイスが見つかりませんでした` と出る
  - デバイス名を変更している場合は `--device-name` で指定
  - 距離を近づけ、アドバタイズが再開されているか確認
  - `--scan-timeout` を延ばす

## 参考（実装のポイント）

- NUS (Nordic UART Service) UUID:
  - Service: `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
  - TX Notify: `6e400003-b5a3-f393-e0a9-e50e24dcca9e`
  - RX Write: `6e400002-b5a3-f393-e0a9-e50e24dcca9e`（未使用）
- CSV: `millis, ax, ay, az, gx, gy, gz, tempC, audioRMS` の9フィールド
- 通知断片はアプリ側で改行区切りに再構成

---

