# XIAO nRF52840 Sense データロガー - レシーバー

<!-- Language Switcher -->
**Languages**: [English](./README.md) | [日本語](./README.ja.md)

---

## 🚀 概要

XIAO nRF52840 SenseがBLE（Nordic UARTサービス互換）で送信するセンサーデータを収集し、リアルタイムオシロスコープ可視化またはCSV出力を提供するPython BLEレシーバーツールです。`bleak`ライブラリを使用してWindows、macOS、LinuxでのクロスプラットフォームBLE通信を実現しています。

### 主要機能

- **クロスプラットフォームBLEサポート**: bleakライブラリによるWindows、macOS、Linux対応
- **リアルタイムオシロスコープ**: ライブセンサープロット付きインタラクティブWebベース可視化
- **CSVデータエクスポート**: 設定可能なフィルタリングとコンソール出力付きストリーム処理
- **堅牢な接続ハンドリング**: 自動再接続とタイムアウト管理
- **柔軟な出力モード**: Webオシロスコープ（デフォルト）またはCSVエクスポートモード
- **開発者ツール**: 型チェック、リンティング、テストフレームワーク統合

## 🛠 インストールとセットアップ

### 前提条件

- **Python**: 3.12+（型ヒントと現代的な非同期機能に必要）
- **Bluetooth**: BLE対応アダプタとシステムBluetooth有効化
- **オペレーティングシステム**: BLEサポート付きWindows、macOS、またはLinux

### 1. uvパッケージマネージャーのインストール

uvは高速なPythonパッケージ・プロジェクト管理ツールです。プラットフォームを選択してください：

**Windows (PowerShell)**:
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS/Linux**:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**インストール確認**:
```bash
uv --version
```

### 2. プロジェクトセットアップ

プロジェクトルートから仮想環境と依存関係を同期：

```bash
# receiverディレクトリに移動
cd receiver/

# 依存関係をインストールして仮想環境を作成
uv sync
```

これにより、以下を含む全ての必要依存関係を持つ分離されたPython環境が作成されます：
- `bleak`: クロスプラットフォームBLEライブラリ
- `dash`: オシロスコープインターフェース用Webアプリケーションフレームワーク
- `plotly`: リアルタイム可視化用インタラクティブプロッティングライブラリ
- `pandas`: データ操作・解析

### 3. 使用方法

#### 方法1: ローカル開発（推奨）

プロジェクト仮想環境から実行：

```bash
# デフォルト使用法 - Webオシロスコープ起動
uv run xiao-nrf52840-sense-receiver

# CSV出力モード - クリーンな出力でデータ受信
uv run xiao-nrf52840-sense-receiver --csv --no-header --drop-missing-audio

# カスタムポートでオシロスコープ
uv run xiao-nrf52840-sense-receiver --port 9000

# CSVモードでタイムアウト保護 - 5秒間データがなければ終了
uv run xiao-nrf52840-sense-receiver --csv --idle-timeout 5

# CSVデータをファイル保存
uv run xiao-nrf52840-sense-receiver --csv --no-header > sensor_data.csv

# デバイスアドレス直接指定（スキャンをスキップ）
uv run xiao-nrf52840-sense-receiver --address "12:34:56:78:9A:BC"
```

#### 方法2: グローバルツールインストール

システム全体のツールとしてインストール（一度のみセットアップ）：

```bash
# 現在のディレクトリからグローバルにツールをインストール
uv tool install .

# インストール後はどこからでも実行可能
uvx xiao-nrf52840-sense-receiver                                           # オシロスコープ起動
uvx xiao-nrf52840-sense-receiver --csv --no-header --drop-missing-audio
uvx xiao-nrf52840-sense-receiver --csv --idle-timeout 10
```

## ⚙️ コマンドラインオプション

| オプション | 説明 | デフォルト | 例 |
|-----------|------|-----------|---|
| `--csv` | CSV出力モードを有効化 | オシロスコープモード | `--csv` |
| `--address <MAC>` | 直接BLEアドレス指定（スキャンをスキップ） | 自動発見 | `--address "12:34:56:78:9A:BC"` |
| `--device-name <NAME>` | スキャン対象デバイス名 | `"XIAO Sense IMU"` | `--device-name "My Sensor"` |
| `--scan-timeout <sec>` | BLEスキャンタイムアウト秒数 | 10.0 | `--scan-timeout 15` |
| `--port <number>` | オシロスコープ用Webサーバーポート | 8050 | `--port 9000` |
| `--mock` | Mockデータを使用（BLEデバイス不要） | 実際のBLEデータ | `--mock` |
| `--no-header` | CSVヘッダー出力を抑制（CSVモード時のみ） | ヘッダー含む | `--no-header` |
| `--drop-missing-audio` | audioRMS=-1.0行をフィルター（CSVモード時のみ） | 全て含む | `--drop-missing-audio` |
| `--idle-timeout <sec>` | N秒間データなしで終了 | 無制限 | `--idle-timeout 30` |

## 🔧 システム要件

### Windows
- **Bluetooth**: 設定でシステムBluetooth有効化
- **位置情報サービス**: 有効化必須（BLEスキャンに必要）
- **実行**: ローカルPowerShell（リモートデスクトップでは問題が発生する場合）
- **環境**: ネイティブWindows（WSL/仮想化環境不可）
- **ドライバー**: Bluetoothアダプタが適切に認識
- **デバイス状態**: XIAOデバイスが切断状態でアドバタイジング中

