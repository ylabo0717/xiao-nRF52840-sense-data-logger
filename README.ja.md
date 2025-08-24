# XIAO nRF52840 Sense データロガー

<!-- Language Switcher -->
**Languages**: [English](./README.md) | [日本語](./README.ja.md)

---

## 🚀 概要

XIAO nRF52840 Sense マイクロコントローラー用の2コンポーネント構成センサーデータロガーシステムです。IMU（加速度/ジャイロ）とPDMマイクロフォンデータを収集し、BLEとUSBシリアル経由でCSV形式でストリーミングします。

### システム構成

- **Sender**: XIAO nRF52840 Sense上で動作するC++/Arduinoファームウェア
- **Receiver**: データ収集と可視化用のPython BLEクライアントツール

## 📦 コンポーネント

### [Sender（ファームウェア）](./sender/)
- **ハードウェア**: LSM6DS3 IMUとPDMマイクロフォン搭載のXIAO nRF52840 Sense
- **フレームワーク**: Arduino + PlatformIO
- **出力**: BLE Nordic UARTサービスとUSBシリアル経由のCSVデータ
- **データレート**: シリアル経由〜100Hz、BLE経由〜25Hz

### [Receiver（Pythonツール）](./receiver/)
- **プラットフォーム**: Python 3.12+ with uvパッケージマネージャー
- **機能**: BLEデータ受信、CSVエクスポート、リアルタイム可視化
- **依存関係**: bleak（BLE）、dash（Web UI）、plotly（チャート）

## 🚀 クイックスタート

### 前提条件

- **ハードウェア**: XIAO nRF52840 Senseボード
- **ソフトウェア**: 
  - PlatformIO Core（ファームウェア開発）
  - Python 3.12+ with uv（データ受信）
  - Bluetoothアダプタ（BLE受信用）

### 1. ファームウェアセットアップ

```bash
cd sender/
pio run                    # ファームウェアビルド
pio run -t upload         # アップロード（DFUモード必要 - リセットボタン2回押し）
pio device monitor -b 115200  # シリアル出力監視
```

### 2. データ受信

```bash
cd receiver/
uv sync                   # 依存関係インストール
uv run xiao-nrf52840-sense-receiver --no-header --drop-missing-audio
```

## 📊 データ形式

9フィールドのCSV出力:
```
millis,ax,ay,az,gx,gy,gz,tempC,audioRMS
```

- **millis**: タイムスタンプ（起動からのミリ秒）
- **ax,ay,az**: 加速度計（g）
- **gx,gy,gz**: ジャイロスコープ（dps）  
- **tempC**: 温度（°C）
- **audioRMS**: オーディオRMS値（10msウィンドウ、欠損データは-1.0）

## 🔧 開発

### ファームウェア開発
詳細なファームウェア開発手順については[sender/README.md](./sender/README.md)を参照してください。

### Pythonツール開発  
Python開発ガイドラインとAPI文書については[receiver/README.md](./receiver/README.md)を参照してください。

## 🎯 使用例

- **動作解析**: ロボティクスと動作研究のためのIMUデータロギング
- **音響監視**: 加速度計コンテキストによる環境音レベル追跡
- **IoTプロトタイピング**: BLE接続によるワイヤレスセンサーデータ収集
- **教育プロジェクト**: リアルタイムセンサーデータ可視化と解析

## 🛠 システム要件

### ハードウェア
- XIAO nRF52840 Senseボード
- プログラミングとシリアル通信用のUSB-Cケーブル
- Bluetooth Low Energyサポートのあるコンピューター

### ソフトウェア
- **ファームウェア**: PlatformIO Core、Git
- **データ受信**: Python 3.12+、uvパッケージマネージャー
- **OS対応**: Windows、macOS、Linux（BLEスタック依存）

## 📄 ライセンス

このプロジェクトはMITライセンスの下でライセンスされています。詳細は[LICENSE](LICENSE)ファイルを参照してください。

## 🤝 貢献

1. リポジトリをフォーク
2. フィーチャーブランチを作成（`git checkout -b feature/amazing-feature`）
3. 変更をコミット（`git commit -m 'Add amazing feature'`）
4. ブランチにプッシュ（`git push origin feature/amazing-feature`）
5. プルリクエストを開く

## 📞 サポート

技術サポートと質問については：
- `sender/`と`receiver/`のコンポーネント固有のREADMEファイルを確認
- ハードウェア文書の確認: [XIAO nRF52840 Sense](https://wiki.seeedstudio.com/XIAO_BLE_Sense/)
- GitHub Issuesでの問題報告