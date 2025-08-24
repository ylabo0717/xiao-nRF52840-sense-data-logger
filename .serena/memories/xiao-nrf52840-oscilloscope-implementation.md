# XIAO nRF52840 Sense Data Logger - Oscilloscope Implementation Summary

## Project Overview
Dual-component sensor data logger system with XIAO nRF52840 Sense hardware and Python receiver application. Successfully implemented comprehensive oscilloscope web interface with data recording capabilities.

## Key Features Implemented

### 1. Data Recorder System (`data_recorder.py`)
- **RecordFileWriter**: Thread-safe CSV file operations with internal buffering
- **RecordingWorkerThread**: Background thread for file I/O at 50Hz polling
- **RecorderManager**: Session coordination and management
- **Design Principles**: Data collection never blocked by recording operations
- **Output Format**: CSV files with companion .meta.json metadata

### 2. Enhanced DataBuffer (`ble_receiver.py`)
- **Index-based Access**: `get_since_index()` method for efficient recording monitoring
- **Thread-safe Operations**: RLock protection for concurrent access
- **Circular Buffer**: Automatic overflow handling with drop detection
- **Statistics Tracking**: Sample rate and fill level monitoring

### 3. Oscilloscope Web Interface (`oscilloscope/app.py`)
- **Real-time Visualization**: Multi-sensor plots updated at 15Hz
- **Recording Controls**: Start/Stop recording via web UI
- **Connection Status**: Visual indicators for BLE connection state
- **Buffer Management**: Thread-safe data flow from BLE to UI

### 4. CLI Integration (`__init__.py`)
- **Unified Command Interface**: `--oscilloscope` flag for web UI mode
- **Data Source Selection**: `--mock` flag for testing without BLE device
- **Port Configuration**: `--port` option for server customization
- **Clear Error Handling**: No confusing auto-fallbacks between BLE/Mock

## Architecture Highlights

### Thread Safety & Performance
- **RLock Usage**: Prevents deadlocks in reentrant access scenarios
- **Non-blocking Design**: UI updates never block data collection
- **Efficient Polling**: 50Hz background thread for file operations
- **Index-based Tracking**: Minimal memory overhead for recording

### Data Flow
```
BLE Device → DataSource → DataBuffer → [UI Thread + Recording Thread]
                                    ↓              ↓
                              Web Interface    CSV Files
```

### Error Resolution History
1. **Buffer Synchronization**: Fixed UnboundLocalError in connection status logic
2. **Threading Deadlock**: Resolved by switching from Lock to RLock
3. **Auto-fallback Removal**: Eliminated confusion between real/test data
4. **Import/Type Issues**: Fixed module imports and type annotations

## File Structure
```
receiver/
├── src/xiao_nrf52840_sense_receiver/
│   ├── __init__.py              # CLI entry point with oscilloscope integration
│   ├── ble_receiver.py          # Enhanced DataBuffer + BLE/Mock sources
│   ├── data_recorder.py         # Complete recording system (NEW)
│   └── oscilloscope/
│       ├── app.py              # Web interface with recording controls
│       └── plots.py            # Visualization components
├── scripts/
│   └── ble_diagnostics.py     # BLE troubleshooting tool
└── recordings/                 # Output directory for recorded data
```

## Usage Examples

### Real Device Connection
```bash
uv run xiao-nrf52840-sense-receiver --oscilloscope --port 8050
```

### Testing Mode
```bash
uv run xiao-nrf52840-sense-receiver --oscilloscope --mock --port 8050
```

### BLE Diagnostics
```bash
python scripts/ble_diagnostics.py
```

## Technical Specifications

### Data Format
- **CSV Header**: `millis,ax,ay,az,gx,gy,gz,tempC,audioRMS`
- **Sample Rate**: ~25Hz over BLE, up to 100Hz via USB Serial
- **Precision**: 6 decimal places for acceleration/gyro, 2 for temperature
- **Metadata**: JSON sidecar with session info and statistics

### Recording Features
- **Session Management**: Automatic timestamp-based filenames
- **Directory Organization**: Date-based folder structure (YYYY-MM-DD)
- **Statistics Tracking**: Total samples, duration, average sample rate
- **Buffer Size**: Configurable, defaults to 100 samples (~4 seconds at 25Hz)

### Web Interface
- **Update Rate**: 15Hz for smooth real-time visualization
- **Buffer Display**: Last 500 data points shown
- **Connection Indicators**: Visual status with startup phase detection
- **Recording Status**: Real-time sample count and file size display

## Design Principles Followed

1. **Separation of Concerns**: Clear boundaries between data collection, visualization, and recording
2. **Thread Safety**: All shared resources protected with appropriate locking
3. **Non-blocking Operations**: UI/recording never interferes with data collection
4. **Error Transparency**: Clear error messages with actionable troubleshooting
5. **Testability**: Mock data source for development/testing without hardware

## Performance Characteristics
- **Memory Usage**: Circular buffer with configurable size limits
- **CPU Impact**: Minimal overhead from background threads
- **I/O Efficiency**: Batched writes with configurable buffer flushing
- **Network Load**: ~25Hz update rate sustainable over BLE

## Integration Status
- ✅ CLI integration complete
- ✅ Recording system implemented
- ✅ Thread safety verified
- ✅ Error handling robust
- ✅ File organization cleaned
- ✅ Type checking passed
- ✅ Pre-commit hooks satisfied

This implementation provides a complete, production-ready solution for real-time sensor data visualization and recording from XIAO nRF52840 Sense devices.
