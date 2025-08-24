# XIAO nRF52840 Sense Data Logger

<!-- Language Switcher -->
**Languages**: [English](./README.md) | [日本語](./README.ja.md)

---

## 🚀 Overview

A dual-component sensor data logging system for XIAO nRF52840 Sense microcontroller that collects IMU (accelerometer/gyroscope) and PDM microphone data, streaming it over BLE and USB Serial in CSV format.

### System Architecture

- **Sender**: C++/Arduino firmware running on XIAO nRF52840 Sense
- **Receiver**: Python BLE client tool for data collection and visualization

## 📦 Components

### [Sender (Firmware)](./sender/)
- **Hardware**: XIAO nRF52840 Sense with LSM6DS3 IMU and PDM microphone
- **Framework**: Arduino + PlatformIO
- **Output**: CSV data via BLE Nordic UART Service and USB Serial
- **Data Rate**: ~100Hz via Serial, ~25Hz via BLE

### [Receiver (Python Tool)](./receiver/)
- **Platform**: Python 3.12+ with uv package manager
- **Features**: BLE data reception, CSV export, real-time visualization
- **Dependencies**: bleak (BLE), dash (web UI), plotly (charts)

## 🚀 Quick Start

### Prerequisites

- **Hardware**: XIAO nRF52840 Sense board
- **Software**: 
  - PlatformIO Core (firmware development)
  - Python 3.12+ with uv (data reception)
  - Bluetooth adapter (for BLE reception)

### 1. Firmware Setup

```bash
cd sender/
pio run                    # Build firmware
pio run -t upload         # Upload (requires DFU mode - double-click reset)
pio device monitor -b 115200  # Monitor serial output
```

### 2. Data Reception

```bash
cd receiver/
uv sync                   # Install dependencies
uv run xiao-nrf52840-sense-receiver --no-header --drop-missing-audio
```

## 📊 Data Format

CSV output with 9 fields:
```
millis,ax,ay,az,gx,gy,gz,tempC,audioRMS
```

- **millis**: Timestamp (milliseconds since boot)
- **ax,ay,az**: Accelerometer (g)
- **gx,gy,gz**: Gyroscope (dps)  
- **tempC**: Temperature (°C)
- **audioRMS**: Audio RMS value (10ms window, -1.0 for missing data)

## 🔧 Development

### Firmware Development
See [sender/README.md](./sender/README.md) for detailed firmware development instructions.

### Python Tool Development  
See [receiver/README.md](./receiver/README.md) for Python development guidelines and API documentation.

## 🎯 Use Cases

- **Motion Analysis**: IMU data logging for robotics and movement studies
- **Audio Monitoring**: Ambient sound level tracking with accelerometer context
- **IoT Prototyping**: Wireless sensor data collection with BLE connectivity
- **Educational Projects**: Real-time sensor data visualization and analysis

## 🛠 System Requirements

### Hardware
- XIAO nRF52840 Sense board
- USB-C cable for programming and serial communication
- Computer with Bluetooth Low Energy support

### Software
- **Firmware**: PlatformIO Core, Git
- **Data Reception**: Python 3.12+, uv package manager
- **OS Support**: Windows, macOS, Linux (BLE stack dependent)

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📞 Support

For technical support and questions:
- Check component-specific README files in `sender/` and `receiver/`
- Review hardware documentation: [XIAO nRF52840 Sense](https://wiki.seeedstudio.com/XIAO_BLE_Sense/)
- Report issues via GitHub Issues