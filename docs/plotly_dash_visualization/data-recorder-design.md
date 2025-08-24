# Data Recorder Feature - Design and Implementation Plan

## Overview

The Data Recorder feature enables real-time capture and storage of sensor data from the XIAO nRF52840 Sense oscilloscope interface. Users can start/stop recording sessions and export collected data to CSV files for offline analysis.

## Feature Requirements

### Functional Requirements

1. **Recording Control**
   - Start/Stop recording with UI buttons
   - Visual indication of recording status
   - Display of recording duration and sample count
   - Automatic filename generation with timestamp

2. **Data Storage**
   - Real-time CSV file writing during recording
   - Configurable recording duration (continuous or time-limited)
   - Buffer-to-file synchronization without data loss
   - File format compatible with existing CSV output

3. **File Management**
   - Organized storage in dedicated recordings directory
   - Automatic filename with ISO timestamp format
   - Optional user-specified filename prefix
   - File size and duration limits for safety

4. **User Interface**
   - Recording controls in oscilloscope interface
   - Recording status indicators and progress
   - Download/export buttons for completed recordings
   - Recording session management

### Non-Functional Requirements

1. **Performance**
   - Minimal impact on real-time visualization
   - Efficient file I/O with buffered writes
   - Memory usage bounded regardless of recording duration

2. **Reliability**
   - Data integrity during recording
   - Graceful handling of disk space issues
   - Recovery from interrupted recordings

3. **Usability**
   - One-click recording start/stop
   - Clear visual feedback for recording state
   - Easy access to recorded files

## System Architecture

### Data Flow and Threading Model

**Critical Design Principle**: Data collection must NEVER be blocked by recording operations.

```
[XIAO Device] --BLE--> [Data Collection Thread] --> [DataBuffer] --> [UI Thread]
                            (Highest Priority)           ↓
                                              [Index-based Access API]
                                                        ↓
                                             [Recording Worker Thread]
                                                        ↓
                                               [RecordFileWriter]
                                               (Sync I/O + Buffering)
```

### Threading Architecture

1. **Data Collection Thread** (Existing - Highest Priority)
   - Receives BLE data from XIAO device
   - Writes directly to DataBuffer with lock-free append
   - **MUST NEVER BE BLOCKED** by recording operations
   - Real-time operation at ~25Hz

2. **UI Update Thread** (Existing - Medium Priority)  
   - Reads from DataBuffer for visualization
   - Updates Plotly graphs at 15 FPS
   - Non-blocking buffer access

3. **Recording Worker Thread** (New - Low Priority)
   - Dedicated thread for file writing operations
   - Uses synchronous I/O with internal buffering
   - Communicates via thread-safe queue (no additional event loops)
   - Timer-based polling every 10-20ms for new data

### Component Overview

```text
┌─────────────────────────────────────────────────────────┐
│                 Oscilloscope UI                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │   Plots     │  │  Controls   │  │    Recorder     │  │
│  │             │  │             │  │    Panel        │  │
│  └─────────────┘  └─────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│                 Data Recorder                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  Recorder    │  │ Recording    │  │  Record      │   │
│  │  Manager     │  │ Worker Thread│  │ File Writer  │   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│              Enhanced Data Buffer                       │
│    (with Index-based Access: get_since_index())        │
└─────────────────────────────────────────────────────────┘
```

### Core Components

#### 1. RecorderManager Class
Central coordinator for recording operations (simplified from design review):

```python
class RecorderManager:
    def __init__(self, buffer: DataBuffer, output_dir: Path):
        self._buffer = buffer
        self._output_dir = output_dir
        self._worker_thread: Optional[RecordingWorkerThread] = None
        self._is_recording = False
        
    def start_recording(self, prefix: Optional[str] = None, 
                       duration: Optional[float] = None) -> SessionInfo
    def stop_recording(self) -> SessionInfo  
    def get_status(self) -> RecordingStatus
```

#### 2. RecordingWorkerThread Class
Dedicated thread for file writing operations:

