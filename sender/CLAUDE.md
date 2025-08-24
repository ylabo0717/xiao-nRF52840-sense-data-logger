# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a XIAO nRF52840 Sense sensor data logger that collects IMU (LSM6DS3) accelerometer/gyroscope data and PDM microphone audio RMS values, outputting the data via both USB Serial and BLE UART as CSV format.

## Development Commands

### Build and Upload

```bash
# Build the project (compile)
pio run

# Upload firmware to device (requires DFU mode - double-click reset button)
pio run -t upload

# Upload to specific port if needed
pio run -t upload --upload-port COM5

# Clean build artifacts
pio run -t clean

# Update dependencies and platforms
pio pkg update
```

### Monitoring and Debugging

```bash
# Monitor serial output (adjust baud rate as needed)
pio device monitor -b 115200

# List available devices/ports
pio device list
```

## Hardware Architecture

### Target Board

- **Board**: Seeed Studio XIAO nRF52840 Sense
- **Framework**: Arduino
- **Platform**: Custom Seeed platform from GitHub
- **Environment**: `seeed_xiao_nrf52840_sense`

### Key Hardware Components

- **IMU**: LSM6DS3 accelerometer/gyroscope (I2C addresses 0x6A or 0x6B)
- **Microphone**: Internal PDM microphone (16kHz, 1-channel, 16-bit)
- **Connectivity**: BLE (Nordic UART Service compatible)
- **I2C**: Primary Wire interface (400kHz), optional Wire1 support

## Code Architecture

### Main Components (src/main.cpp)

1. **IMU Management**: Dynamic LSM6DS3 initialization with address detection and retry logic
2. **PDM Audio Processing**: Ring buffer for continuous audio capture with RMS calculation
3. **BLE Communication**: Robust BLE UART with partial write handling and timeout management
4. **Data Format**: CSV output with timestamped sensor fusion data

### Data Output Format

CSV fields (no header in BLE): `millis,ax,ay,az,gx,gy,gz,tempC,audioRMS`

- Serial: ~100Hz full rate
- BLE: ~25Hz (bandwidth-limited)
- Audio RMS: 10ms sliding window (160 samples @ 16kHz)

### BLE Implementation Details

- **Service**: Nordic UART Service (NUS) compatible
- **Device Name**: "XIAO Sense IMU"
- **Data Rate**: 25Hz CSV transmission with retry and timeout handling
- **Connection**: Auto-restart advertising on disconnect

### Error Handling

- IMU initialization retry every 1 second if failed
- I2C device scanning every 5 seconds during IMU failure
- BLE write timeout and recovery mechanisms
- PDM ring buffer overflow protection

## Key Dependencies

From `platformio.ini`:

- Seeed Arduino LSM6DS3 library for IMU
- Adafruit Bluefruit nRF52 libraries (included in platform)
- Arduino framework with nRF52 extensions

## Development Notes

- The firmware supports both Wire and Wire1 I2C interfaces where available
- BLE MTU and connection parameters are optimized for data throughput
- Audio processing uses interrupt-driven PDM with ring buffer for real-time performance
- Serial output always active; BLE output only when connected and notifications enabled
