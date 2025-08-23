# XIAO nRF52840 Sense Data Oscilloscope Visualization - Design Document

## Overview

This document outlines the design for a real-time oscilloscope-like visualization system for XIAO nRF52840 Sense sensor data using Plotly Dash. The system will provide interactive, real-time graphs of IMU data, temperature, and audio RMS values.

## Current Data Structure

The receiver outputs CSV data with 9 fields:

- `millis`: Timestamp in milliseconds (device relative time, resets on device restart)
- `ax`, `ay`, `az`: Accelerometer data in g-force units (1g = 9.80665 m/s²)
- `gx`, `gy`, `gz`: Gyroscope data in degrees per second (deg/s)
- `tempC`: Temperature in Celsius
- `audioRMS`: Audio RMS value from 16-bit PDM samples (range: 0-32768, -1.0 indicates missing data)

### Data Characteristics

- **Sample Rates**: ~25Hz via BLE, ~100Hz via USB Serial
- **Missing Data**: AudioRMS = -1.0 when insufficient PDM data (startup/connection delays)
- **Timestamp**: Device-relative milliseconds, potential discontinuity at restart/overflow (~49.7 days)
- **Audio Processing**: 10ms sliding window (160 samples @ 16kHz) for RMS calculation

## System Architecture

### Core Components

1. **Data Source Interface**
   - Abstract base class for data sources
   - BLE receiver implementation
   - Future: USB Serial receiver implementation
   - Mock data source for development/testing

2. **Data Buffer Management**
   - Circular buffer for real-time data storage
   - Configurable buffer size (default: 1000 samples)
   - Thread-safe operations for concurrent read/write

3. **Dash Web Application**
   - Real-time plotting with auto-refresh
   - Multiple plot panels for different sensor groups
   - Interactive controls for display settings

4. **Plot Components**
   - IMU Accelerometer panel (3 traces: ax, ay, az) - Units: g-force
   - IMU Gyroscope panel (3 traces: gx, gy, gz) - Units: deg/s
   - Temperature panel (single trace) - Units: °C
   - Audio RMS panel (single trace) - Units: PDM counts (0-32768, gaps for -1.0)
   - Optional: Combined overview panel

### User Interface Design