```python
class RecordingWorkerThread(threading.Thread):
    def __init__(self, buffer: DataBuffer, file_writer: RecordFileWriter):
        super().__init__(daemon=True)
        self._buffer = buffer
        self._writer = file_writer
        self._last_read_index = 0
        self._stop_event = threading.Event()
        
    def run(self) -> None:
        """Main worker loop with timer-based polling"""
        while not self._stop_event.is_set():
            new_samples, next_index, dropped = self._buffer.get_since_index(
                self._last_read_index
            )
            
            if dropped:
                logger.warning("Data loss detected during recording")
            
            if new_samples:
                self._writer.append_rows(new_samples)
                self._last_read_index = next_index
                
            # Timer-based polling every 10-20ms
            self._stop_event.wait(0.02)  # 50Hz polling rate
```

#### 3. RecordFileWriter Class
Handles synchronous file operations with internal buffering (unified naming):

```python
class RecordFileWriter:
    def __init__(self, filepath: Path, buffer_size: int = 100):
        self._filepath = filepath
        self._buffer_size = buffer_size  # Flush every N rows
        self._write_buffer: List[str] = []
        self._file_handle: Optional[TextIO] = None
        self._sample_count = 0
        
    def append_rows(self, samples: List[ImuRow]) -> None:
        """Add samples to write buffer"""
        csv_lines = [self._format_csv_row(sample) for sample in samples]
        self._write_buffer.extend(csv_lines)
        self._sample_count += len(samples)
        
        # Flush when buffer is full (every ~4 seconds at 25Hz)
        if len(self._write_buffer) >= self._buffer_size:
            self.flush()
            
    def flush(self, force_fsync: bool = False) -> None:
        """Write buffered data to disk"""
        if not self._write_buffer or not self._file_handle:
            return
            
        # Synchronous write (simple and reliable)
        self._file_handle.writelines(self._write_buffer)
        self._write_buffer.clear()
        
        if force_fsync:
            self._file_handle.flush()
            os.fsync(self._file_handle.fileno())
            
    def close(self) -> None:
        """Close file and write metadata"""
        if self._file_handle:
            self.flush(force_fsync=True)
            self._file_handle.close()
            self._write_metadata_file()
```

#### 4. Enhanced DataBuffer API
Index-based access for efficient recording monitoring:

```python
class DataBuffer:
    def __init__(self, max_size: int = 1000):
        self._buffer: deque[ImuRow] = deque(maxlen=max_size)
        self._lock = threading.RLock()
        self._write_index = 0  # Monotonic counter
        self._base_index = 0   # Index of first element in buffer
        
    def get_since_index(self, last_index: int) -> tuple[list[ImuRow], int, bool]:
        """
        Get samples since last_index with drop detection.
        
        Returns:
            - samples: List of new samples
            - next_index: Index to use for next call
            - dropped: True if data was lost due to buffer overflow
        """
        with self._lock:
            # Detect if requested data was dropped
            dropped = last_index < self._base_index
            
            if dropped:
                # Return all available data and warn about loss
                return list(self._buffer), self._write_index, True
            
            # Calculate slice indices
            start_offset = max(0, last_index - self._base_index)
            end_offset = self._write_index - self._base_index
            
            if start_offset >= len(self._buffer):
                return [], self._write_index, False
                
            # Return slice of buffer
            samples = list(self._buffer)[start_offset:end_offset]
            return samples, self._write_index, False
```

## Implementation Plan

### Phase 1: Core Recording Infrastructure (Week 1)

#### 1.1 Recording Backend (Revised)
- [ ] Implement `RecorderManager` class with simplified start/stop functionality
- [ ] Create `RecordingWorkerThread` for dedicated file operations
- [ ] Add `RecordFileWriter` with synchronous I/O and internal buffering
- [ ] Implement CSV file writing with proper formatting and metadata

#### 1.2 File Management
- [ ] Create recordings directory structure (`recordings/YYYY-MM-DD/`)
- [ ] Implement automatic filename generation (`sensor_data_YYYYMMDD_HHMMSS.csv`)
- [ ] Add file validation and error handling
- [ ] Implement recording metadata storage

#### 1.3 Enhanced Data Buffer Integration
- [ ] **Add index-based data access** - `get_since_index()` method with drop detection
- [ ] **Implement write_index/base_index tracking** - Monotonic counters for data integrity
- [ ] **Thread-safe concurrent access** - Short locks only during buffer operations
- [ ] **Recording state tracking** - Buffer statistics include recording status
- [ ] **Backpressure handling** - Define policies for buffer overflow scenarios