### macOS
- **Bluetooth**: システムBluetooth有効化
- **権限**: プロンプト時にTerminal/IDEのBluetooth アクセス許可
- **デバイス状態**: XIAOデバイスが切断状態でアドバタイジング中

### Linux
- **Bluetooth**: BlueZスタックのインストールと実行
- **権限**: ユーザーが`bluetooth`グループに所属または適切な権限で実行
- **デバイス状態**: XIAOデバイスが切断状態でアドバタイジング中

## 🚑 トラブルシューティング

### 一般的な接続問題

**エラー: `Failed to start scanner. Is Bluetooth turned on?`**
- システムBluetoothが有効化されているか確認
- **Windows**: 位置情報サービスを有効化（BLEスキャンに必要）
- デバイスマネージャーでBluetoothアダプターの状態を確認
- MACアドレスが分かる場合は`--address`で直接接続を試す

**エラー: `Target device not found`**
- デバイスがアドバタイジング中か確認（XIAOボードの状態チェック）
- デバイス名が一致するか確認（カスタマイズされている場合は`--device-name`を使用）
- スキャンタイムアウトを増やす: `--scan-timeout 20`
- デバイス同士を近づける
- XIAOデバイスのアドバタイジングを再開

**頻繁な接続断**
- 他のデバイスからのBLE干渉をチェック
- XIAOデバイスの電源供給安定性を確認
- 期待される切断には`--idle-timeout`を使用
- デバイス間の距離を確認

### パフォーマンス問題

**データ受信が遅い**
- BLE接続パラメータの最適化が必要な可能性
- システムBluetoothスタックのパフォーマンスをチェック
- XIAOデバイスのバッテリーレベルを確認

**オーディオデータの欠損 (audioRMS = -1.0)**
- 音声サンプルが不十分な場合の正常な動作
- これらの行をフィルターするには`--drop-missing-audio`を使用
- 音声処理には最低160サンプルが必要

## 📊 データ形式

レシーバーは以下の構造のCSVデータを処理します：

```
millis,ax,ay,az,gx,gy,gz,tempC,audioRMS
```

| フィールド | 説明 | 単位 | 範囲 |
|-----------|------|------|------|
| `millis` | デバイス起動からのタイムスタンプ | ms | 0から〜49.7日 |
| `ax,ay,az` | 加速度計X,Y,Z | g | ±16g |
| `gx,gy,gz` | ジャイロスコープX,Y,Z | dps | ±2000 dps |
| `tempC` | 温度 | °C | デバイス依存 |
| `audioRMS` | 音声RMSレベル | - | ≥0.0 または -1.0（欠損） |

## 🔌 BLEプロトコル詳細

**Nordic UARTサービス（NUS）UUID**:
- **サービス**: `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
- **TX特性** (デバイス→レシーバー): `6e400003-b5a3-f393-e0a9-e50e24dcca9e`
- **RX特性** (レシーバー→デバイス): `6e400002-b5a3-f393-e0a9-e50e24dcca9e` (未使用)

**データ伝送**:
- **形式**: `\n`で終端されるCSV行
- **断片化**: BLE通知が行を分割する可能性；レシーバーが再組み立て
- **レート**: XIAOデバイスからBLE経由で〜25Hz

## 📝 開発

### コード品質ツール

```bash
# コードフォーマット
uv run --frozen ruff format .

# コードリント
uv run --frozen ruff check .

# 型チェック
uv run --frozen pyright

# テスト実行
uv run --frozen pytest
```

### 開発ガイドライン

- **パッケージ管理**: `uv`のみ使用、`pip`は使用禁止
- **型ヒント**: 全てのpublic関数で必須
- **ドキュメンテーション**: public APIにはGoogle形式のdocstring
- **テスト**: 新機能とバグ修正にはテストを記述
- **ログ**: Pythonログモジュール使用、`print()`文は禁止

### 依存関係追加

```bash
# ランタイム依存関係を追加
uv add package-name

# 開発依存関係を追加
uv add --dev package-name

# 特定パッケージをアップグレード
uv add package-name --upgrade-package package-name
```

## 📚 参考文書

- [bleak Documentation](https://bleak.readthedocs.io/): Python BLEライブラリ
- [Nordic UART Service](https://developer.nordicsemi.com/nRF_Connect_SDK/doc/latest/nrf/libraries/bluetooth_services/services/nus.html): BLEプロトコル仕様
- [uv Documentation](https://docs.astral.sh/uv/): パッケージマネージャーガイド
- [Python asyncio](https://docs.python.org/3/library/asyncio.html): 非同期プログラミング

## 🚀 現在の機能と将来の機能拡張

### ✅ 現在の機能
- **リアルタイムオシロスコープ**: ライブセンサープロット付きインタラクティブWebベース可視化
- **CSVデータエクスポート**: 設定可能なストリーム処理とファイル出力
- **クロスプラットフォームBLE**: bleakによるWindows、macOS、Linuxサポート
- **Mockデータモード**: 物理デバイスなしでのテスト

### 🔮 将来の機能拡張
- **可視化の強化**: 追加のプロットタイプと解析ツール
- **データ解析ツール**: 内蔵信号処理とフィルタリング
- **複数デバイス対応**: 複数センサーからの同時データ収集
- **データベース統合**: 時系列データベースへの直接ロギング
- **モバイルアプリ**: モニタリング用コンパニオンモバイルアプリ