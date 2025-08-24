# XIAO nRF52840 Sense Data Logger - Receiver

<!-- Language Switcher -->
**Languages**: [English](./README.md) | [日本語](./README.ja.md)

---

## 🚀 Overview

Python BLE receiver tool that collects sensor data transmitted by XIAO nRF52840 Sense via BLE (Nordic UART Service compatible) and provides real-time oscilloscope visualization or CSV output. Uses `bleak` library for cross-platform BLE communication on Windows, macOS, and Linux.

### Key Features

- **Cross-platform BLE Support**: Windows, macOS, Linux via bleak library
- **Real-time Oscilloscope**: Interactive web-based visualization with live sensor plots
- **CSV Data Export**: Stream processing with configurable filtering and console output
- **Robust Connection Handling**: Auto-reconnection and timeout management
- **Flexible Output Modes**: Web oscilloscope (default) or CSV export mode
- **Developer Tools**: Type checking, linting, testing framework integration

## 🛠 Installation and Setup

### Prerequisites

- **Python**: 3.12+ (required for type hints and modern async features)
- **Bluetooth**: BLE-capable adapter and enabled system Bluetooth
- **Operating System**: Windows, macOS, or Linux with BLE support

### 1. Install uv Package Manager

uv is a fast Python package and project management tool. Choose your platform:

**Windows (PowerShell)**:
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS/Linux**:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Verify Installation**:
```bash
uv --version
```

### 2. Project Setup

Synchronize virtual environment and dependencies from the project root:

```bash
# Navigate to receiver directory
cd receiver/

# Install dependencies and create virtual environment
uv sync
```

This creates an isolated Python environment with all required dependencies including:
- `bleak`: Cross-platform BLE library
- `dash`: Web application framework for oscilloscope interface
- `plotly`: Interactive plotting library for real-time visualization
- `pandas`: Data manipulation and analysis

### 3. Usage Methods

#### Method 1: Local Development (Recommended)

Run from project virtual environment:

```bash
# Default usage - start web oscilloscope
uv run xiao-nrf52840-sense-receiver

# CSV output mode - receive data with clean output
uv run xiao-nrf52840-sense-receiver --csv --no-header --drop-missing-audio

# Oscilloscope with custom port
uv run xiao-nrf52840-sense-receiver --port 9000

# CSV mode with timeout protection - exit if no data for 5 seconds
uv run xiao-nrf52840-sense-receiver --csv --idle-timeout 5

# Save CSV data to file
uv run xiao-nrf52840-sense-receiver --csv --no-header > sensor_data.csv

# Specify device address directly (skip scanning)
uv run xiao-nrf52840-sense-receiver --address "12:34:56:78:9A:BC"
```

#### Method 2: Global Tool Installation

Install as system-wide tool (one-time setup):

```bash
# Install tool globally from current directory
uv tool install .

# Run from anywhere after installation
uvx xiao-nrf52840-sense-receiver                                    # Start oscilloscope
uvx xiao-nrf52840-sense-receiver --csv --no-header --drop-missing-audio
uvx xiao-nrf52840-sense-receiver --csv --idle-timeout 10
```

## ⚙️ Command Line Options

| Option | Description | Default | Example |
|--------|-------------|---------|----------|
| `--csv` | Enable CSV output mode | Oscilloscope mode | `--csv` |
| `--address <MAC>` | Direct BLE address (skip scanning) | Auto-discover | `--address "12:34:56:78:9A:BC"` |
| `--device-name <NAME>` | Target device name for scanning | `"XIAO Sense IMU"` | `--device-name "My Sensor"` |
| `--scan-timeout <sec>` | BLE scan timeout in seconds | 10.0 | `--scan-timeout 15` |
| `--port <number>` | Web server port for oscilloscope | 8050 | `--port 9000` |
| `--mock` | Use mock data (no BLE device needed) | Real BLE data | `--mock` |
| `--no-header` | Suppress CSV header (CSV mode only) | Include header | `--no-header` |
| `--drop-missing-audio` | Filter audioRMS=-1.0 (CSV mode only) | Include all | `--drop-missing-audio` |
| `--idle-timeout <sec>` | Exit if no data for N seconds | Unlimited | `--idle-timeout 30` |

## 🔧 System Requirements

### Windows
- **Bluetooth**: System Bluetooth enabled in Settings
- **Location Services**: Must be enabled (required for BLE scanning)
- **Execution**: Local PowerShell (Remote Desktop may cause issues)
- **Environment**: Native Windows (not WSL/virtualization)
- **Drivers**: Bluetooth adapter properly recognized
- **Device State**: XIAO device disconnected and advertising

