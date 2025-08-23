# XIAO nRF52840 Sense サンプル

プロジェクト名: xiao-nrf52840-sense  
対応ボード: Seeed Studio XIAO nRF52840 Sense  
フレームワーク: Arduino  
PlatformIO 環境名: `seeed_xiao_nrf52840_sense`（`platformio.ini` 参照）

このリポジトリは、PlatformIO Core（CLI）だけで XIAO nRF52840 系にビルド・書き込み・実行する最小サンプルです。`pio` コマンドのみを使用します。

---

## 前提条件（Windows + PowerShell）

以下がインストールされていることを想定します。

- Python 3.8 以上
- Git（PlatformIO が GitHub からプラットフォームを取得するため）

任意の導入例:

Python（未導入なら）

```powershell
winget install --id Python.Python.3.12 -e --source winget
```

(Windowsの場合)環境変数設定 PATH に下記を追加してターミナルを再起動(VS Codeの場合はVS Codeを完全再起動)  

```
%LOCALAPPDATA%\Programs\Python\Python312
%LOCALAPPDATA%\Programs\Python\Python312\Scripts
%APPDATA%\Python\Python312
```


Git（未導入なら）

```powershell
winget install --id Git.Git -e --source winget
```

%HOMEPATH%\.gitconfig を下記のように設定

```ini
[http]
	sslVerify = false
[user]
	name = <your name>
    email = <your email>
```

---

## 環境変数の設定

環境変数に下記を追加

| 変数名 | 値 |
|-|-|
| HTTP_PROXY |http://proxy-sen.noc.sony.co.jp:10080|
| HTTPS_PROXY |http://proxy-sen.noc.sony.co.jp:10080|
|NO_PROXY|localhost,127.0.0.1,::1,github.com,api.github.com,api.githubcopilot.com,githubusercontent.com,raw.githubusercontent.com,marketplace.visualstudio.com,vscode.dev,update.code.visualstudio.com|

---

## PlatformIO Core (CLI) のインストール

推奨（pipx を使用）:

pipx の導入（未導入なら）

```powershell
python -m pip install --user pipx
```

```powershell
python -m pipx ensurepath
```

新しい PowerShell を開き直してから実行

```powershell
pipx install platformio
```

動作確認

```powershell
pio --version
```

代替（pip を直接使用）:

PlatformIO のインストール

```powershell
python -m pip install --user -U platformio
```

必要なら PATH を一時反映（セッション内）

```powershell
$env:Path = "$([Environment]::GetFolderPath('LocalApplicationData'))\Programs\Python\Python$(python -c "import sys;print(str(sys.version_info.major)+str(sys.version_info.minor))")\Scripts;" + $env:Path
```

動作確認

```powershell
pio --version
```

---

## プロジェクト取得と構成

リポジトリのクローン

```powershell
git clone git@github.com:ylabo0717/nextjs-boilerplate.git
```

ディレクトリ移動

```powershell
cd xiao-nrf52840-platformio-sample
```

---

## ビルド（コンパイル）

環境は 1 つだけなので `-e` の指定は不要です。

```powershell
pio run
```

成果物例: `.pio\build\seeed_xiao_nrf52840_sense\firmware.hex`

---

## 書き込み（Upload）

XIAO nRF52840 系はブートローダ（DFU）モードで書き込みます。

1. リセットボタンを2回カチカチと押してDFUモードにする
2. 新しい COM ポートが現れることを確認（必要に応じて `pio device list`）。
3. 書き込み:

```powershell
pio run -t upload
```

ポートを明示したい場合（例 : COM5）

```powershell
pio run -t upload --upload-port COM5
```

---

## 実行とシリアルモニタ

スケッチの `setup()`/`loop()` が起動します。シリアルログを見る場合は、スケッチのボーレート（例: 115200bps）に合わせてモニタします。

```powershell
pio device monitor -b 115200
```

スケッチは `src/main.cpp` にあります。必要に応じて `setup()` に `Serial.begin(115200);` を追加してください。

---

## よく使うコマンド

依存関係・プラットフォームの更新

```powershell
pio pkg update
```

ビルド

```powershell
pio run
```

クリーン

```powershell
pio run -t clean
```

書き込み

```powershell
pio run -t upload
```

シリアルモニタ

```powershell
pio device monitor -b 115200
```

---

## トラブルシュート

- `pio` が見つからない: 新しい PowerShell を開き直す/パス設定を確認（pipx の場合は `python -m pipx ensurepath` 実行後に再起動）。
- ボードが見えない/書き込みできない: リセットボタン長押しでブートローダに入ってから再実行。`pio device list` で COM を確認し、必要なら `--upload-port` を使用。
- 初回取得に失敗: ネットワーク/プロキシ設定を確認し、`pio pkg update` を試す。
- 権限エラー: PowerShell を管理者として実行、または別 USB ポート/ケーブルを試す。

---

## 参考リンク

- [PlatformIO Core (CLI)](https://docs.platformio.org/en/latest/core/index.html)
- [Seeed XIAO nRF52840](https://wiki.seeedstudio.com/XIAO_BLE/)
- [Seeed XIAO nRF52840 Sense](https://wiki.seeedstudio.com/XIAO_BLE_Sense/)