**Critical Implementation Details:**
- Buffer access uses **minimal locking** (only during buffer copy operations)
- Recording monitoring uses **separate read tracking** to avoid interference with UI
- **Timer-based polling** (50Hz) instead of high-frequency async monitoring
- **Error isolation** - Recording failures don't affect data collection
- **Data loss detection** - Warn when buffer overflow causes sample drops

**Deliverable**: Working backend recording system

### Phase 2: User Interface Integration (Week 2)

#### 2.1 Recording Controls UI
- [ ] Add recording panel to oscilloscope interface
- [ ] Implement Start/Stop recording buttons
- [ ] Add recording status indicators (recording/stopped/error)
- [ ] Display current recording duration and sample count

#### 2.2 Recording Session Management
- [ ] Show list of available recordings
- [ ] Add download buttons for recorded files
- [ ] Display recording metadata (duration, samples, file size)
- [ ] Implement recording deletion functionality

#### 2.3 User Experience Enhancements
- [ ] Add recording progress visualization
- [ ] Implement recording time limits and warnings
- [ ] Add disk space monitoring and alerts
- [ ] Create recording configuration options

**Deliverable**: Complete user interface for recording

### Phase 3: Advanced Features and Polish (Week 3)

#### 3.1 Advanced Recording Options
- [ ] Configurable recording parameters (sample rate, duration limits)
- [ ] Custom filename prefixes and organization
- [ ] Selective sensor data recording (e.g., accelerometer only)
- [ ] Recording quality settings and compression

#### 3.2 Data Analysis Integration
- [ ] Preview recorded data within interface
- [ ] Basic statistics for recorded sessions
- [ ] Comparison tools for multiple recordings
- [ ] Export to other formats (JSON, Parquet)

#### 3.3 Performance and Reliability
- [ ] Optimize file I/O for high-frequency data
- [ ] Add recovery mechanisms for interrupted recordings
- [ ] Implement recording validation and integrity checks
- [ ] Performance benchmarking and optimization

**Deliverable**: Production-ready recording system

## Technical Implementation Details

### File Format Specification

#### CSV Header Format
```csv
# XIAO nRF52840 Sense Recording Session
# Start Time: 2024-08-24T16:30:00+09:00
# Device: XIAO Sense IMU
# Recording Duration: 00:02:30.5
# Total Samples: 3765
# Sample Rate: 25.1 Hz (average)
# Note: Header comments optional via --with-comment-header
millis,ax,ay,az,gx,gy,gz,tempC,audioRMS
```

**CSV Format Compatibility**: 
- Column order matches existing `print_stream` output exactly
- Decimal precision consistent with current implementation
- Line endings: LF only (Unix style)
- Comment header rows optional for tool compatibility

#### Recording Metadata File
Each recording generates a companion `.meta.json` file:

```json
{
  "session_id": "20240824_163000_001",
  "start_time": "2024-08-24T16:30:00+09:00",
  "end_time": "2024-08-24T16:32:30.5+09:00",
  "duration_seconds": 150.5,
  "total_samples": 3765,
  "average_sample_rate_hz": 25.1,
  "file_path": "recordings/2024-08-24/sensor_data_20240824_163000.csv",
  "file_size_bytes": 234567,
  "device_info": {
    "name": "XIAO Sense IMU",
    "connection_type": "BLE"
  },
  "recording_settings": {
    "buffer_size": 2000,
    "update_rate_fps": 15
  }
}
```

### Database Schema (Optional Enhancement)

For advanced session management, consider SQLite database:

```sql
CREATE TABLE recording_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    duration_seconds REAL,
    total_samples INTEGER,
    sample_rate_hz REAL,
    file_path TEXT NOT NULL,
    file_size_bytes INTEGER,
    device_name TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Performance Considerations

#### Data Collection Protection (Highest Priority)
- **Minimal-impact monitoring**: Buffer monitoring uses short, infrequent locks
- **Dedicated worker thread**: Recording operations run in separate, low-priority thread
- **Separate thread priorities**: Data collection > UI > Recording
- **Error isolation**: Recording failures don't affect data collection

#### Memory Management
- **Streaming CSV writer**: No memory buildup during long recordings
- **Index-based tracking**: Efficiently track new data without large copies
- **Batch processing**: Process 100-row batches (≈4 seconds) to optimize I/O
- **Bounded write buffer**: Configurable memory limit for file operations

#### File I/O Optimization (Simplified)
- **Synchronous file operations**: Simple, reliable I/O with internal buffering
- **Buffered writes**: Batch writes every 100 rows to minimize disk operations
- **Timer-based polling**: 50Hz monitoring reduces CPU overhead
- **Efficient CSV formatting**: Pre-formatted strings to minimize processing

#### Concurrent Access Strategy (Revised)
```python
# Data Collection Thread (Never Blocked)
def collect_data():
    while collecting:
        sample = receive_ble_data()  # Real-time operation
        buffer.append(sample)  # Short lock only during append
        
