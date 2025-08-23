# XIAO nRF52840 Sense Oscilloscope Visualization - Implementation Plan

## Project Structure

```
reciever/
├── src/xiao_nrf52840_sense_reciever/
│   ├── __init__.py
│   ├── __main__.py
│   ├── ble_receiver.py          # Existing BLE receiver
│   ├── data_source.py           # New: Abstract data source interface
│   ├── data_buffer.py           # New: Thread-safe circular buffer
│   ├── oscilloscope/            # New: Visualization package
│   │   ├── __init__.py
│   │   ├── app.py               # Main Dash application
│   │   ├── plots.py             # Plot components and layouts
│   │   ├── callbacks.py         # Dash callbacks for interactivity
│   │   └── assets/              # CSS/JS assets for styling
│   │       └── style.css
│   └── mock_data.py             # New: Mock data source for testing
├── tests/                       # New: Test suite
│   ├── test_data_buffer.py
│   ├── test_data_source.py
│   └── test_oscilloscope.py
└── ...
```

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1)

**Goal**: Establish data flow and basic plotting framework

#### 1.1 Data Source Abstraction

- [ ] Create `data_source.py` with abstract base class
- [ ] Implement `BleDataSource` adapter for existing BLE receiver
- [ ] Create `MockDataSource` for development/testing
- [ ] Add connection status and error handling

#### 1.2 Data Buffer System

- [ ] Implement thread-safe circular buffer in `data_buffer.py`
- [ ] Support configurable buffer size (default 1000 samples)
- [ ] Add buffer statistics (fill level, sample rate)
- [ ] Thread-safe read/write operations

#### 1.3 Basic Dash Application

- [ ] Create minimal Dash app in `oscilloscope/app.py`
- [ ] Single-plot proof of concept (accelerometer data)
- [ ] Real-time data polling from buffer
- [ ] Basic styling with CSS

**Deliverable**: Working single-plot oscilloscope with mock data

### Phase 2: Multi-Plot Interface (Week 2)

**Goal**: Complete oscilloscope interface with all sensor data

#### 2.1 Plot Components

- [ ] Create `plots.py` with reusable plot components
- [ ] Implement 4-panel layout (accel, gyro, temp, audio)
- [ ] Consistent styling and color schemes
- [ ] Responsive design for different screen sizes

#### 2.2 Interactive Controls

- [ ] Add start/stop buttons for data acquisition
- [ ] Time window selection (5s, 10s, 30s, 60s)
- [ ] Auto-scale toggle for Y-axis
- [ ] Plot visibility toggles

#### 2.3 Real-time Updates

- [ ] Implement efficient plot updates in `callbacks.py`
- [ ] Optimize for 10-20 FPS update rate
- [ ] Handle buffer underrun/overflow gracefully
- [ ] Connection status indicator

**Deliverable**: Full 4-panel oscilloscope interface

### Phase 3: Integration and Polish (Week 3)

**Goal**: Integrate with BLE receiver and add advanced features

#### 3.1 BLE Integration

- [ ] Integrate `BleDataSource` with existing receiver
- [ ] Add command-line options for oscilloscope mode
- [ ] Handle BLE connection/disconnection events
- [ ] Error recovery and auto-reconnect

#### 3.2 Advanced Features

- [ ] Data export functionality (save buffer to CSV)
- [ ] Plot zoom and pan capabilities
- [ ] Statistics overlay (min, max, mean, RMS)
- [ ] Performance monitoring and optimization

#### 3.3 Testing and Documentation

- [ ] Comprehensive test suite for all components
- [ ] Performance benchmarking
- [ ] User documentation and examples
- [ ] API documentation with type hints

**Deliverable**: Production-ready oscilloscope application

## Dependencies and Requirements

### New Dependencies

```toml
dependencies = [
    "bleak>=1.1.0",           # Existing
    "dash>=2.18.0",           # Web framework
    "plotly>=5.22.0",         # Plotting library
    "pandas>=2.2.0",          # Data manipulation
    "numpy>=1.26.0",          # Numerical operations
]

[dependency-groups]
dev = [
    "mypy>=1.17.1",           # Existing
    "pytest>=8.4.1",          # Existing
    "ruff>=0.12.10",          # Existing
    "pre-commit>=4.0.1",      # Existing
    "pytest-asyncio>=0.25.0", # Async testing
    "pytest-mock>=3.14.0",    # Mock testing
]
```

