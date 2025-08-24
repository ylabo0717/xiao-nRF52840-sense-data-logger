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
                                                   [Buffer Monitor]
                                                        ↓
                                               [Async File Writer]
                                               (Background Thread)
```

### Threading Architecture

1. **Data Collection Thread** (Existing - Highest Priority)
   - Receives BLE data from XIAO device
   - Writes directly to DataBuffer
   - **MUST NEVER BE BLOCKED** by recording operations
   - Real-time operation at ~25Hz

2. **UI Update Thread** (Existing - Medium Priority)  
   - Reads from DataBuffer for visualization
   - Updates Plotly graphs at 15 FPS
   - Non-blocking buffer access

3. **Recording Monitor Thread** (New - Low Priority)
   - Monitors DataBuffer for new data
   - Asynchronously writes to file
   - Uses separate asyncio event loop
   - Polling-based detection (100Hz monitoring)

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
│  │   Session    │  │ Async File   │  │   Buffer     │   │
│  │  Manager     │  │   Writer     │  │   Monitor    │   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│              Enhanced Data Buffer                       │
│         (with Index Tracking Support)                  │
└─────────────────────────────────────────────────────────┘
```

### Core Components

#### 1. DataRecorder Class
Central coordinator for recording operations:

```python
class DataRecorder:
    def __init__(self, buffer: DataBuffer, output_dir: Path):
        self._buffer = buffer
        self._output_dir = output_dir
        self._session: Optional[RecordingSession] = None
        self._is_recording = False
        
    def start_recording(self, filename: Optional[str] = None) -> RecordingSession
    def stop_recording(self) -> RecordingSession
    def get_status(self) -> RecordingStatus
```

#### 2. RecordingSession Class
Manages individual recording sessions:

```python
class RecordingSession:
    def __init__(self, filename: str, start_time: datetime):
        self.filename = filename
        self.start_time = start_time
        self.sample_count = 0
        self.file_writer: Optional[CSVWriter] = None
        
    def write_samples(self, samples: List[ImuRow]) -> None
    def finalize(self) -> RecordingMetadata
```

#### 3. BufferMonitor Class
Monitors buffer for new data during recording with zero-impact design:

```python
class BufferMonitor:
    def __init__(self, buffer: DataBuffer, file_writer: AsyncFileWriter):
        self._buffer = buffer
        self._writer = file_writer
        self._last_read_index = 0  # Track last processed sample
        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None
        
    async def start_monitoring(self) -> None:
        """Start monitoring loop in background thread"""
        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        
    async def stop_monitoring(self) -> None:
        """Stop monitoring and flush remaining data"""
        self._monitoring = False
        if self._monitor_task:
            await self._monitor_task
        await self._flush_remaining_data()
        
    async def _monitor_loop(self) -> None:
        """Non-blocking monitoring loop at 100Hz"""
        while self._monitoring:
            try:
                # Get new data since last read (non-blocking)
                new_samples = self._buffer.get_samples_since_index(self._last_read_index)
                
                if new_samples:
                    # Asynchronous batch write (doesn't block data collection)
                    await self._writer.write_batch_async(new_samples)
                    self._last_read_index += len(new_samples)
                
                # High-frequency monitoring for minimal latency
                await asyncio.sleep(0.01)  # 100Hz polling
                
            except Exception as e:
                # Log error but continue monitoring
                logger.error(f"Recording error: {e}")
                await asyncio.sleep(0.1)  # Slower retry on error
```

#### 4. AsyncFileWriter Class
Handles asynchronous file operations without blocking data collection:

```python
class AsyncFileWriter:
    def __init__(self, filepath: Path, buffer_size: int = 1024):
        self._filepath = filepath
        self._buffer_size = buffer_size
        self._write_buffer: List[str] = []
        self._file_handle: Optional[TextIO] = None
        
    async def write_batch_async(self, samples: List[ImuRow]) -> None:
        """Write samples to file asynchronously"""
        csv_lines = [self._format_csv_row(sample) for sample in samples]
        self._write_buffer.extend(csv_lines)
        
        # Flush buffer when full to optimize disk I/O
        if len(self._write_buffer) >= self._buffer_size:
            await self._flush_buffer_async()
            
    async def _flush_buffer_async(self) -> None:
        """Asynchronously flush write buffer to disk"""
        if not self._write_buffer:
            return
            
        # Use thread pool executor for file I/O to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, 
            self._write_to_disk, 
            self._write_buffer.copy()
        )
        self._write_buffer.clear()
```

