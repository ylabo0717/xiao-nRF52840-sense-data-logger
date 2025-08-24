# XIAO nRF52840 Sense データロガー - ファームウェア

<!-- Language Switcher -->

**Languages**: [English](./README.md) | [日本語](./README.ja.md)

---

## 🚀 概要

IMU（LSM6DS3）加速度・ジャイロスコープデータとPDMマイクロフォンの音声RMS値を収集し、USBシリアルとBLE UART両方でCSV形式で送信するXIAO nRF52840 Sense用ファームウェアです。

### 主要機能

- **マルチセンサーデータ収集**: IMU + PDMマイクロフォンのタイムスタンプ同期
- **デュアル出力**: USBシリアル（フルレート〜100Hz）+ BLE（最適化〜25Hz）
- **堅牢なBLE**: 自動再接続、部分書き込み処理、タイムアウト管理
- **動的ハードウェア検出**: LSM6DS3互換性のためのI2Cアドレススキャン

## 🔧 ハードウェア構成

### ターゲットプラットフォーム

- **ボード**: Seeed Studio XIAO nRF52840 Sense
- **フレームワーク**: Arduino + PlatformIO
- **プラットフォーム**: GitHub からのカスタムSeeedプラットフォーム
- **環境**: `seeed_xiao_nrf52840_sense`

### ハードウェアコンポーネント

- **IMU**: LSM6DS3 加速度・ジャイロスコープ (I2Cアドレス 0x6A または 0x6B)
- **マイクロフォン**: 内蔵PDMマイクロフォン (16kHz、1チャンネル、16ビット)
- **通信**: BLE Nordic UARTサービス互換
- **I2C**: プライマリWireインターフェース (400kHz)、オプションのWire1サポート

## 📊 データ出力形式

CSVフィールド: `millis,ax,ay,az,gx,gy,gz,tempC,audioRMS`

- **シリアル出力**: 〜100Hz フルレート（ヘッダー付き）
- **BLE出力**: 〜25Hz 帯域幅最適化（ヘッダーなし）
- **Audio RMS**: 10msスライディングウィンドウ（16kHzで160サンプル）、データ不足時は-1.0
- **BLEサービス**: Nordic UARTサービス（NUS）、デバイス名「XIAO Sense IMU」

## 🛠 開発セットアップ

### 前提条件

- **Python**: 3.8+（PlatformIO用）
- **Git**: プラットフォーム/ライブラリ管理用
- **PlatformIO Core**: CLI ベース開発環境

### インストール

1. **PlatformIO Core をインストール**（推奨: pipx）:

   ```bash
   # pipx が未インストールの場合
   python -m pip install --user pipx
   python -m pipx ensurepath

   # PlatformIO をインストール
   pipx install platformio

   # インストール確認
   pio --version
   ```

2. **代替方法**（直接pip）:
   ```bash
   python -m pip install --user -U platformio
   ```

### ビルドとアップロード

```bash
# ファームウェアをビルド
pio run

# デバイスにアップロード（DFUモード必要）
pio run -t upload

# 特定のポートにアップロード
pio run -t upload --upload-port COM5

# ビルド成果物をクリーン
pio run -t clean

# 依存関係/プラットフォームを更新
pio pkg update
```

### プログラミングモード

XIAO nRF52840 はプログラミングにブートローダー（DFU）モードを使用:

1. **DFUモード開始**: リセットボタンを素早く2回クリック
2. **確認**: 新しいCOMポートが表示される（`pio device list` で確認）
3. **アップロード**: アップロードコマンドを実行

### モニタリングとデバッグ

```bash
# シリアル出力をモニター
pio device monitor -b 115200

# 利用可能なデバイス/ポートをリスト
pio device list
```

## 💻 コード構成

### メインコンポーネント (src/main.cpp)

1. **IMU管理**:
   - I2Cアドレス検出による動的LSM6DS3初期化
   - センサー初期化失敗時のリトライロジック
   - センサー障害時のI2Cデバイススキャン

2. **PDMオーディオ処理**:
   - 連続オーディオキャプチャ用リングバッファ
   - 10msスライディングウィンドウでのRMS計算
   - リアルタイムパフォーマンス用割り込み駆動PDM

3. **BLE通信**:
   - 部分書き込み処理による堅牢なBLE UART
   - タイムアウト管理と接続回復
   - 切断時の自動アドバタイジング再開

4. **データ同期**:
   - タイムスタンプ付きセンサーフュージョンデータ
   - 一貫したフィールド構造のCSV出力フォーマット

### エラーハンドリング

- **IMU初期化**: 失敗時は1秒ごとにリトライ
- **I2Cスキャン**: IMU障害時は5秒ごとのデバイス発見
- **BLE回復**: 書き込みタイムアウトと自動再接続
- **バッファ保護**: PDMリングバッファオーバーフロー防止

## 📋 依存関係

`platformio.ini` より:

- **Seeed Arduino LSM6DS3**: IMUセンサーライブラリ
- **Adafruit Bluefruit nRF52**: BLEスタック（プラットフォームに含まれる）
- **Arduino Framework**: nRF52拡張とコアライブラリ

## 🔧 設定

### ハードウェア設定

- **I2C速度**: 最適なセンサーパフォーマンスのための400kHz
- **BLE MTU**: データスループット最適化
- **オーディオサンプリング**: 10ms RMSウィンドウでの16kHz PDM

### データレート最適化

- **シリアル**: 全データでのフルセンサーレート（〜100Hz）
- **BLE**: 同じデータ精度での帯域幅制限レート（〜25Hz）
- **オーディオ**: データレートでのRMS報告を伴う連続キャプチャ

## 🚨 トラブルシューティング

### よくある問題

- **PlatformIO が見つからない**: インストール後にターミナル/IDEを再起動、PATHを確認
- **ボードが検出されない**: DFUモードに入る（リセット2回クリック）、`pio device list` で確認
- **アップロード失敗**: 異なるUSBポート/ケーブルを試す、DFUモードを確認、`--upload-port` を使用
- **初回ビルド失敗**: ネットワーク/プロキシ設定確認、`pio pkg update` を実行
- **権限エラー**: 管理者として実行、または異なるUSBポートを試す

### ハードウェア問題

- **IMUデータなし**: I2C接続確認、LSM6DS3電源を確認
- **オーディオデータなし**: PDMマイクロフォンに初期化遅延が必要な場合
- **BLE接続問題**: デバイスのアドバタイジング確認、受信側のBLEスタック確認

## 📚 参考文書

- [PlatformIO Core (CLI)](https://docs.platformio.org/en/latest/core/index.html)
- [Seeed XIAO nRF52840 Sense](https://wiki.seeedstudio.com/XIAO_BLE_Sense/)
- [LSM6DS3 データシート](https://www.st.com/resource/en/datasheet/lsm6ds3.pdf)
- [Nordic UART Service 仕様](https://developer.nordicsemi.com/nRF_Connect_SDK/doc/latest/nrf/libraries/bluetooth_services/services/nus.html)

## ⚡ パフォーマンス注記

- **シリアル出力**: 常に有効、フルセンサーレート
- **BLE出力**: 接続時且つ通知有効時のみ
- **オーディオ処理**: リアルタイムパフォーマンス用割り込み駆動
- **メモリ使用量**: リングバッファ設計でRAM要件を最小化
- **電力効率**: バッテリー動作用の最適化されたBLEパラメータ
