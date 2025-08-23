// XIAO nRF52840 Sense: Seeed LSM6DS3 ライブラリで加速度・ジャイロを取得してシリアル出力
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_TinyUSB.h>
#include "LSM6DS3.h"  // Seeed_Arduino_LSM6DS3
#include <PDM.h>       // 内蔵PDMマイク（Adafruit nRF52 コア同梱）
#include <math.h>      // sqrt
#include <bluefruit.h> // BLE (Adafruit Bluefruit nRF52)

static const uint32_t SERIAL_BAUD = 115200;

// I2Cアドレス（通常 0x6A、場合により 0x6B）
static const uint8_t ADDR1 = 0x6A;
static const uint8_t ADDR2 = 0x6B;

// 動的に選択されたIMUインスタンスを保持
LSM6DS3* gImu = nullptr;
uint8_t gImuAddr = 0;

// BLE UART サービス
BLEUart bleuart; // スマホからはシリアルのように扱える

// 2系統目のI2Cがある場合に備えて参照（存在しない環境では無視）
#if defined(PIN_WIRE1_SDA) && defined(PIN_WIRE1_SCL)
extern TwoWire Wire1;
#define HAS_WIRE1 1
#else
#define HAS_WIRE1 0
#endif

// --- BLE 安全送信ユーティリティ -----------------------------------------
// BLEUart は write() が部分書き込み/0 を返す場合があるため、全量書き切る。
// timeoutMs 以内に送れなければ false を返す（改行は送らないなどの判断用）。
static const uint32_t BLE_BODY_TIMEOUT_MS = 600; // 本文の送信許容（将来拡張用・現状未使用）
static const uint32_t BLE_LF_TIMEOUT_MS   = 100; // LFの送信許容
static const uint32_t BLE_BODY_SLICE_MS   = 120; // 1回の送信試行で使う時間枠

// 予算時間内で“できた分だけ”送る。戻り値は実際に書けたバイト数（0可）。
static size_t bleWriteSome(BLEUart& uart, const uint8_t* buf, size_t len, uint32_t budgetMs)
{
  if (!Bluefruit.connected()) return 0;
  #ifdef BLE_UART_HAS_NOTIFY_ENABLED
  if (!uart.notifyEnabled()) return 0;
  #endif
  uint32_t start = millis();
  size_t total = 0;
  uint32_t backoff = 1;
  while (total < len && (millis() - start) < budgetMs) {
    size_t w = uart.write(buf + total, len - total);
    if (w > 0) {
      total += w;
      backoff = 1;
    } else {
      delay(backoff);
      if (backoff < 32) backoff <<= 1;
    }
  }
  return total;
}

// CSVラインの整形（本文のみ。改行は付けない）
static int formatCsvLine(char* dst, size_t dstsz,
                         unsigned long ts,
                         float ax, float ay, float az,
                         float gx_dps, float gy_dps, float gz_dps,
                         float tC, float rms)
{
  int n = snprintf(dst, dstsz,
                   "%lu,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.2f,%.2f",
                   ts,
                   (double)ax, (double)ay, (double)az,
                   (double)gx_dps, (double)gy_dps, (double)gz_dps,
                   (double)tC, (double)rms);
  if (n < 0) return -1;
  if ((size_t)n >= dstsz) {
    // 末尾切り詰め
    n = (int)dstsz - 1;
    dst[n] = '\0';
  }
  return n;
}

bool beginIMU() {
  if (gImu) { delete gImu; gImu = nullptr; }
  gImu = new LSM6DS3(I2C_MODE, ADDR1);
  if (gImu->begin() == 0) {
    gImuAddr = ADDR1;
    Serial.println("IMU begin @0x6A");
    return true;
  }
  delete gImu; gImu = nullptr;
  gImu = new LSM6DS3(I2C_MODE, ADDR2);
  if (gImu->begin() == 0) {
    gImuAddr = ADDR2;
    Serial.println("IMU begin @0x6B");
    return true;
  }
  delete gImu; gImu = nullptr;
  return false;
}

// ==== PDM (内蔵マイク) ====
// 16kHz, 1ch, 16bit を想定。onReceiveコールバックでリングバッファに格納。
static constexpr uint32_t PDM_SR = 16000;
static constexpr size_t   PDM_FRAME_SAMPLES = 160;   // 10ms 相当
static constexpr size_t   PDM_RING_SAMPLES  = 4096;  // 約256ms分
static int16_t            gPdmRing[PDM_RING_SAMPLES];
static volatile size_t    gPdmWrite = 0;
static volatile size_t    gPdmRead  = 0;

void onPDMdata() {
  int bytes = PDM.available();
  if (bytes <= 0) return;
  // 一時バッファに読み出し（bytes は2の倍数のはず）
  static int16_t tmp[512];
  int toRead = bytes;
  if (toRead > (int)sizeof(tmp)) toRead = (int)sizeof(tmp);
  int nread = PDM.read(tmp, toRead);
  if (nread <= 0) return;
  size_t samples = (size_t)nread / sizeof(int16_t);
  // リングへコピー（割り込み中なので簡易に実装）
  for (size_t i = 0; i < samples; ++i) {
    gPdmRing[gPdmWrite] = tmp[i];
    gPdmWrite = (gPdmWrite + 1) % PDM_RING_SAMPLES;
    // 追い越し時は読み取り側も進めてドロップ（最古データを捨てる）
    if (gPdmWrite == gPdmRead) {
      gPdmRead = (gPdmRead + 1) % PDM_RING_SAMPLES;
    }
  }
}