## Implementation Plan

### Phase 1: Core Recording Infrastructure (Week 1)

#### 1.1 Data Recorder Backend
- [ ] Implement `DataRecorder` class with start/stop functionality
- [ ] Create `RecordingSession` for session management
- [ ] Add `BufferMonitor` for real-time data detection
- [ ] Implement CSV file writing with proper formatting

#### 1.2 File Management
- [ ] Create recordings directory structure (`recordings/YYYY-MM-DD/`)
- [ ] Implement automatic filename generation (`sensor_data_YYYYMMDD_HHMMSS.csv`)
- [ ] Add file validation and error handling
- [ ] Implement recording metadata storage

#### 1.3 Enhanced Data Buffer Integration
- [ ] **Add index-based data access** - `get_samples_since_index()` method
- [ ] **Implement zero-copy monitoring** - Non-blocking buffer access
- [ ] **Thread-safe concurrent access** - Multiple readers without locks
- [ ] **Recording state tracking** - Buffer statistics include recording status

**Critical Implementation Details:**
- Buffer access must be **lock-free** for data collection thread
- Recording monitoring uses **separate read index** to avoid interference
- **Batch processing** (1-second batches) to minimize file I/O overhead
- **Error isolation** - Recording failures don't affect data collection

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
millis,ax,ay,az,gx,gy,gz,tempC,audioRMS
```

#### Recording Metadata File
Each recording generates a companion `.meta.json` file:

```json
{
  "session_id": "20240824_163000_001",
  "start_time": "2024-08-24T16:30:00+09:00",
  "end_time": "2024-08-24T16:32:30.5+09:00",
  "duration_seconds": 150.5,
  "total_samples": 3765,
  "sample_rate_hz": 25.1,
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
- **Zero-impact monitoring**: Buffer monitoring never blocks data collection
- **Lock-free buffer access**: Data collection thread uses lock-free circular buffer
- **Separate thread priorities**: Data collection > UI > Recording
- **Error isolation**: Recording failures don't affect data collection

#### Memory Management
- **Streaming CSV writer**: No memory buildup during long recordings
- **Index-based tracking**: Avoid copying large datasets from buffer
- **Batch processing**: Process 1-second batches (≈25 samples) to optimize I/O
- **Bounded write buffer**: Configurable memory limit for file operations

#### File I/O Optimization
- **Asynchronous file operations**: All disk I/O uses asyncio.run_in_executor()
- **Buffered writes**: Batch writes every 1-2 seconds to minimize disk operations
- **Thread pool executor**: File I/O operations run in separate thread pool
- **Efficient CSV formatting**: Pre-formatted strings to minimize processing

#### Concurrent Access Strategy
```python
# Data Collection Thread (Never Blocked)
def collect_data():
    while collecting:
        sample = receive_ble_data()  # Real-time operation
        buffer.append_lockfree(sample)  # Lock-free append
        
# Recording Thread (Background, Low Priority)  
async def record_data():
    while recording:
        new_samples = buffer.get_new_samples()  # Non-blocking read
        await async_file_writer.write(new_samples)  # Async I/O
        await asyncio.sleep(0.01)  # Yield to other tasks
```

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
- [ ] `DataRecorder` state management and recording flow
- [ ] `RecordingSession` file operations and data integrity
- [ ] `BufferMonitor` new data detection accuracy
- [ ] CSV file format validation and compatibility

### Integration Tests  
- [ ] End-to-end recording workflow with live data
- [ ] Concurrent recording and visualization performance
- [ ] File system operations and error recovery
- [ ] UI component integration and user interactions

### Performance Tests
- [ ] Recording performance with high data rates (>50 Hz)
- [ ] Memory usage during extended recordings (>1 hour)
- [ ] File I/O performance under various conditions
- [ ] System resource usage impact

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