```
┌─────────────────────────────────────────────────────────────┐
│ XIAO nRF52840 Sense - Real-time Oscilloscope               │
├─────────────────────────────────────────────────────────────┤
│ Controls: [●Start] [■Stop] [⚙Settings] Connection: ●Online │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────┬─────────────────────────────┐   │
│ │ Accelerometer (g)       │ Gyroscope (deg/s)           │   │
│ │     ┌─────────────┐     │     ┌─────────────┐         │   │
│ │  2  │    /\  ax   │  2  │ 100 │     /\  gx  │  100    │   │
│ │  0  │   /  \      │  0  │  0  │    /  \     │   0     │   │
│ │ -2  │__/____\_____|_-2  │-100 │___/____\____|_-100    │   │
│ │     │   ay  az    │     │     │   gy  gz    │         │   │
│ └─────────────────────────┴─────────────────────────────┘   │
│ ┌─────────────────────────┬─────────────────────────────┐   │
│ │ Temperature (°C)        │ Audio RMS (PDM counts)      │   │
│ │     ┌─────────────┐     │     ┌─────────────┐         │   │
│ │ 25  │ ____________│ 25  │5000 │  /\    /\   │  5000   │   │
│ │ 20  │             │ 20  │2500 │ /  \  /  \  │ 2500    │   │
│ │ 15  │_____________│ 15  │  0  │/____\/____\ │   0     │   │
│ └─────────────────────────┴─────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### System Architecture Diagram

#### Overall System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    XIAO nRF52840 Oscilloscope System           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌─────────────────┐    ┌───────────────┐  │
│  │   XIAO BLE   │    │  Data Reception │    │   Web Browser │  │
│  │    Device    │───▶│     Thread      │    │   (Display)   │  │
│  │              │    │   (Receiver)    │    │               │  │
│  └──────────────┘    └─────────────────┘    └───────────────┘  │
│        │                       │                      ▲        │
│        │ BLE Data Stream       │                      │        │
│        ▼                       ▼                      │        │
│  ┌──────────────┐    ┌─────────────────┐              │        │
│  │  ImuRow Data │    │  Thread-Safe    │              │        │
│  │ (9 CSV fields)│───▶│ Circular Buffer │              │        │
│  │   ~25Hz       │    │  (1000 samples) │              │        │
│  └──────────────┘    └─────────────────┘              │        │
│                               │                        │        │
│                               ▼                        │        │
│                    ┌─────────────────┐                 │        │
│                    │   Dash Web App  │─────────────────┘        │
│                    │ (Main Thread)   │                          │
│                    │   Polling @15Hz │                          │
│                    └─────────────────┘                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### Thread Architecture Detail

```
Thread 1: Data Reception (Async)          Thread 2: Web Application (Main)
┌─────────────────────────────────┐       ┌──────────────────────────────┐
│                                 │       │                              │
│  ┌─────────────────────────┐    │       │  ┌────────────────────────┐  │
│  │    BLE Data Source      │    │       │  │     Dash Server        │  │
│  │                         │    │       │  │                        │  │
│  │  async def start()      │    │       │  │  @app.callback         │  │
│  │  async def get_data()   │    │       │  │  def update_plots()    │  │
│  └─────────────────────────┘    │       │  └────────────────────────┘  │
│              │                  │       │              ▲               │
│              ▼                  │       │              │               │
│  ┌─────────────────────────┐    │       │  ┌────────────────────────┐  │
│  │   Data Processing       │    │       │  │    Plot Generation     │  │
│  │                         │    │       │  │                        │  │
│  │  parse_csv()           │    │       │  │  create_accel_plot()   │  │
│  │  validate_data()       │    │       │  │  create_gyro_plot()    │  │
│  └─────────────────────────┘    │       │  │  create_temp_plot()    │  │
│              │                  │       │  │  create_audio_plot()   │  │
│              ▼                  │       │  └────────────────────────┘  │
│  ┌─────────────────────────┐    │       │              ▲               │
│  │      Buffer Write       │    │       │              │               │
│  │                         │    │       │  ┌────────────────────────┐  │
│  │  buffer.append(row)     │◄──┼───────┼──┤     Buffer Read        │  │
│  │  threading.RLock()      │    │       │  │                        │  │
│  └─────────────────────────┘    │       │  │  buffer.get_recent()   │  │
│                                 │       │  │  threading.RLock()     │  │
└─────────────────────────────────┘       │  └────────────────────────┘  │
                                          │                              │
                                          └──────────────────────────────┘

                    ┌─────────────────────────────┐
                    │     Shared Resource         │
                    │                             │
                    │  ┌────────────────────────┐ │
                    │  │   Circular Buffer      │ │
                    │  │                        │ │
                    │  │  collections.deque     │ │
                    │  │  maxlen=1000           │ │
                    │  │  threading.RLock()     │ │
                    │  │                        │ │
                    │  │  Methods:              │ │
                    │  │  - append(row)         │ │
                    │  │  - get_recent(count)   │ │
                    │  │  - get_stats()         │ │
                    │  └────────────────────────┘ │
                    └─────────────────────────────┘
```

#### Data Flow Sequence

```
1. Data Acquisition
   XIAO Device ──BLE──▶ BLE Receiver ──parse──▶ ImuRow Objects
                                                      │
2. Buffer Management                                  ▼
   Data Reception Thread ──lock──▶ Circular Buffer ◄──lock── Web App Thread
                                       │
3. Web Interface                       ▼
   Dash Callback ──poll(@15Hz)──▶ Buffer Read ──format──▶ Plotly Graphs
                                                                  │
4. Display                                                       ▼
   Plotly Graphs ──render──▶ Web Browser ──display──▶ User Interface