// リングから最大Nサンプルを取り出してRMSを計算。足りなければfalse。
bool pdmConsumeRMS(size_t needSamples, float &outRms) {
  // 利用可能サンプル数
  size_t avail = (gPdmWrite + PDM_RING_SAMPLES - gPdmRead) % PDM_RING_SAMPLES;
  if (avail < needSamples) return false;
  // 合計と2乗和を計算（DC除去は簡易のため省略）
  double sumSq = 0.0;
  for (size_t i = 0; i < needSamples; ++i) {
    int16_t s = gPdmRing[gPdmRead];
    gPdmRead = (gPdmRead + 1) % PDM_RING_SAMPLES;
    sumSq += (double)s * (double)s;
  }
  outRms = (float)sqrt(sumSq / (double)needSamples);
  return true;
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  Serial.begin(SERIAL_BAUD);
  unsigned long start = millis();
  while (!Serial && (millis() - start < 3000)) { delay(10); }

  Serial.println();
  Serial.println("=== XIAO nRF52840 Sense IMU (Seeed LSM6DS3) ===");
  Serial.print("Build: "); Serial.print(__DATE__); Serial.print(" "); Serial.println(__TIME__);
  // I2Cピン情報
  #ifdef PIN_WIRE_SDA
  Serial.print("Wire SDA="); Serial.print(PIN_WIRE_SDA);
  #endif
  #ifdef PIN_WIRE_SCL
  Serial.print(" SCL="); Serial.println(PIN_WIRE_SCL);
  #else
  Serial.println();
  #endif
  #if HAS_WIRE1
  Serial.print("Wire1 SDA="); Serial.print(PIN_WIRE1_SDA);
  Serial.print(" SCL="); Serial.println(PIN_WIRE1_SCL);
  #endif

  Wire.begin();
  Wire.setClock(400000);
  #if HAS_WIRE1
  Wire1.begin();
  Wire1.setClock(400000);
  #endif

  // PDM 初期化（16kHz, 1ch）
  PDM.onReceive(onPDMdata);
  // 一部の実装ではゲイン指定が可能（無視されるプラットフォームもあり）
  #ifdef PDM_HAS_SET_GAIN
  PDM.setGain(20);
  #endif
  if (!PDM.begin(1, PDM_SR)) {
    Serial.println("WARN: PDM begin failed");
  }

  // BLE 初期化（UARTサービスでCSVを出力）
  // 帯域最大化（ATT MTU/データ長/ConnParam を広めに）：大量通知の詰まりを緩和
  Bluefruit.configPrphBandwidth(BANDWIDTH_MAX);
  Bluefruit.begin();
  Bluefruit.setName("XIAO Sense IMU");
  Bluefruit.setTxPower(4); // 0~8程度
  bleuart.begin();
  Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
  Bluefruit.Advertising.addTxPower();
  Bluefruit.Advertising.addService(bleuart);
  Bluefruit.ScanResponse.addName();
  Bluefruit.Advertising.restartOnDisconnect(true);
  Bluefruit.Advertising.setInterval(32, 244); // 20ms-152.5ms
  Bluefruit.Advertising.setFastTimeout(30);
  Bluefruit.Advertising.start(0);

  // 推奨範囲の接続間隔
  Bluefruit.Periph.setConnInterval(6, 12);

  if (!beginIMU()) {
    Serial.println("IMU not found (0x6A/0x6B). Scanning I2C...");
    uint8_t found = 0;
    for (uint8_t a = 0x08; a <= 0x77; a++) {
      Wire.beginTransmission(a);
      if (Wire.endTransmission() == 0) {
        Serial.print(" - found 0x"); Serial.println(a, HEX);
        found++;
      }
    }
    #if HAS_WIRE1
    Serial.println("I2C scan (Wire1) start...");
    uint8_t found2 = 0;
    for (uint8_t a = 0x08; a <= 0x77; a++) {
      Wire1.beginTransmission(a);
      if (Wire1.endTransmission() == 0) {
        Serial.print(" - found 0x"); Serial.println(a, HEX);
        found2++;
      }
    }
    if (!found2) Serial.println(" - no devices found on Wire1");
    Serial.println("I2C scan (Wire1) done.");
    #endif
    if (!found) Serial.println(" - no devices found");
  } else {
  Serial.println("Output: millis,ax,ay,az,gx,gy,gz,tempC,audioRMS");
  }
}

