# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Rules

- All responses must be written in Japanese.

## Project Overview

This is a dual-component XIAO nRF52840 Sense sensor data logger system:
- **Sender**: Firmware for XIAO nRF52840 Sense that collects IMU and PDM microphone data, transmits via BLE and USB Serial
- **Receiver**: Python tool that receives BLE data from the sender and outputs CSV to console/file

## Repository Structure

```
├── sender/          # PlatformIO firmware project (C++/Arduino)
├── receiver/        # Python BLE receiver tool (uv managed)
└── CLAUDE.md        # This file
```

Each subdirectory has its own CLAUDE.md with component-specific details.

## Common Development Commands

### Sender (Firmware)
```bash
cd sender/
pio run                    # Build firmware
pio run -t upload         # Upload to device (requires DFU mode)
pio device monitor -b 115200  # Monitor serial output
```

### Receiver (Python)
```bash
cd receiver/
uv sync                   # Install dependencies
uv run xiao-nrf52840-sense-reciever --no-header --drop-missing-audio
```

## System Architecture

### Data Flow
1. **Sensor Capture**: XIAO collects LSM6DS3 IMU data (~100Hz) and PDM audio RMS values
2. **BLE Transmission**: Data sent as CSV over Nordic UART Service (~25Hz)
3. **PC Reception**: Python tool receives, parses, and outputs CSV data

### Communication Protocol
- **BLE Service**: Nordic UART Service (NUS) compatible
- **Device Name**: "XIAO Sense IMU"
- **Data Format**: CSV with 9 fields: `millis,ax,ay,az,gx,gy,gz,tempC,audioRMS`
- **Connection**: Auto-restart advertising on disconnect

### Key Components
- **IMU**: LSM6DS3 accelerometer/gyroscope with dynamic address detection
- **Audio**: PDM microphone with 10ms sliding window RMS calculation
- **BLE**: Robust transmission with partial write handling and timeouts
- **Serial**: Always-active USB Serial output at full rate

## Development Notes

- Both components use strict development guidelines (see individual CLAUDE.md files)
- Sender uses PlatformIO with custom Seeed platform
- Receiver uses uv for Python package management with strict type checking
- System designed for real-time sensor data streaming with BLE bandwidth optimization