```

### Technical Specifications

#### Data Flow

1. **Data Acquisition**: BLE receiver generates ImuRow objects
2. **Buffer Management**: Thread-safe circular buffer stores recent data
3. **Web Interface**: Dash app polls buffer and updates plots
4. **Display**: Plotly graphs render real-time waveforms

#### Performance Requirements

- **Latency**: Median < 100ms, Maximum < 200ms from data reception to display
- **Buffer Size**: Dynamic sizing based on time window (1500 samples for 60s @ 25Hz)
- **Update Rate**: 15 FPS for smooth visualization (66ms intervals)
- **Memory Usage**: < 50MB for data buffers and plot cache

#### Configuration Options

- **Time Window**: 5s, 10s, 30s, 60s display windows with automatic buffer sizing
- **Auto-scale**: Enable/disable automatic Y-axis scaling per plot panel
- **Plot Visibility**: Show/hide individual sensor plots to improve performance
- **Data Export**: Save current buffer or visible window to timestamped CSV
- **Settings Persistence**: Save user preferences to browser localStorage or dcc.Store

#### UI Enhancements

- **Axis Management**: Linked X-axis time synchronization across all plots
- **Missing Data Visualization**: Audio RMS gaps for -1.0 values, clear indication in plot
- **Connection Status**: Real-time BLE connection indicator with reconnection controls
- **Performance Monitoring**: Display buffer fill level, update rate, and connection quality

## Data Source Abstraction

### Interface Definition

```python
class DataSource(ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    def get_data_stream(self) -> AsyncGenerator[ImuRow, None]: ...

    @abstractmethod
    def is_connected(self) -> bool: ...
```

### Implementations

- **BleDataSource**: Wraps existing `stream_rows()` async generator with start/stop/connection status
- **MockDataSource**: Generates synthetic data for testing and development
- **SerialDataSource**: Future USB serial implementation

### Async-to-Sync Bridge Design

```python
class AsyncDataBridge:
    def __init__(self, data_source: DataSource, buffer: DataBuffer):
        self._source = data_source
        self._buffer = buffer
        self._task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
    def start_background_thread(self):
        """Start background thread with asyncio loop for data collection"""
        thread = threading.Thread(target=self._run_async_loop, daemon=True)
        thread.start()
        
    async def _data_collection_loop(self):
        """Main async loop for data collection with error recovery"""
        while True:
            try:
                async for row in self._source.get_data_stream():
                    self._buffer.append(row)
            except Exception as e:
                # Log error, wait, and attempt reconnection
                await asyncio.sleep(1.0)
```

## Security and Error Handling

### Error Handling

- **Connection Loss**: Graceful handling with auto-reconnect attempts
- **Data Corruption**: Skip invalid samples, log warnings
- **Buffer Overflow**: Circular buffer prevents memory issues
- **Network Errors**: Dash app continues with cached data

### Security Considerations

- **Local Network Only**: Dash app binds to localhost by default
- **No External Dependencies**: All data processing local
- **Input Validation**: CSV parsing with error handling

## Performance Optimizations

### Data Processing

- **Vectorized Operations**: Use NumPy for efficient buffer operations and RMS calculations
- **Smart Decimation**: Variable decimation based on time window (5s: all points, 30s+: even spacing)
- **Missing Data Handling**: Skip audioRMS = -1.0 values, create gaps in plots

### Web Interface Updates

- **Incremental Updates**: Use Plotly `extendData` for minimal data transfer
- **UI State Preservation**: Use `uirevision` to maintain user zoom/pan settings
- **Selective Rendering**: Update only visible/changed plots to reduce computation
- **Dynamic Buffer Sizing**: Adjust buffer size based on selected time window

### Plot Optimizations

- **Linked Axes**: Share X-axis across all plots, group Y-axis for IMU panels
- **Efficient Data Transfer**: Send only new data points since last update
- **Client-side Caching**: Cache plot configurations to reduce server load

## Future Enhancements

### Phase 2 Features

- **Data Recording**: Save sessions to timestamped files
- **Signal Analysis**: FFT, filtering, statistical analysis
- **Multi-device**: Support multiple XIAO devices simultaneously
- **Custom Dashboards**: User-configurable plot layouts

### Phase 3 Features

- **Machine Learning**: Real-time anomaly detection
- **Remote Monitoring**: Network-accessible interface
- **Data Fusion**: Combine multiple sensor streams
- **Export Formats**: Support for various data export formats