### System Requirements

- Python 3.12+
- 8GB RAM minimum (for data buffers)
- Modern web browser (Chrome, Firefox, Safari)
- BLE adapter (for live data)

## Command Line Interface

### New Command Options

```bash
# Existing CSV output mode (unchanged)
uv run xiao-nrf52840-sense-reciever --no-header --drop-missing-audio

# New oscilloscope mode
uv run xiao-nrf52840-sense-reciever --oscilloscope
uv run xiao-nrf52840-sense-reciever --oscilloscope --port 8050
uv run xiao-nrf52840-sense-reciever --oscilloscope --buffer-size 2000

# Development mode with mock data
uv run xiao-nrf52840-sense-reciever --oscilloscope --mock
```

### Configuration Options

- `--port`: Dash server port (default: 8050)
- `--host`: Bind address (default: 127.0.0.1)
- `--buffer-size`: Sample buffer size (default: 1000)
- `--update-rate`: Plot update rate in FPS (default: 15)
- `--mock`: Use mock data source for testing

## Technical Implementation Details

### Data Buffer Design

```python
class DataBuffer:
    def __init__(self, max_size: int = 1000):
        self._buffer: deque[ImuRow] = deque(maxlen=max_size)
        self._lock = threading.RLock()
        self._stats = BufferStats()

    def append(self, row: ImuRow) -> None:
        with self._lock:
            self._buffer.append(row)
            self._stats.update(row)

    def get_recent(self, count: int) -> list[ImuRow]:
        with self._lock:
            return list(self._buffer)[-count:]
```

### Dash App Structure

```python
# Main application factory
def create_app(data_source: DataSource) -> Dash:
    app = Dash(__name__)
    app.layout = create_layout()

    # Register callbacks for real-time updates
    register_callbacks(app, data_source)
    return app

# Callback for plot updates
@app.callback(
    Output('accel-plot', 'figure'),
    Input('interval-component', 'n_intervals')
)
def update_accel_plot(n):
    return create_accel_plot(buffer.get_recent(500))
```

### Performance Optimizations

#### Data Processing

- Use NumPy arrays for efficient data manipulation
- Vectorized operations for statistical calculations
- Minimal data copying in buffer operations

#### Web Interface

- Selective plot updates (only changed data)
- Client-side caching of static elements
- Efficient JSON serialization of plot data

#### Memory Management

- Circular buffer prevents unbounded growth
- Lazy loading of historical data
- Garbage collection hints for large arrays

## Testing Strategy

### Unit Tests

- `DataBuffer` thread safety and correctness
- `DataSource` implementations and error handling
- Plot component rendering and data handling

### Integration Tests

- End-to-end data flow from source to display
- BLE connection handling and recovery
- Web interface functionality and performance

### Performance Tests

- Buffer operations under high data rates
- Plot update performance with large datasets
- Memory usage patterns over extended runs

## Risk Mitigation

### Technical Risks

1. **Real-time Performance**: Mitigate with efficient algorithms and profiling
2. **Memory Usage**: Implement circular buffers and memory monitoring
3. **BLE Reliability**: Add robust error handling and reconnection logic

### Development Risks

1. **Dependency Conflicts**: Use uv for strict dependency management
2. **Browser Compatibility**: Test on major browsers, provide fallbacks
3. **Code Quality**: Maintain strict type checking and test coverage

## Success Metrics

### Performance Targets

- Plot update latency < 100ms
- Memory usage < 50MB for 1000-sample buffer
- CPU usage < 10% during normal operation
- 99% uptime for 1-hour continuous operation

### User Experience Goals

- Intuitive interface requiring no documentation
- Responsive design working on laptop/desktop screens
- Smooth real-time visualization at 15+ FPS
- Reliable operation with BLE connection handling

## Future Roadmap

### Short-term (3-6 months)

- USB Serial data source implementation
- Signal processing features (filtering, FFT)
- Data recording and playback capabilities

### Medium-term (6-12 months)

- Multi-device support
- Advanced analysis tools (statistics, triggers)
- Custom dashboard configurations

### Long-term (1+ years)

- Machine learning integration
- Remote monitoring capabilities
- Mobile app companion
