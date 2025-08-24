# XIAO nRF52840 Sense Data Logger

<!-- Language Switcher -->
**Languages**: [English](./README.md) | [日本語](./README.ja.md)

---

## 🚀 Overview

A dual-component sensor data logging system for XIAO nRF52840 Sense microcontroller that collects IMU (accelerometer/gyroscope) and PDM microphone data, providing real-time web oscilloscope visualization or CSV data export over BLE and USB Serial.

### System Architecture

- **Sender**: C++/Arduino firmware running on XIAO nRF52840 Sense
- **Receiver**: Python BLE client with web oscilloscope interface and CSV export

## 📦 Components

### [Sender (Firmware)](./sender/)
- **Hardware**: XIAO nRF52840 Sense with LSM6DS3 IMU and PDM microphone
- **Framework**: Arduino + PlatformIO
- **Output**: CSV data via BLE Nordic UART Service and USB Serial
- **Data Rate**: ~100Hz via Serial, ~25Hz via BLE

### [Receiver (Python Tool)](./receiver/)
- **Platform**: Python 3.12+ with uv package manager
- **Default Mode**: Interactive web oscilloscope with real-time sensor plots
- **CSV Mode**: Command-line data export with filtering options
- **Dependencies**: bleak (BLE), dash (web UI), plotly (visualization), pandas (data)

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

#### Web Oscilloscope (Default)
```bash
cd receiver/
uv sync                   # Install dependencies
uv run xiao-nrf52840-sense-receiver          # Start web interface at http://localhost:8050
```

#### CSV Export Mode
```bash
uv run xiao-nrf52840-sense-receiver --csv --no-header --drop-missing-audio
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

### Real-time Monitoring
- **Live Oscilloscope**: Interactive web interface for real-time sensor visualization
- **Motion Analysis**: IMU data monitoring for robotics and movement studies
- **Audio Monitoring**: Ambient sound level tracking with accelerometer context

### Data Collection & Analysis
- **CSV Data Export**: Long-term data logging with filtering and export options
- **IoT Prototyping**: Wireless sensor data collection with BLE connectivity
- **Educational Projects**: Sensor data analysis and signal processing studies

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