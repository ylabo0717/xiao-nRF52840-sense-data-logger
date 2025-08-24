/**
 * @file main.cpp
 * @brief XIAO nRF52840 Sense sensor data logger with BLE and USB Serial output
 * 
 * This firmware collects IMU data from LSM6DS3 sensor and PDM microphone RMS values,
 * transmitting the data as CSV format over both USB Serial and BLE UART.
 * The system is designed for real-time sensor data streaming with BLE bandwidth optimization.
 */

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_TinyUSB.h>
#include "LSM6DS3.h"  // Seeed_Arduino_LSM6DS3
#include <PDM.h>       // Internal PDM microphone (bundled with Adafruit nRF52 core)
#include <math.h>      // sqrt
#include <bluefruit.h> // BLE (Adafruit Bluefruit nRF52)

static const uint32_t SERIAL_BAUD = 115200;

// I2C addresses (typically 0x6A, sometimes 0x6B)
static const uint8_t ADDR1 = 0x6A;
static const uint8_t ADDR2 = 0x6B;

// Dynamically selected IMU instance holder
LSM6DS3* gImu = nullptr;
uint8_t gImuAddr = 0;

// BLE UART service
BLEUart bleuart; // Appears as serial interface to host

// Reference for secondary I2C if available (ignored in environments where it doesn't exist)
#if defined(PIN_WIRE1_SDA) && defined(PIN_WIRE1_SCL)
extern TwoWire Wire1;
#define HAS_WIRE1 1
#else
#define HAS_WIRE1 0
#endif

// --- BLE Safe Transmission Utility -----------------------------------------
// BLEUart write() may return partial writes/0, so we ensure complete transmission.
// Returns false if unable to send within timeoutMs (for decisions like skipping newlines).
static const uint32_t BLE_BODY_TIMEOUT_MS = 600; // Body transmission allowance (future extension, currently unused)
static const uint32_t BLE_LF_TIMEOUT_MS   = 100; // LF transmission allowance
static const uint32_t BLE_BODY_SLICE_MS   = 120; // Time budget for single transmission attempt

/**
 * @brief Attempts to write as much data as possible within the given time budget
 * @param uart BLE UART service instance
 * @param buf Buffer containing data to write
 * @param len Length of data to write
 * @param budgetMs Time budget in milliseconds for the write operation
 * @return Number of bytes actually written (can be 0)
 * 
 * Design intent: BLE write operations can be unreliable due to buffer limitations
 * and connection state. This function implements a robust retry mechanism with
 * exponential backoff to maximize data throughput while respecting timing constraints.
 */
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

/**
 * @brief Formats sensor data into CSV line format (body only, no newline)
 * @param dst Destination buffer
 * @param dstsz Size of destination buffer
 * @param ts Timestamp in milliseconds
 * @param ax Accelerometer X axis (g)
 * @param ay Accelerometer Y axis (g)
 * @param az Accelerometer Z axis (g)
 * @param gx_dps Gyroscope X axis (degrees per second)
 * @param gy_dps Gyroscope Y axis (degrees per second)
 * @param gz_dps Gyroscope Z axis (degrees per second)
 * @param tC Temperature in Celsius
 * @param rms Audio RMS value
 * @return Number of characters written, or -1 on error
 * 
 * Design intent: Creates a standardized CSV format for sensor fusion data.
 * The format is designed to be compatible with data analysis tools while
 * minimizing bandwidth usage over BLE connection.
 */
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
    // Truncate at end
    n = (int)dstsz - 1;
    dst[n] = '\0';
  }
  return n;
}

/**
 * @brief Initializes IMU with dynamic I2C address detection
 * @return true if initialization successful, false otherwise
 * 
 * Design intent: LSM6DS3 sensors can have different I2C addresses depending
 * on hardware configuration. This function implements a robust initialization
 * strategy that tries both common addresses (0x6A and 0x6B) to ensure
 * compatibility across different hardware revisions and configurations.
 */
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

// ==== PDM (Internal Microphone) ====
// Assumes 16kHz, 1ch, 16bit. Stores in ring buffer via onReceive callback.
static constexpr uint32_t PDM_SR = 16000;
static constexpr size_t   PDM_FRAME_SAMPLES = 160;   // Equivalent to 10ms
static constexpr size_t   PDM_RING_SAMPLES  = 4096;  // Approximately 256ms buffer
static int16_t            gPdmRing[PDM_RING_SAMPLES];
static volatile size_t    gPdmWrite = 0;
static volatile size_t    gPdmRead  = 0;

