# XIAO nRF52840 Sense Data Logger - Firmware

<!-- Language Switcher -->

**Languages**: [English](./README.md) | [日本語](./README.ja.md)

---

## 🚀 Overview

Firmware for XIAO nRF52840 Sense that collects IMU (LSM6DS3) accelerometer/gyroscope data and PDM microphone audio RMS values, transmitting the data via both USB Serial and BLE UART in CSV format.

### Key Features

- **Multi-sensor Data Collection**: IMU + PDM microphone with timestamp synchronization
- **Dual Output**: USB Serial (full rate ~100Hz) + BLE (optimized ~25Hz)
- **Robust BLE**: Auto-reconnection, partial write handling, timeout management
- **Dynamic Hardware Detection**: I2C address scanning for LSM6DS3 compatibility

## 🔧 Hardware Architecture

### Target Platform

- **Board**: Seeed Studio XIAO nRF52840 Sense
- **Framework**: Arduino + PlatformIO
- **Platform**: Custom Seeed platform from GitHub
- **Environment**: `seeed_xiao_nrf52840_sense`

### Hardware Components

- **IMU**: LSM6DS3 accelerometer/gyroscope (I2C addresses 0x6A or 0x6B)
- **Microphone**: Internal PDM microphone (16kHz, 1-channel, 16-bit)
- **Connectivity**: BLE Nordic UART Service compatible
- **I2C**: Primary Wire interface (400kHz), optional Wire1 support

## 📊 Data Output Format

CSV fields: `millis,ax,ay,az,gx,gy,gz,tempC,audioRMS`

- **Serial Output**: ~100Hz full rate with header
- **BLE Output**: ~25Hz bandwidth-optimized, no header
- **Audio RMS**: 10ms sliding window (160 samples @ 16kHz), -1.0 for insufficient data
- **BLE Service**: Nordic UART Service (NUS) with device name "XIAO Sense IMU"

## 🛠 Development Setup

### Prerequisites

- **Python**: 3.8+ (for PlatformIO)
- **Git**: For platform/library management
- **PlatformIO Core**: CLI-based development environment

### Installation

1. **Install PlatformIO Core** (recommended: pipx):

   ```bash
   # Install pipx if not available
   python -m pip install --user pipx
   python -m pipx ensurepath

   # Install PlatformIO
   pipx install platformio

   # Verify installation
   pio --version
   ```

2. **Alternative** (direct pip):
   ```bash
   python -m pip install --user -U platformio
   ```

### Build and Upload

```bash
# Build firmware
pio run

# Upload to device (requires DFU mode)
pio run -t upload

# Upload to specific port
pio run -t upload --upload-port COM5

# Clean build artifacts
pio run -t clean

# Update dependencies/platforms
pio pkg update
```

### Programming Mode

XIAO nRF52840 uses bootloader (DFU) mode for programming:

1. **Enter DFU Mode**: Double-click reset button rapidly
2. **Verify**: New COM port appears (`pio device list` to check)
3. **Upload**: Run upload command

### Monitoring and Debugging

```bash
# Monitor serial output
pio device monitor -b 115200

# List available devices/ports
pio device list
```

## 💻 Code Architecture

### Main Components (src/main.cpp)

1. **IMU Management**:
   - Dynamic LSM6DS3 initialization with I2C address detection
   - Retry logic for failed sensor initialization
   - I2C device scanning during sensor failure

2. **PDM Audio Processing**:
   - Ring buffer for continuous audio capture
   - RMS calculation with 10ms sliding window
   - Interrupt-driven PDM with real-time performance

3. **BLE Communication**:
   - Robust BLE UART with partial write handling
   - Timeout management and connection recovery
   - Auto-restart advertising on disconnect

4. **Data Synchronization**:
   - Timestamped sensor fusion data
   - CSV output formatting with consistent field structure

### Error Handling

- **IMU Initialization**: Retry every 1 second on failure
- **I2C Scanning**: Device discovery every 5 seconds during IMU failure
- **BLE Recovery**: Write timeout and automatic reconnection
- **Buffer Protection**: PDM ring buffer overflow prevention

## 📋 Dependencies

From `platformio.ini`:

- **Seeed Arduino LSM6DS3**: IMU sensor library
- **Adafruit Bluefruit nRF52**: BLE stack (included in platform)
- **Arduino Framework**: nRF52 extensions and core libraries

## 🔧 Configuration

### Hardware Configuration

- **I2C Speed**: 400kHz for optimal sensor performance
- **BLE MTU**: Optimized for data throughput
- **Audio Sampling**: 16kHz PDM with 10ms RMS windows

### Data Rate Optimization

- **Serial**: Full sensor rate (~100Hz) with all data
- **BLE**: Bandwidth-limited rate (~25Hz) with same data precision
- **Audio**: Continuous capture with RMS reporting at data rate

## 🚨 Troubleshooting

### Common Issues

- **PlatformIO not found**: Restart terminal/IDE after installation, verify PATH
- **Board not detected**: Enter DFU mode (double-click reset), check with `pio device list`
- **Upload failure**: Try different USB port/cable, verify DFU mode, use `--upload-port`
- **Initial build failure**: Check network/proxy settings, run `pio pkg update`
- **Permission errors**: Run as administrator or try different USB port

### Hardware Issues

- **No IMU data**: Check I2C connections, verify LSM6DS3 power
- **No audio data**: PDM microphone may need initialization delay
- **BLE connection issues**: Verify device advertising, check BLE stack on receiver

## 📚 Reference Documentation

- [PlatformIO Core (CLI)](https://docs.platformio.org/en/latest/core/index.html)
- [Seeed XIAO nRF52840 Sense](https://wiki.seeedstudio.com/XIAO_BLE_Sense/)
- [LSM6DS3 Datasheet](https://www.st.com/resource/en/datasheet/lsm6ds3.pdf)
- [Nordic UART Service Specification](https://developer.nordicsemi.com/nRF_Connect_SDK/doc/latest/nrf/libraries/bluetooth_services/services/nus.html)

## ⚡ Performance Notes

- **Serial Output**: Always active, full sensor rate
- **BLE Output**: Only when connected and notifications enabled
- **Audio Processing**: Interrupt-driven for real-time performance
- **Memory Usage**: Ring buffer design minimizes RAM requirements
- **Power Efficiency**: Optimized BLE parameters for battery operation
