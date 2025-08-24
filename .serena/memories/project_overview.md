# XIAO nRF52840 Sense Data Logger - Project Overview

## Purpose

Dual-component sensor data logging system for XIAO nRF52840 Sense microcontroller:

- **Sender**: C++/Arduino firmware that collects IMU and PDM microphone data, transmits via BLE and USB Serial
- **Receiver**: Python tool that receives BLE data and outputs CSV data to console/file

## Tech Stack

### Sender (Firmware)

- Language: C++/Arduino
- Platform: PlatformIO with custom Seeed platform
- Hardware: XIAO nRF52840 Sense with LSM6DS3 IMU and PDM microphone
- Communication: BLE (Nordic UART Service) + USB Serial

### Receiver (Python)

- Language: Python 3.12+
- Package Manager: uv (strict requirement, no pip allowed)
- Dependencies: bleak (BLE), dash (3.2.0+), plotly (6.3.0+), pandas (2.3.2+)
- Architecture: async BLE receiver with planned Dash web visualization

## Data Flow

1. XIAO collects LSM6DS3 IMU data (~100Hz) and PDM audio RMS values
2. Data transmitted as CSV over BLE Nordic UART Service (~25Hz)
3. Python receiver parses and outputs CSV: `millis,ax,ay,az,gx,gy,gz,tempC,audioRMS`

## Current Implementation Status

- **Sender**: Complete firmware with BLE transmission and USB Serial output
- **Receiver**: Basic BLE receiver with CSV output functional
- **Visualization**: Oscilloscope interface planned but not yet implemented

## Key Design Considerations

- Real-time sensor data streaming with BLE bandwidth optimization
- Robust BLE connection handling with auto-reconnect
- Thread-safe data buffering for visualization
- Audio RMS uses -1.0 for missing/insufficient data
- Device uses relative timestamps (millis since boot, ~49.7 day overflow)