/**
 * @brief PDM data reception callback - stores audio data in ring buffer
 * 
 * Design intent: This interrupt-driven callback ensures continuous audio capture
 * without blocking the main loop. The ring buffer implementation provides overflow
 * protection by dropping oldest data when buffer is full, ensuring real-time
 * performance is maintained even under high system load.
 */
void onPDMdata() {
  int bytes = PDM.available();
  if (bytes <= 0) return;
  // Read into temporary buffer (bytes should be even number)
  static int16_t tmp[512];
  int toRead = bytes;
  if (toRead > (int)sizeof(tmp)) toRead = (int)sizeof(tmp);
  int nread = PDM.read(tmp, toRead);
  if (nread <= 0) return;
  size_t samples = (size_t)nread / sizeof(int16_t);
  // Copy to ring buffer (simplified implementation for interrupt context)
  for (size_t i = 0; i < samples; ++i) {
    gPdmRing[gPdmWrite] = tmp[i];
    gPdmWrite = (gPdmWrite + 1) % PDM_RING_SAMPLES;
    // On overflow, advance read pointer to drop oldest data
    if (gPdmWrite == gPdmRead) {
      gPdmRead = (gPdmRead + 1) % PDM_RING_SAMPLES;
    }
  }
}

/**
 * @brief Consumes samples from ring buffer and calculates RMS
 * @param needSamples Number of samples required for RMS calculation
 * @param outRms Reference to store calculated RMS value
 * @return true if sufficient samples available and RMS calculated, false otherwise
 * 
 * Design intent: Implements sliding window RMS calculation for audio level monitoring.
 * The 10ms window (160 samples at 16kHz) provides good balance between responsiveness
 * and noise reduction. DC removal is omitted for simplicity as RMS naturally
 * emphasizes AC components for audio level measurement.
 */
bool pdmConsumeRMS(size_t needSamples, float &outRms) {
  // Calculate available samples
  size_t avail = (gPdmWrite + PDM_RING_SAMPLES - gPdmRead) % PDM_RING_SAMPLES;
  if (avail < needSamples) return false;
  // Calculate sum of squares (DC removal omitted for simplicity)
  double sumSq = 0.0;
  for (size_t i = 0; i < needSamples; ++i) {
    int16_t s = gPdmRing[gPdmRead];
    gPdmRead = (gPdmRead + 1) % PDM_RING_SAMPLES;
    sumSq += (double)s * (double)s;
  }
  outRms = (float)sqrt(sumSq / (double)needSamples);
  return true;
}

/**
 * @brief Arduino setup function - initializes hardware and services
 * 
 * Design intent: Implements a comprehensive initialization sequence that handles
 * multiple potential failure modes gracefully. The setup prioritizes getting
 * basic functionality (Serial, BLE advertising) working even if some components
 * fail, ensuring the system remains accessible for debugging and data collection.
 * 
 * Key initialization steps:
 * 1. Basic GPIO setup (LED indicator)
 * 2. Serial communication with timeout for headless operation
 * 3. I2C bus initialization with multiple wire support
 * 4. PDM microphone setup with error handling
 * 5. BLE stack initialization with optimized parameters
 * 6. IMU initialization with fallback I2C scanning
 */
void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  Serial.begin(SERIAL_BAUD);
  unsigned long start = millis();
  while (!Serial && (millis() - start < 3000)) { delay(10); }

  Serial.println();
  Serial.println("=== XIAO nRF52840 Sense IMU (Seeed LSM6DS3) ===");
  Serial.print("Build: "); Serial.print(__DATE__); Serial.print(" "); Serial.println(__TIME__);
  // I2C pin information
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

  // PDM initialization (16kHz, 1ch)
  PDM.onReceive(onPDMdata);
  // Some implementations allow gain specification (ignored on some platforms)
  #ifdef PDM_HAS_SET_GAIN
  PDM.setGain(20);
  #endif
  if (!PDM.begin(1, PDM_SR)) {
    Serial.println("WARN: PDM begin failed");
  }

  // BLE initialization (CSV output via UART service)
  // Maximize bandwidth (wide ATT MTU/data length/ConnParam): mitigates bulk notification congestion
  Bluefruit.configPrphBandwidth(BANDWIDTH_MAX);
  Bluefruit.begin();
  Bluefruit.setName("XIAO Sense IMU");
  Bluefruit.setTxPower(4); // Range approximately 0-8
  bleuart.begin();
  Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
  Bluefruit.Advertising.addTxPower();
  Bluefruit.Advertising.addService(bleuart);
  Bluefruit.ScanResponse.addName();
  Bluefruit.Advertising.restartOnDisconnect(true);
  Bluefruit.Advertising.setInterval(32, 244); // 20ms-152.5ms
  Bluefruit.Advertising.setFastTimeout(30);
  Bluefruit.Advertising.start(0);

  // Recommended connection interval range
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