# Recording Worker Thread (Background, Low Priority)  
def record_data():
    while recording:
        # Short lock during buffer access only
        new_samples, next_index, dropped = buffer.get_since_index(last_index)
        
        if new_samples:
            file_writer.append_rows(new_samples)  # Sync I/O
            
        time.sleep(0.02)  # 50Hz polling - low CPU usage
```

#### Backpressure and Safety Mechanisms
- **Disk space monitoring**: Check available space before and during recording
- **Buffer overflow detection**: Warn when data is lost due to circular buffer limits
- **Graceful degradation**: Continue data collection even if recording fails
- **Automatic recovery**: Retry recording operations after transient failures

## User Interface Design

### Recording Panel Layout
```
┌─────────────────────────────────────────────────────────┐
│                Recording Controls                       │
├─────────────────────────────────────────────────────────┤
│ 🔴 Record  ⏹️ Stop    📁 Browse Recordings             │
│                                                         │
│ Status: ⚪ Ready to record                              │
│ Duration: 00:00:00 | Samples: 0 | Rate: 0.0 Hz         │
│                                                         │
│ 📊 Current Session                                      │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ File: sensor_data_20240824_163000.csv              │ │
│ │ Size: 0 KB | Started: --:--:--                     │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Recording Status Indicators
- 🔴 **Recording**: Active recording session
- ⚪ **Ready**: Ready to start recording
- ⚠️ **Warning**: Disk space low or other issues
- ❌ **Error**: Recording failed or interrupted

## Testing Strategy

### Unit Tests
- [ ] `RecorderManager` state management and recording flow
- [ ] `RecordingWorkerThread` data polling and file operations
- [ ] `RecordFileWriter` batching, flushing, and data integrity
- [ ] Enhanced `DataBuffer.get_since_index()` with drop detection
- [ ] CSV file format validation and compatibility

### Integration Tests  
- [ ] End-to-end recording workflow with MockDataSource (60-second test)
- [ ] Concurrent recording and visualization performance
- [ ] File system operations and error recovery
- [ ] Backpressure scenarios (slow disk, buffer overflow)
- [ ] UI component integration and user interactions

### Performance Tests
- [ ] Recording performance with sustained 25Hz data rates
- [ ] Memory usage during extended recordings (>1 hour - should be <10MB growth)
- [ ] File I/O throughput (>10k rows/second capability)
- [ ] Buffer overflow recovery and data loss detection
- [ ] System resource usage impact (should be minimal)

## Risk Assessment

### Technical Risks
1. **File I/O Performance**: Risk of blocking UI during writes
   - Mitigation: Asynchronous file operations and buffering
2. **Data Loss**: Risk of losing data during system failures
   - Mitigation: Regular flush operations and recovery mechanisms
3. **Storage Capacity**: Risk of filling disk during long recordings
   - Mitigation: Disk space monitoring and configurable limits

### User Experience Risks
1. **Interface Complexity**: Risk of overwhelming users with options
   - Mitigation: Progressive disclosure and sensible defaults
2. **Recording Management**: Risk of users losing track of recordings
   - Mitigation: Clear organization and search functionality

## Success Metrics

### Performance Targets
- Recording latency < 10ms from buffer to file
- Memory overhead < 10MB regardless of recording duration
- File I/O operations don't block UI for more than 1ms
- Support recordings up to 24 hours without degradation

### User Experience Goals
- One-click recording start/stop
- Reliable data capture with 0% data loss
- Intuitive file organization and access
- Clear feedback on recording status and progress

## Future Enhancements

### Short-term (3-6 months)
- Recording scheduler for automated sessions
- Data compression options for storage efficiency
- Integration with cloud storage services
- Mobile app companion for remote recording control

### Long-term (6+ months)
- Real-time streaming to external services
- Advanced data analysis and visualization tools
- Machine learning integration for anomaly detection
- Multi-device synchronized recording