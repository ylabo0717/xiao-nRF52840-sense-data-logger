# XIAO nRF52840 Sense Data Oscilloscope Visualization - Design Document

## Overview

This document outlines the design for a real-time oscilloscope-like visualization system for XIAO nRF52840 Sense sensor data using Plotly Dash. The system will provide interactive, real-time graphs of IMU data, temperature, and audio RMS values.

## Current Data Structure

The receiver outputs CSV data with 9 fields:

- `millis`: Timestamp in milliseconds
- `ax`, `ay`, `az`: Accelerometer data (m/s²)
- `gx`, `gy`, `gz`: Gyroscope data (rad/s)
- `tempC`: Temperature in Celsius
- `audioRMS`: Audio RMS value

Data rate: ~25Hz via BLE, ~100Hz via USB Serial

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
   - IMU Accelerometer panel (3 traces: ax, ay, az)
   - IMU Gyroscope panel (3 traces: gx, gy, gz)
   - Temperature panel (single trace)
   - Audio RMS panel (single trace)
   - Optional: Combined overview panel

### User Interface Design

```
┌─────────────────────────────────────────────────────────────┐
│ XIAO nRF52840 Sense - Real-time Oscilloscope               │
├─────────────────────────────────────────────────────────────┤
│ Controls: [●Start] [■Stop] [⚙Settings] Connection: ●Online │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────┬─────────────────────────────┐   │
│ │ Accelerometer (m/s²)    │ Gyroscope (rad/s)           │   │
│ │     ┌─────────────┐     │     ┌─────────────┐         │   │
│ │  2  │    /\  ax   │  2  │ 0.5 │     /\  gx  │  0.5    │   │
│ │  0  │   /  \      │  0  │  0  │    /  \     │   0     │   │
│ │ -2  │__/____\_____|_-2  │-0.5 │___/____\____|_-0.5    │   │
│ │     │   ay  az    │     │     │   gy  gz    │         │   │
│ └─────────────────────────┴─────────────────────────────┘   │
│ ┌─────────────────────────┬─────────────────────────────┐   │
│ │ Temperature (°C)        │ Audio RMS                   │   │
│ │     ┌─────────────┐     │     ┌─────────────┐         │   │
│ │ 25  │ ____________│ 25  │0.1  │  /\    /\   │  0.1    │   │
│ │ 20  │             │ 20  │0.05 │ /  \  /  \  │ 0.05    │   │
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

- **Latency**: < 100ms from data reception to display update
- **Buffer Size**: 1000 samples (40 seconds at 25Hz)
- **Update Rate**: 10-20 FPS for smooth visualization
- **Memory Usage**: < 50MB for data buffers

#### Configuration Options

- **Time Window**: 5s, 10s, 30s, 60s display windows
- **Auto-scale**: Enable/disable automatic Y-axis scaling
- **Plot Selection**: Show/hide individual sensor plots
- **Sampling Rate**: Display decimation for performance
- **Export**: Save current buffer to CSV file

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

- **BleDataSource**: Uses existing BLE receiver
- **MockDataSource**: Generates synthetic data for testing
- **SerialDataSource**: Future USB serial implementation

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

- **Vectorized Operations**: Use NumPy for buffer operations
- **Efficient Updates**: Only update changed plot data
- **Lazy Loading**: Load plot data only when visible

### Web Interface

- **Client-side Caching**: Reduce server load
- **Selective Updates**: Update only visible plots
- **Responsive Design**: Adapt to different screen sizes

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