/**
 * @brief Arduino main loop - handles sensor data collection and transmission
 * 
 * Design intent: Implements a robust main loop that handles multiple concurrent
 * tasks with proper error recovery and state management. The loop prioritizes
 * system reliability and data continuity over performance optimization.
 * 
 * Key operations:
 * 1. LED heartbeat indication (500ms blink)
 * 2. IMU recovery with periodic retry and I2C scanning
 * 3. Sensor data acquisition (IMU + PDM microphone)
 * 4. Dual-channel data output (Serial at full rate, BLE at reduced rate)
 * 5. BLE transmission state management with timeout handling
 * 
 * The loop runs at approximately 100Hz, with BLE output throttled to ~25Hz
 * to respect bandwidth limitations while maintaining real-time Serial output.
 */
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
    // Initialization retry every 1 second
    if (now - lastRetry >= 1000) {
      lastRetry = now;
      Serial.println("Retrying IMU init...");
      if (beginIMU()) {
        Serial.println("IMU initialized.");
        Serial.println("Output: millis,ax,ay,az,gx,gy,gz,tempC,audioRMS");
      }
    }
    // I2C scan every 5 seconds
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

  // Calculate RMS from PDM samples equivalent to 10ms (returns -1 if insufficient)
  float rms = -1.0f;
  (void)pdmConsumeRMS(PDM_FRAME_SAMPLES, rms);

  // Format line and transmit to each output destination
  char line[192];
  int linelen = formatCsvLine(line, sizeof(line), (unsigned long)millis(),
                              ax, ay, az, gx_dps, gy_dps, gz_dps, tC, rms);
  if (linelen < 0) {
    // Skip on format failure
    delay(10);
    return;
  }

  // Output to Serial every time (~100Hz)
  Serial.write((const uint8_t*)line, (size_t)linelen);
  Serial.write((const uint8_t*)"\r\n", 2);

  // BLE throttled to approximately 25Hz considering bandwidth
  static uint32_t lastBle = 0;
  // Maintain pending state (unsent body) and continue transmission in next loop
  static char     blePending[192];
  static int      blePendLen = -1; // <0: empty, >=0: valid length
  static int      blePendPos = 0;  // Bytes already sent

  // Handle connection state changes (discard pending on disconnect)
  bool conn = Bluefruit.connected();
  if (conn != lastConn) {
  lastConn = conn;
    if (!conn) { blePendLen = -1; blePendPos = 0; }
  }

  if (conn && (now - lastBle >= 100)) { // Relax transmission interval to 100ms
    lastBle = now;
    // Can start new line only when not pending. During pending, continue from where left off.
  if (blePendLen < 0) {
      // Register current line as pending
      if (linelen > (int)sizeof(blePending)) linelen = sizeof(blePending);
      memcpy(blePending, line, (size_t)linelen);
      blePendLen = linelen;
      blePendPos = 0;
    }

    // Send unsent portion
    if (blePendLen >= 0 && blePendPos < blePendLen) {
      // Send remaining body (reflecting partial write progress)
      size_t wrote = bleWriteSome(bleuart,
                                  (const uint8_t*)blePending + blePendPos,
                                  (size_t)(blePendLen - blePendPos),
                                  BLE_BODY_SLICE_MS);
      blePendPos += (int)wrote;
      // Monitor consecutive zero writes (simplified version without logging)
      static uint32_t zeroStart = 0;
      if (wrote == 0) {
        if (zeroStart == 0) zeroStart = millis();
        // If no progress for 3+ seconds, drop pending line and attempt recovery
        if (millis() - zeroStart >= 3000) {
          blePendLen = -1; // Drop
          blePendPos = 0;
          zeroStart = 0;
          // Cooldown (delay next transmission slightly)
          lastBle = millis() + 200; // Resume after 200ms
        }
      } else {
        zeroStart = 0; // Clear when progress is made
      }
    }
    // Once all body is sent, send newline LF to complete
    if (blePendLen >= 0 && blePendPos == blePendLen) {
      size_t lf = bleWriteSome(bleuart, (const uint8_t*)"\n", 1, BLE_LF_TIMEOUT_MS);
      if (lf == 1) {
        blePendLen = -1; // Complete
        blePendPos = 0;
      }
    }
  }

  delay(10); // ~100Hz
}