void loop() {
  static uint32_t lastBlink = 0;
  static uint32_t lastRetry = 0;
  static uint32_t lastScan = 0;
  static bool     lastConn = false;
  uint32_t now = millis();
  if (now - lastBlink >= 500) {
    lastBlink = now;
    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
  }

  if (!gImu) {
    // 1秒おきに初期化リトライ
    if (now - lastRetry >= 1000) {
      lastRetry = now;
      Serial.println("Retrying IMU init...");
      if (beginIMU()) {
        Serial.println("IMU initialized.");
        Serial.println("Output: millis,ax,ay,az,gx,gy,gz,tempC,audioRMS");
      }
    }
    // 5秒おきにI2Cスキャン
    if (now - lastScan >= 5000) {
      lastScan = now;
      Serial.println("I2C scan (Wire) start...");
      uint8_t found = 0;
      for (uint8_t a = 0x08; a <= 0x77; a++) {
        Wire.beginTransmission(a);
        if (Wire.endTransmission() == 0) {
          Serial.print(" - found 0x"); Serial.println(a, HEX);
          found++;
        }
      }
      if (!found) Serial.println(" - no devices found");
      Serial.println("I2C scan done.");
      #if HAS_WIRE1
      Serial.println("I2C scan (Wire1) start...");
      uint8_t found2 = 0;
      for (uint8_t a = 0x08; a <= 0x77; a++) {
        Wire1.beginTransmission(a);
        if (Wire1.endTransmission() == 0) {
          Serial.print(" - found 0x"); Serial.println(a, HEX);
          found2++;
        }
      }
      if (!found2) Serial.println(" - no devices found on Wire1");
      Serial.println("I2C scan (Wire1) done.");
      #endif
    }
    delay(100);
    return;
  }

  float ax = gImu->readFloatAccelX();
  float ay = gImu->readFloatAccelY();
  float az = gImu->readFloatAccelZ();
  float gx_dps = gImu->readFloatGyroX();
  float gy_dps = gImu->readFloatGyroY();
  float gz_dps = gImu->readFloatGyroZ();
  float tC = gImu->readTempC();

  // 10ms相当のPDMサンプルからRMSを算出（不足時は-1）
  float rms = -1.0f;
  (void)pdmConsumeRMS(PDM_FRAME_SAMPLES, rms);

  // 行を整形して各出力先に送信
  char line[192];
  int linelen = formatCsvLine(line, sizeof(line), (unsigned long)millis(),
                              ax, ay, az, gx_dps, gy_dps, gz_dps, tC, rms);
  if (linelen < 0) {
    // フォーマット失敗はスキップ
    delay(10);
    return;
  }

  // シリアルへは毎回出力（~100Hz）
  Serial.write((const uint8_t*)line, (size_t)linelen);
  Serial.write((const uint8_t*)"\r\n", 2);

  // BLEは帯域に配慮して25Hz程度に間引き
  static uint32_t lastBle = 0;
  // ペンディング状態（未送完了の本文）を維持して次ループで継続送信する
  static char     blePending[192];
  static int      blePendLen = -1; // <0: 空き、>=0: 有効長
  static int      blePendPos = 0;  // 送信済みバイト数

  // 接続状態変化時の処理（切断でペンディング破棄）
  bool conn = Bluefruit.connected();
  if (conn != lastConn) {
  lastConn = conn;
    if (!conn) { blePendLen = -1; blePendPos = 0; }
  }

  if (conn && (now - lastBle >= 100)) { // 送出間隔を100msに緩和
    lastBle = now;
    // 新しい行を開始できるのは未ペンディング時のみ。ペンディング中は続きから送る。
  if (blePendLen < 0) {
      // 現在行をペンディングに登録
      if (linelen > (int)sizeof(blePending)) linelen = sizeof(blePending);
      memcpy(blePending, line, (size_t)linelen);
      blePendLen = linelen;
      blePendPos = 0;
    }

    // 未送分を送る
    if (blePendLen >= 0 && blePendPos < blePendLen) {
      // 本文の残りを送る（部分書き込みの進捗を反映）
      size_t wrote = bleWriteSome(bleuart,
                                  (const uint8_t*)blePending + blePendPos,
                                  (size_t)(blePendLen - blePendPos),
                                  BLE_BODY_SLICE_MS);
      blePendPos += (int)wrote;
  // 連続0書き込み監視（ログなしの簡素版）
  static uint32_t zeroStart = 0;
      if (wrote == 0) {
        if (zeroStart == 0) zeroStart = millis();
        // 3秒以上進展がない場合、ペンディング行をドロップして復帰を試みる
        if (millis() - zeroStart >= 3000) {
          blePendLen = -1; // ドロップ
          blePendPos = 0;
          zeroStart = 0;
          // クールダウン（次回送信を少し遅らせる）
          lastBle = millis() + 200; // 200ms 後に再開
        }
      } else {
        zeroStart = 0; // 進捗が出たら解除
      }
    }
    // 本文をすべて送れたら改行LFを送って完了
    if (blePendLen >= 0 && blePendPos == blePendLen) {
      size_t lf = bleWriteSome(bleuart, (const uint8_t*)"\n", 1, BLE_LF_TIMEOUT_MS);
      if (lf == 1) {
        blePendLen = -1; // 完了
        blePendPos = 0;
      }
    }
  }

  delay(10); // ~100Hz
}