### macOS
- **Bluetooth**: System Bluetooth enabled
- **Permissions**: Allow Terminal/IDE Bluetooth access when prompted
- **Device State**: XIAO device disconnected and advertising

### Linux
- **Bluetooth**: BlueZ stack installed and running
- **Permissions**: User in `bluetooth` group or run with appropriate permissions
- **Device State**: XIAO device disconnected and advertising

## 🚑 Troubleshooting

### Common Connection Issues

**Error: `Failed to start scanner. Is Bluetooth turned on?`**
- Verify system Bluetooth is enabled
- **Windows**: Enable Location Services (required for BLE scanning)
- Check Bluetooth adapter status in Device Manager
- Try direct connection with `--address` if MAC address is known

**Error: `Target device not found`**
- Verify device is advertising (check XIAO board status)
- Ensure device name matches (use `--device-name` if customized)
- Increase scan timeout: `--scan-timeout 20`
- Move devices closer together
- Restart XIAO device advertising

**Connection drops frequently**
- Check BLE interference from other devices
- Verify power supply stability on XIAO device
- Use `--idle-timeout` to handle expected disconnections
- Check distance between devices

### Performance Issues

**Slow data reception**
- BLE connection parameters may need optimization
- Check for system Bluetooth stack performance
- Verify XIAO device battery level

**Missing audio data (audioRMS = -1.0)**
- Normal behavior when insufficient audio samples
- Use `--drop-missing-audio` to filter these rows
- Audio processing requires 160 samples minimum

## 📊 Data Format

The receiver processes CSV data with the following structure:

```
millis,ax,ay,az,gx,gy,gz,tempC,audioRMS
```

| Field | Description | Unit | Range |
|-------|-------------|------|-------|
| `millis` | Timestamp since device boot | ms | 0 to ~49.7 days |
| `ax,ay,az` | Accelerometer X,Y,Z | g | ±16g |
| `gx,gy,gz` | Gyroscope X,Y,Z | dps | ±2000 dps |
| `tempC` | Temperature | °C | Device dependent |
| `audioRMS` | Audio RMS level | - | ≥0.0 or -1.0 (missing) |

## 🔌 BLE Protocol Details

**Nordic UART Service (NUS) UUIDs**:
- **Service**: `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
- **TX Characteristic** (device→receiver): `6e400003-b5a3-f393-e0a9-e50e24dcca9e`
- **RX Characteristic** (receiver→device): `6e400002-b5a3-f393-e0a9-e50e24dcca9e` (unused)

**Data Transmission**:
- **Format**: CSV lines terminated with `\n`
- **Fragmentation**: BLE notifications may split lines; receiver reassembles
- **Rate**: ~25Hz from XIAO device via BLE

## 📝 Development

### Code Quality Tools

```bash
# Format code
uv run --frozen ruff format .

# Lint code
uv run --frozen ruff check .

# Type checking
uv run --frozen pyright

# Run tests
uv run --frozen pytest
```

### Development Guidelines

- **Package Management**: ONLY use `uv`, never `pip`
- **Type Hints**: Required for all public functions
- **Documentation**: Google-style docstrings for public APIs
- **Testing**: Write tests for new features and bug fixes
- **Logging**: Use Python logging module, no `print()` statements

### Adding Dependencies

```bash
# Add runtime dependency
uv add package-name

# Add development dependency
uv add --dev package-name

# Upgrade specific package
uv add package-name --upgrade-package package-name
```

## 📚 Reference Documentation

- [bleak Documentation](https://bleak.readthedocs.io/): Python BLE library
- [Nordic UART Service](https://developer.nordicsemi.com/nRF_Connect_SDK/doc/latest/nrf/libraries/bluetooth_services/services/nus.html): BLE protocol specification
- [uv Documentation](https://docs.astral.sh/uv/): Package manager guide
- [Python asyncio](https://docs.python.org/3/library/asyncio.html): Asynchronous programming

## 🚀 Current Features & Future Enhancements

### ✅ Current Features
- **Real-time Oscilloscope**: Interactive web-based visualization with live sensor plots
- **CSV Data Export**: Configurable stream processing and file output
- **Cross-platform BLE**: Windows, macOS, Linux support via bleak
- **Mock Data Mode**: Testing without physical device

### 🔮 Future Enhancements
- **Enhanced Visualization**: Additional plot types and analysis tools
- **Data Analysis Tools**: Built-in signal processing and filtering
- **Multiple Device Support**: Concurrent data collection from multiple sensors
- **Database Integration**: Direct logging to time-series databases
- **Mobile App**: Companion mobile application for monitoring