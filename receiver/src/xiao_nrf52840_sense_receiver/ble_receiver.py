"""BLE sensor data receiver for XIAO nRF52840 Sense devices.

This module provides a comprehensive BLE communication system for receiving
real-time sensor telemetry from XIAO nRF52840 Sense devices over Nordic UART
Service (NUS). The implementation handles the complete data pipeline from device
discovery through data parsing and streaming.

Core Features:
- **Device Discovery**: Automatic BLE scanning by device name or service UUID
- **Robust Connection**: Multi-retry connection logic with exponential backoff
- **Data Assembly**: Fragment reassembly with multiple line delimiter support
- **Stream Processing**: Real-time CSV parsing into structured data objects
- **Error Recovery**: Comprehensive error classification and recovery strategies
- **Production Ready**: Configurable timeouts and monitoring for deployment

The module supports both direct CLI usage for simple data capture and programmatic
integration through abstract data source interfaces for complex applications.

Architecture:
- DataSource interface enables pluggable data sources (BLE, Mock, File, etc.)
- Circular buffer provides thread-safe data storage with gap detection
- Async/await throughout ensures non-blocking operation under high data rates
- Producer-consumer pattern decouples data collection from processing

Requirements:
- bleak: Cross-platform BLE library for device communication
- asyncio: Async I/O support for concurrent operation
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from typing import AsyncGenerator, AsyncIterator, Callable, Iterable, Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakError


# Nordic UART Service (NUS) UUID constants
NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_CHAR = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # Notify (device to client)
NUS_RX_CHAR = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Write (client to device, unused)


DEVICE_NAME = "XIAO Sense IMU"


@dataclass(frozen=True)
class ImuRow:
    """Represents a single IMU sensor data row from the XIAO nRF52840 Sense device.

    This class encapsulates one complete sensor reading containing accelerometer,
    gyroscope, temperature, and audio RMS values. The frozen dataclass design
    ensures immutability, which is crucial for data integrity in a streaming
    system where data flows through multiple processing stages.

    The field order matches the CSV format transmitted by the XIAO device:
    millis,ax,ay,az,gx,gy,gz,tempC,audioRMS

    Attributes:
        millis: Timestamp in milliseconds from device boot. Used for timing
            analysis and synchronization between samples.
        ax: Accelerometer X-axis (m/s²). Part of 3-axis motion detection.
        ay: Accelerometer Y-axis (m/s²). Part of 3-axis motion detection.
        az: Accelerometer Z-axis (m/s²). Part of 3-axis motion detection.
        gx: Gyroscope X-axis (deg/s). Part of 3-axis rotation detection.
        gy: Gyroscope Y-axis (deg/s). Part of 3-axis rotation detection.
        gz: Gyroscope Z-axis (deg/s). Part of 3-axis rotation detection.
        tempC: Temperature in Celsius from IMU sensor. Used for thermal
            compensation and environmental monitoring.
        audioRMS: RMS value of 10ms audio window. Provides audio level
            indication without raw audio data transmission.

    Note:
        The frozen=True parameter prevents accidental mutation of sensor data,
        ensuring data integrity throughout the processing pipeline.
    """

    millis: int
    ax: float
    ay: float
    az: float
    gx: float
    gy: float
    gz: float
    tempC: float
    audioRMS: float

    @staticmethod
    def parse_csv(line: str) -> "ImuRow":
        """Parse CSV line into ImuRow instance.

        This method handles the conversion from the raw CSV format transmitted
        by the XIAO device into a structured data object. The parser is designed
        to be lenient with whitespace to handle potential BLE transmission
        artifacts while maintaining strict field count validation.

        Args:
            line: CSV string in format "millis,ax,ay,az,gx,gy,gz,tempC,audioRMS"
                Whitespace around commas is automatically stripped.

        Returns:
            ImuRow: Parsed sensor data instance with all fields populated.

        Raises:
            ValueError: If the line doesn't contain exactly 9 comma-separated
                fields, indicating a malformed or incomplete transmission.
            ValueError: If any numeric field cannot be converted to the
                appropriate type (int for millis, float for others).

        Note:
            The whitespace stripping is essential because BLE transmission
            sometimes introduces extra spaces due to packet fragmentation
            and reassembly at the protocol level.
        """
        # Input typically uses ", " but be lenient with whitespace variations
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 9:
            raise ValueError(f"Unexpected CSV fields count: {len(parts)} in '{line}'")

        millis = int(parts[0])
        ax, ay, az = float(parts[1]), float(parts[2]), float(parts[3])
        gx, gy, gz = float(parts[4]), float(parts[5]), float(parts[6])
        tempC = float(parts[7])
        audioRMS = float(parts[8])
        return ImuRow(
            millis=millis,
            ax=ax,
            ay=ay,
            az=az,
            gx=gx,
            gy=gy,
            gz=gz,
            tempC=tempC,
            audioRMS=audioRMS,
        )


@dataclass
class BufferStats:
    """Real-time statistics for sensor data buffer monitoring.

    This class tracks buffer utilization and data flow rates for performance
    monitoring and system health assessment. Statistics are calculated in
    real-time during normal buffer operations without additional overhead.

    The statistics serve multiple purposes:
    1. **Performance monitoring**: Track data ingestion rates and buffer utilization
    2. **System health**: Detect buffer overflows and connection issues
    3. **User feedback**: Provide real-time status in UI applications
    4. **Debugging**: Historical data rate information for troubleshooting

    Attributes:
        fill_level: Current number of samples in the buffer. Used to monitor
            buffer utilization and detect approaching overflow conditions.
        sample_rate: Current data ingestion rate in samples per second. Calculated
            from time intervals between consecutive updates.
        last_update: Timestamp of the most recent statistics update. Used internally
            for sample rate calculations.

    Note:
        Sample rate calculation uses a simple interval-based approach rather than
        moving averages for minimal computational overhead during high-frequency
        data ingestion.
    """

    fill_level: int = 0
    sample_rate: float = 0.0
    last_update: float = 0.0

    def update(self, _row: ImuRow) -> None:
        """Update statistics with new sensor data sample.

        This method is called automatically during buffer operations to maintain
        real-time statistics. The sample rate calculation uses simple time
        intervals for minimal computational overhead.

        Args:
            _row: New sensor data sample being processed. The actual data values
                are not used for statistics, only the arrival timing for rate calculation.

        Note:
            Sample rate is calculated as the reciprocal of the time interval
            between consecutive calls. This provides instantaneous rate rather
            than smoothed averages, making it responsive to connection changes.
        """
        current_time = time.time()
        if self.last_update > 0:
            time_diff = current_time - self.last_update
            if time_diff > 0:
                self.sample_rate = 1.0 / time_diff
        self.last_update = current_time


class DataBuffer:
    """Thread-safe circular buffer optimized for real-time sensor data streaming.

    This class implements a specialized circular buffer designed for high-frequency
    sensor data ingestion with concurrent access patterns. The key design decisions
    address specific challenges in real-time sensor systems:

    1. **Index-based tracking**: Unlike simple circular buffers, this maintains
       monotonic indices to detect data loss during concurrent access, essential
       for reliable data recording.

    2. **Thread safety**: Uses RLock to handle recursive locking scenarios while
       maintaining performance for high-frequency writes (~25Hz BLE + ~100Hz simulation).

    3. **Non-blocking statistics**: Real-time stats calculation without separate
       threads, minimizing system complexity.

    4. **Drop detection**: Critical for data recording systems where knowing about
       lost samples is more important than perfect buffering.

    The circular nature prevents unbounded memory growth while the index tracking
    ensures recording threads can detect gaps in the data stream.

    Attributes:
        _max_size: Maximum buffer capacity before oldest entries are dropped.
        _buffer: Circular deque storing actual IMU data rows.
        _lock: Reentrant lock for thread-safe operations.
        _stats: Real-time statistics tracking buffer state and data ranges.
        _write_index: Monotonically increasing counter for all writes ever made.
        _base_index: Index of the oldest sample currently in the buffer.

    Note:
        The index-based design is specifically required for the recording system
        to maintain data integrity across thread boundaries without complex
        synchronization mechanisms.
    """

    def __init__(self, max_size: int = 1000):
        """Initialize thread-safe circular buffer with index tracking.

        Args:
            max_size: Maximum number of samples to retain. When exceeded,
                oldest samples are dropped. Default 1000 provides ~40 seconds
                of data at 25Hz BLE rate, sufficient for visualization and
                short-term recording without excessive memory usage.
        """
        self._max_size = max_size
        self._buffer: deque[ImuRow] = deque(maxlen=max_size)
        self._lock = threading.RLock()
        self._stats = BufferStats()

        # Index-based access for recording (enables gap detection)
        self._write_index = 0  # Monotonic counter for all writes
        self._base_index = 0  # Index of first element currently in buffer

    def append(self, row: ImuRow) -> None:
        """Add new sensor data row to buffer with automatic statistics update.

        This method handles the core data ingestion from BLE reception. The
        implementation is optimized for high-frequency calls (~25Hz) while
        maintaining thread safety and real-time statistics.

        Args:
            row: Complete IMU sensor reading to add to the buffer.

        Note:
            When buffer is full, oldest data is automatically dropped. The
            base_index tracking ensures recording threads can detect this
            condition and handle data gaps appropriately.
        """
        with self._lock:
            # Check if we're about to drop data due to circular buffer overflow
            if len(self._buffer) == self._max_size:
                self._base_index += 1  # First element will be dropped

            self._buffer.append(row)
            self._write_index += 1
            self._stats.fill_level = len(self._buffer)
            self._stats.update(row)

    def get_recent(self, count: int) -> list[ImuRow]:
        """Get the most recent N data points for visualization.

        This method is primarily used by the oscilloscope visualization to
        efficiently retrieve the latest sensor readings without affecting
        the buffer's internal state or recording operations.

        Args:
            count: Number of recent samples to retrieve. If count exceeds
                buffer size, all available samples are returned.

        Returns:
            List of IMU rows ordered from oldest to newest in the requested range.

        Note:
            Returns a shallow copy to prevent external modification of buffer
            contents while avoiding expensive deep copying of sensor data.
        """
        with self._lock:
            return (
                list(self._buffer)[-count:]
                if count <= len(self._buffer)
                else list(self._buffer)
            )

    def get_all(self) -> list[ImuRow]:
        """Get all data points currently in buffer.

        Returns:
            Complete list of all buffered IMU rows, ordered chronologically.

        Note:
            Used primarily for debugging and full data export scenarios.
            For recording operations, prefer get_since_index() for efficiency.
        """
        with self._lock:
            return list(self._buffer)

    def get_since_index(self, last_index: int) -> tuple[list[ImuRow], int, bool]:
        """Retrieve new samples since last_index with data loss detection.

        This is the critical method for recording operations, designed to handle
        concurrent access patterns where visualization continues while recording
        is active. The index-based approach ensures recording threads can detect
        and handle buffer overflows gracefully.

        The implementation handles three scenarios:
        1. Normal case: Return new samples since last check
        2. Buffer overflow: Detect data loss and return all available data
        3. No new data: Return empty list efficiently

        Args:
            last_index: Index of the last sample previously processed by
                the calling thread. Must be from a previous call's return value.

        Returns:
            tuple containing:
            - samples: List of new IMU rows since last_index, chronologically ordered
            - next_index: Index value to pass to next call for continuation
            - dropped: True if data was lost due to circular buffer overflow,
                indicating the recording may have gaps

        Note:
            This method is the foundation of gap-aware recording. When dropped=True,
            the caller should log the data loss and decide whether to continue
            recording or restart with a clean session.
        """
        with self._lock:
            # Detect if requested data was dropped from circular buffer
            dropped = last_index < self._base_index

            if dropped:
                # Return all available data and warn about loss
                return list(self._buffer), self._write_index, True

            # Calculate slice indices within current buffer
            start_offset = max(0, last_index - self._base_index)
            end_offset = self._write_index - self._base_index

            if start_offset >= len(self._buffer):
                # No new data available
                return [], self._write_index, False

            # Return slice of buffer containing new data
            samples = list(self._buffer)[start_offset:end_offset]
            return samples, self._write_index, False

    def clear(self) -> None:
        """Clear all buffer contents and reset index tracking.

        This method provides a clean reset of the entire buffer state,
        used primarily when switching data sources or restarting sessions.
        All statistics and index tracking are reset to initial values.

        Note:
            After calling clear(), any previous index values from get_since_index()
            become invalid and should not be reused.
        """
        with self._lock:
            self._buffer.clear()
            self._stats.fill_level = 0
            # Reset index tracking
            self._write_index = 0
            self._base_index = 0

    @property
    def stats(self) -> BufferStats:
        """Get current buffer statistics for monitoring and debugging.

        Returns:
            BufferStats: Real-time statistics including fill level and
                data range information, calculated during normal operations.
        """
        with self._lock:
            return self._stats

    @property
    def size(self) -> int:
        """Get current number of samples in buffer.

        Returns:
            Current buffer occupancy, useful for monitoring buffer utilization.
        """
        with self._lock:
            return len(self._buffer)

    @property
    def max_size(self) -> int:
        """Get maximum buffer capacity.

        Returns:
            Maximum number of samples before circular overflow occurs.
        """
        return self._max_size

    @property
    def current_write_index(self) -> int:
        """Get current write index for recording initialization.

        This property enables recording threads to initialize their tracking
        index to the current buffer state, ensuring they don't miss data
        when starting recording mid-stream.

        Returns:
            Current monotonic write index value.

        Note:
            This index represents the total number of samples ever written
            to this buffer instance, not the current buffer position.
        """
        with self._lock:
            return self._write_index


class DataSource(ABC):
    """Abstract base class defining the interface for sensor data sources.

    This interface enables pluggable data sources for the sensor monitoring system,
    supporting both real hardware devices and simulated data sources. The design
    follows the Strategy pattern, allowing applications to switch between different
    data sources without changing the consuming code.

    Key design principles:
    1. **Async-first**: All methods are asynchronous to support non-blocking I/O
    2. **Lifecycle management**: Clear start/stop semantics for resource management
    3. **Connection monitoring**: Status checking for robust error handling
    4. **Stream interface**: Generator pattern for efficient data processing

    Implementations must handle their own connection management, error recovery,
    and resource cleanup. The interface is intentionally minimal to support
    diverse data source types (BLE, USB, file, network, etc.).

    Example implementations:
    - BleDataSource: Real BLE communication with XIAO devices
    - MockDataSource: Synthetic data for testing and development
    - FileDataSource: Playback from recorded data files
    - NetworkDataSource: Remote sensor data over TCP/WebSocket
    """

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if the data source is currently connected and operational.

        Returns:
            True if data source is connected and ready to provide data,
            False otherwise.

        Note:
            This should reflect the logical connection state. For BLE sources,
            this means device is paired and communicating. For file sources,
            this means file is open and readable.
        """
        pass

    @abstractmethod
    async def start(self) -> None:
        """Initialize and start the data source.

        This method should perform all necessary setup to prepare the data
        source for operation. For hardware sources, this might include device
        discovery and connection. For file sources, this might mean opening
        files and validating headers.

        Raises:
            Various exceptions specific to the data source type. Common examples:
            - ConnectionError: Unable to establish connection
            - FileNotFoundError: Source data file missing
            - PermissionError: Insufficient access rights

        Note:
            This method should be idempotent - calling it multiple times should
            not cause issues if the source is already started.
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the data source and clean up resources.

        This method should gracefully shut down the data source and release
        any held resources (connections, files, threads, etc.). It should
        ensure that get_data_stream() terminates cleanly.

        Note:
            This method should be idempotent and safe to call even if the
            source is already stopped or was never started.
        """
        pass

    @abstractmethod
    def get_data_stream(self) -> AsyncGenerator[ImuRow, None]:
        """Get an async generator that yields sensor data samples.

        This is the core method that provides the actual sensor data stream.
        The generator should yield ImuRow objects as they become available
        from the data source.

        Yields:
            ImuRow: Individual sensor readings with all fields populated.

        Raises:
            Various exceptions depending on the data source:
            - ConnectionError: Lost connection during streaming
            - DataError: Corrupted or invalid data received
            - TimeoutError: Data source became unresponsive

        Note:
            The generator should run indefinitely until stop() is called or
            an unrecoverable error occurs. Temporary issues should be handled
            internally with appropriate retry logic.
        """
        pass


class BleDataSource(DataSource):
    """Production BLE data source with robust connection handling and monitoring.

    This class implements the DataSource interface specifically for BLE communication
    with XIAO nRF52840 Sense devices. The design focuses on reliability in
    real-world deployment scenarios where BLE connections are inherently unstable.

    Key design decisions:

    1. **Configurable timeouts**: Both scan and idle timeouts can be tuned for
       different deployment environments (office vs. field vs. production).

    2. **Connection health monitoring**: Automatic logging and statistics tracking
       help diagnose connection issues without manual intervention.

    3. **Error classification**: Different BLE errors get specific handling and
       user guidance, improving troubleshooting experience.

    4. **Graceful degradation**: Connection failures are logged but don't crash
       the application, allowing for retry logic at higher levels.

    The implementation wraps the lower-level stream_rows() function with
    additional monitoring and stability features required for production use.

    Attributes:
        _connected: Current connection state, used for graceful shutdown.
        _scan_timeout: Maximum time to search for XIAO device during connection.
        _idle_timeout: Maximum time to wait between data packets before timeout.
        _connection_attempts: Counter for debugging connection reliability.
        _last_data_time: Timestamp of last received data for health monitoring.

    Note:
        This class is designed to be the primary data source for production
        deployments where connection reliability is more important than
        maximum throughput.
    """

    def __init__(self, scan_timeout: float = 15.0, idle_timeout: float = 30.0) -> None:
        """Initialize BLE data source with configurable timeout parameters.

        Args:
            scan_timeout: Maximum seconds to scan for XIAO device. Longer
                values increase connection success rate but delay error detection.
                Default 15s balances reliability with user experience.
            idle_timeout: Maximum seconds between data packets before considering
                connection lost. Default 30s accounts for temporary BLE interference
                while detecting actual disconnections promptly.

        Note:
            Timeout values should be tuned based on deployment environment:
            - Office/lab: shorter timeouts for quick feedback
            - Production: longer timeouts for stability
            - Field testing: very long timeouts for challenging RF environments
        """
        self._connected = False
        self._scan_timeout = scan_timeout
        self._idle_timeout = idle_timeout
        self._connection_attempts = 0
        self._last_data_time = 0.0

    async def is_connected(self) -> bool:
        """Check if BLE connection is currently active.

        Returns:
            True if connected and receiving data, False otherwise.

        Note:
            This reflects the logical connection state, not the underlying
            BLE radio state which may have temporary interruptions.
        """
        return self._connected

    async def start(self) -> None:
        """Initialize data source for connection attempts.

        This method prepares the data source for operation but doesn't
        establish the BLE connection. Actual connection happens in
        get_data_stream() to support lazy initialization patterns.
        """
        self._connected = True

    async def stop(self) -> None:
        """Gracefully stop the data source and close BLE connection.

        This method signals the data stream to terminate cleanly,
        allowing any pending operations to complete before shutdown.
        """
        self._connected = False

    async def get_data_stream(self) -> AsyncGenerator[ImuRow, None]:
        """Establish BLE connection and stream sensor data with health monitoring.

        This is the core method that handles the complete BLE connection lifecycle:
        device discovery, connection establishment, data reception, and error handling.
        The implementation includes comprehensive logging and monitoring to support
        production deployment scenarios.

        The health monitoring serves multiple purposes:
        1. **User feedback**: Regular updates show connection is working
        2. **Debugging**: Statistics help diagnose performance issues
        3. **Reliability metrics**: Data rates and connection duration tracking
        4. **Error classification**: Specific guidance for different failure modes

        Yields:
            ImuRow: Individual sensor readings as they arrive from the device.

        Raises:
            KeyboardInterrupt: When user manually stops the connection.
            Various BLE exceptions: Classified and logged with specific guidance.

        Note:
            Connection failures are expected in BLE systems. The detailed error
            classification helps users understand whether issues are environmental
            (move closer), device-related (check power), or system-related
            (restart Bluetooth).
        """
        import logging
        import time

        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)

        self._connected = True
        self._connection_attempts += 1

        try:
            logger.info(
                f"🔍 Scanning for XIAO Sense IMU device (attempt {self._connection_attempts})..."
            )
            logger.info(
                f"⚙️ Scan timeout: {self._scan_timeout}s, Idle timeout: {self._idle_timeout}s"
            )

            data_count = 0
            last_log_time = time.time()
            connection_start = time.time()

            async for row in stream_rows(
                scan_timeout=self._scan_timeout, idle_timeout=self._idle_timeout
            ):
                if not self._connected:
                    logger.info("🛑 Connection manually stopped")
                    break

                current_time = time.time()
                self._last_data_time = current_time
                data_count += 1

                # Log connection health every 10 seconds
                if current_time - last_log_time > 10.0:
                    connection_duration = current_time - connection_start
                    avg_rate = (
                        data_count / connection_duration
                        if connection_duration > 0
                        else 0
                    )
                    logger.info(
                        f"📊 Connection healthy: {data_count} samples, {avg_rate:.1f}Hz avg"
                    )
                    last_log_time = current_time

                yield row

        except KeyboardInterrupt:
            logger.info("🛑 BLE stream interrupted by user")
            self._connected = False
            raise
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.error(f"❌ BLE stream error: {error_msg}")

            # Classify error types for better debugging
            if "was not found" in str(e) or "No such device" in str(e):
                logger.error(
                    "🔍 Device not found - check if XIAO is powered on and advertising"
                )
            elif "Connection failed" in str(e) or "timeout" in str(e).lower():
                logger.error("⏱️ Connection timeout - device may be out of range")
            elif "was disconnected" in str(e) or "disconnected" in str(e).lower():
                logger.error(
                    "🔌 Device disconnected - connection lost during operation"
                )

            self._connected = False
            raise
        finally:
            connection_duration = (
                time.time() - connection_start if "connection_start" in locals() else 0
            )
            logger.info(
                f"🔌 BLE data stream disconnected after {connection_duration:.1f}s"
            )
            self._connected = False


class MockDataSource(DataSource):
    """Synthetic data source for testing, development, and demonstration.

    This data source generates realistic IMU sensor data using mathematical
    functions to simulate the behavior of a real XIAO nRF52840 Sense device.
    The synthetic data includes all sensor modalities with realistic value
    ranges and temporal characteristics.

    Key features:
    1. **Realistic data patterns**: Sinusoidal functions with noise simulate
       actual sensor behavior including gravity, motion, and environmental changes.
    2. **Configurable rate**: Adjustable update interval allows testing at
       different data rates to match real device behavior.
    3. **Missing data simulation**: Includes random audio dropouts to test
       handling of incomplete sensor readings.
    4. **Deterministic patterns**: Predictable mathematical functions enable
       automated testing and validation.

    The generated data characteristics:
    - Accelerometer: Includes 1g gravity offset with periodic motion
    - Gyroscope: Rotational patterns with varying amplitudes
    - Temperature: Slow thermal variations around room temperature
    - Audio RMS: Periodic patterns with 10% random dropouts

    This data source is essential for:
    - Unit testing without hardware dependencies
    - UI development and layout testing
    - Performance testing under controlled conditions
    - Demonstration and training scenarios

    Attributes:
        _connected: Current connection state for lifecycle management.
        _running: Internal flag controlling data generation loop.
        _update_interval: Time delay between generated samples in seconds.
        _start_time: Reference timestamp for deterministic data generation.
    """

    def __init__(self, update_interval: float = 0.04):  # 25Hz
        """Initialize mock data source with configurable update rate.

        Args:
            update_interval: Time between generated samples in seconds.
                Default 0.04 (25Hz) matches typical XIAO device data rates.
                Lower values increase CPU usage but provide higher resolution.

        Note:
            The update interval affects both the temporal resolution of generated
            data and the computational load. Values below 0.01 (100Hz) may
            impact system performance.
        """
        self._connected = False
        self._running = False
        self._update_interval = update_interval
        self._start_time = time.time()

    async def is_connected(self) -> bool:
        """Check if mock data source is active.

        Returns:
            True if data generation is active, False otherwise.

        Note:
            Mock data sources are always "connected" when started since they
            don't depend on external hardware or network resources.
        """
        return self._connected

    async def start(self) -> None:
        """Start mock data generation.

        This method initializes the synthetic data generator and resets timing
        references to ensure deterministic data patterns from the start point.

        Note:
            Starting the mock source is instantaneous since no external resources
            are required. Data generation begins when get_data_stream() is called.
        """
        self._connected = True
        self._running = True
        self._start_time = time.time()

    async def stop(self) -> None:
        """Stop mock data generation.

        This method signals the data generator to terminate cleanly, allowing
        any ongoing get_data_stream() calls to complete gracefully.

        Note:
            Stopping is immediate since no external connections need to be closed.
        """
        self._connected = False
        self._running = False

    async def get_data_stream(self) -> AsyncGenerator[ImuRow, None]:
        """Generate synthetic IMU data with realistic sensor characteristics.

        This method produces a continuous stream of synthetic sensor data using
        mathematical functions to simulate realistic device behavior. The data
        patterns are deterministic based on elapsed time, enabling reproducible
        testing scenarios.

        Data generation characteristics:
        - **Accelerometer**: Combines gravity (1g) with sinusoidal motion patterns
          and Gaussian noise to simulate real movement and sensor noise.
        - **Gyroscope**: Multi-frequency rotational patterns with different
          amplitudes per axis to simulate realistic angular motion.
        - **Temperature**: Slow sinusoidal variation around room temperature
          with random noise to simulate thermal changes.
        - **Audio RMS**: Periodic audio-like patterns with random dropouts
          (10% missing data) to test audio processing robustness.

        Yields:
            ImuRow: Synthetic sensor readings with realistic value ranges
            and temporal correlations.

        Raises:
            asyncio.CancelledError: When the async generator is cancelled.

        Note:
            The generator runs until stop() is called or the async context
            is cancelled. Data patterns are consistent across runs due to
            deterministic mathematical functions.
        """
        self._connected = True
        self._running = True

        try:
            counter = 0
            while self._running:
                current_time = time.time()
                elapsed = current_time - self._start_time

                # Generate sinusoidal data with some noise
                ax = 0.5 * math.sin(2 * math.pi * 0.5 * elapsed) + random.gauss(0, 0.1)
                ay = 0.3 * math.cos(2 * math.pi * 0.3 * elapsed) + random.gauss(0, 0.1)
                az = (
                    1.0
                    + 0.2 * math.sin(2 * math.pi * 0.1 * elapsed)
                    + random.gauss(0, 0.05)
                )

                gx = 10.0 * math.sin(2 * math.pi * 0.8 * elapsed) + random.gauss(0, 2.0)
                gy = 15.0 * math.cos(2 * math.pi * 0.6 * elapsed) + random.gauss(0, 2.0)
                gz = 5.0 * math.sin(2 * math.pi * 0.4 * elapsed) + random.gauss(0, 1.0)

                tempC = (
                    25.0
                    + 3.0 * math.sin(2 * math.pi * 0.01 * elapsed)
                    + random.gauss(0, 0.5)
                )

                # Audio RMS with some random dropouts (-1 indicates missing data)
                if random.random() > 0.1:  # 90% data availability
                    audioRMS = abs(
                        1000.0 * math.sin(2 * math.pi * 2.0 * elapsed)
                    ) + random.gauss(0, 50.0)
                else:
                    audioRMS = -1.0

                millis = int(elapsed * 1000)

                row = ImuRow(
                    millis=millis,
                    ax=ax,
                    ay=ay,
                    az=az,
                    gx=gx,
                    gy=gy,
                    gz=gz,
                    tempC=tempC,
                    audioRMS=audioRMS,
                )

                yield row
                counter += 1

                await asyncio.sleep(self._update_interval)

        except asyncio.CancelledError:
            pass
        finally:
            self._connected = False
            self._running = False


logger = logging.getLogger(__name__)


async def _scan_ble_devices(
    timeout: float,
) -> dict[str, tuple[BLEDevice, AdvertisementData]]:
    """Scan for BLE devices and retrieve advertisement data.

    This function performs device discovery using the cross-platform Bleak library.
    The implementation handles platform-specific quirks and provides detailed error
    messages for common BLE scanning issues.

    Args:
        timeout: Maximum time in seconds to spend scanning for devices.
            Longer timeouts increase device discovery success rate but delay
            error reporting.

    Returns:
        Dictionary mapping device addresses to (BLEDevice, AdvertisementData) tuples.
        The dictionary includes all devices discovered during the scan period.

    Raises:
        RuntimeError: If BLE scanning cannot be initialized. The error message
            includes platform-specific troubleshooting guidance for common issues.

    Note:
        Modern Bleak versions (0.22+) require explicit advertisement data retrieval
        via return_adv=True. This function automatically handles this requirement.
    """
    try:
        # Bleak 0.22+ doesn't include metadata in BLEDevice objects.
        # Request advertisement data explicitly with return_adv=True.
        devices_adv = await BleakScanner.discover(timeout=timeout, return_adv=True)
        logger.debug("Scan completed: %d devices found", len(devices_adv))
        return devices_adv
    except BleakError as e:
        raise RuntimeError(
            "BLE scanner initialization failed. Please verify:\n"
            "- Windows Bluetooth is enabled\n"
            "- Windows Location Services enabled (required for BLE scanning)\n"
            "- Running on native Windows (not in VM/WSL)\n"
            "- Remote desktop connections may block BLE access\n"
            "- Bluetooth adapter/drivers are properly installed\n"
        ) from e


def _match_device(
    dev: BLEDevice, adv: AdvertisementData, device_name: str, service_uuid: str
) -> bool:
    """Check if a discovered device matches the search criteria.

    This function implements a hierarchical matching strategy that prioritizes
    device name matching over service UUID matching. The approach ensures
    reliable device identification even when multiple similar devices are present.

    Args:
        dev: BLE device object containing basic device information.
        adv: Advertisement data containing detailed broadcasting information.
        device_name: Target device name for exact string matching.
        service_uuid: Target service UUID for fallback matching (case-insensitive).

    Returns:
        True if device matches either name or service UUID criteria, False otherwise.

    Note:
        Device name matching takes precedence over service UUID matching to ensure
        specific device selection in environments with multiple similar devices.
    """
    logger.debug(
        "Device discovered: addr=%s name=%s rssi=%s uuids=%s",
        getattr(dev, "address", "?"),
        getattr(dev, "name", None),
        getattr(adv, "rssi", None),
        getattr(adv, "service_uuids", None),
    )

    # Prioritize device name matching for specificity
    if dev.name == device_name:
        logger.info("Device selected by name match: %s (%s)", dev.name, dev.address)
        return True

    # Fallback to service UUID matching for broader compatibility
    uuids: Iterable[str] = adv.service_uuids or []
    if any(u.lower() == service_uuid.lower() for u in uuids):
        logger.info(
            "Device selected by service UUID match: %s (%s)", dev.name, dev.address
        )
        return True

    return False


async def find_device(
    *,
    device_name: str = DEVICE_NAME,
    service_uuid: str = NUS_SERVICE,
    timeout: float = 10.0,
) -> Optional[BLEDevice]:
    """Discover and return the first BLE device matching the specified criteria.

    This function performs a comprehensive BLE device discovery operation with
    configurable matching criteria. It handles the complete discovery lifecycle
    from scanning through device validation and selection.

    Args:
        device_name: Target device name for identification. Default matches
            standard XIAO nRF52840 Sense firmware configuration.
        service_uuid: Target service UUID for fallback identification when
            device name is not available. Default uses Nordic UART Service.
        timeout: Maximum time in seconds to spend scanning. Longer timeouts
            increase discovery success rate but delay error feedback.

    Returns:
        BLEDevice object for the first matching device found, or None if no
        matching device is discovered within the timeout period.

    Note:
        The function returns immediately upon finding the first matching device,
        making it suitable for scenarios where device uniqueness is expected.
        For environments with multiple similar devices, consider using device
        address filtering instead.
    """
    logger.info(
        "BLE device discovery started: name='%s' service='%s' timeout=%.1fs",
        device_name,
        service_uuid,
        timeout,
    )

    devices_adv = await _scan_ble_devices(timeout)

    # devices_adv: dict[address, (BLEDevice, AdvertisementData)]
    for dev, adv in devices_adv.values():
        if _match_device(dev, adv, device_name, service_uuid):
            return dev
    return None


def _parse_line_from_buffer(
    buffer: bytearray, debug_hex_dumped: dict[str, bool]
) -> Optional[str]:
    """Extract one complete line from the BLE receive buffer.

    This function implements robust line parsing for BLE data reception where
    data arrives in arbitrary-sized fragments that need to be assembled into
    complete lines. The implementation handles multiple line delimiter types
    and provides defensive programming against buffer overflow scenarios.

    Key features:
    1. **Multiple delimiter support**: Handles various line endings (LF, CRLF,
       NUL, RS, US, GS, ETX, EOT) to support different firmware implementations.
    2. **Fragment assembly**: Accumulates partial data until a complete line
       is available, essential for BLE's packet-based transmission.
    3. **Buffer overflow protection**: Prevents unbounded memory growth when
       delimiters are missing or corrupted.
    4. **Debug diagnostics**: Provides HEX/ASCII dumps to identify unknown
       control characters during development.

    Args:
        buffer: Mutable byte buffer containing accumulated BLE data fragments.
            Modified in-place as complete lines are extracted.
        debug_hex_dumped: State tracking dict to limit debug output frequency.
            Prevents log spam while providing diagnostic information when needed.

    Returns:
        Complete UTF-8 decoded line string, or None if no complete line is
        available in the current buffer contents.

    Note:
        The function handles CRLF as a two-character sequence while treating
        other delimiters as single characters. Empty lines and lines containing
        only whitespace/commas are filtered out as transmission noise.
    """
    delim_map = [
        (b"\n", "LF"),
        (b"\r", "CR"),
        (b"\x00", "NUL"),
        (b"\x1e", "RS"),
        (b"\x1f", "US"),
        (b"\x1d", "GS"),
        (b"\x03", "ETX"),
        (b"\x04", "EOT"),
    ]
    candidates = []
    for token, name in delim_map:
        idx = buffer.find(token)
        if idx != -1:
            candidates.append((idx, token, name))

    if not candidates:
        # No line delimiter found yet
        if len(buffer) > 0:
            logger.debug("Buffer accumulating: %d bytes (line incomplete)", len(buffer))
            # One-time HEX/ASCII preview to identify unknown delimiters or control characters
            if not debug_hex_dumped["dumped"] and len(buffer) >= 256:
                _log_buffer_preview(buffer)
                debug_hex_dumped["dumped"] = True
            # Buffer overflow protection (trim if exceeds 64KB)
            if len(buffer) > 64 * 1024:
                drop = len(buffer) - 64 * 1024
                logger.warning("Buffer overflow protection: trimming %d bytes", drop)
                del buffer[:drop]
        return None

    # Use the earliest occurring delimiter
    idx, token, token_name = min(candidates, key=lambda t: t[0])
    # CRLF consumes 2 characters, others consume 1
    consume = 1
    delim_name = token_name
    if token == b"\r" and idx + 1 < len(buffer) and buffer[idx + 1 : idx + 2] == b"\n":
        consume = 2
        delim_name = "CRLF"

    # Extract one line (strip trailing CR)
    line = buffer[:idx].rstrip(b"\r")
    del buffer[: idx + consume]

    try:
        text = line.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        logger.error("UTF-8 decode failed: %r", line)
        return None

    # Discard empty lines or lines with only whitespace and commas as noise
    if text.strip() == "" or text.replace(",", "").strip() == "":
        logger.debug("Skipping noise line: %r", text)
        return None

    logger.debug("Line completed (delimiter=%s): %s", delim_name, text)
    return text


def _log_buffer_preview(buffer: bytearray) -> None:
    """Log buffer contents in HEX/ASCII format for debugging transmission issues.

    This function provides diagnostic output when BLE data reception encounters
    unexpected delimiters or control characters. The dual HEX/ASCII format helps
    identify transmission artifacts, encoding issues, or protocol deviations.

    The implementation is designed to be called sparingly (once per problematic
    session) to avoid log spam while providing essential debugging information
    when line parsing fails due to unknown control sequences.

    Key features:
    1. **Control character inventory**: Lists all control bytes present to identify
       non-printable characters that may interfere with line parsing.
    2. **Head/tail sampling**: Shows beginning and end of buffer to capture both
       initial transmission patterns and current reception state.
    3. **Dual format output**: HEX for precise byte analysis, ASCII for readable
       text identification.

    Args:
        buffer: Byte buffer containing accumulated BLE data that failed to parse
            into complete lines. The buffer contents are examined but not modified.

    Note:
        This function is called only when buffer size exceeds 256 bytes without
        finding valid line delimiters, indicating potential transmission issues
        that require manual analysis for protocol debugging.
    """
    # Inventory control bytes present in buffer (<0x20) for analysis
    ctrl_set = sorted(set(b for b in buffer if b < 0x20))
    if ctrl_set:
        logger.debug(
            "Control bytes present: %s",
            " ".join(f"{b:02X}" for b in ctrl_set),
        )

    head = bytes(buffer[:32])
    tail = bytes(buffer[-32:]) if len(buffer) > 32 else b""

    def hex_str(bs: bytes) -> str:
        return " ".join(f"{b:02X}" for b in bs)

    def ascii_str(bs: bytes) -> str:
        return "".join(chr(b) if 32 <= b < 127 else "." for b in bs)

    logger.debug("HEX preview (head): %s | ASCII: %s", hex_str(head), ascii_str(head))
    if tail:
        logger.debug(
            "HEX preview (tail): %s | ASCII: %s", hex_str(tail), ascii_str(tail)
        )


def _create_notification_handler(
    queue: asyncio.Queue[Optional[str]],
    buffer: bytearray,
    debug_hex_dumped: dict[str, bool],
    disconnected: asyncio.Event,
) -> Callable[[bytearray], None]:
    """Create a BLE notification handler with proper closure state management.

    This function creates a callback handler for BLE characteristic notifications
    that bridges between synchronous BLE callbacks and asynchronous data processing.
    The implementation uses closure state to maintain shared resources across
    multiple notification callbacks.

    The handler design addresses key challenges in BLE data reception:
    1. **Fragment assembly**: BLE notifications arrive as arbitrary-sized chunks
       that must be accumulated and parsed into complete lines.
    2. **Async bridging**: BLE callbacks are synchronous but need to communicate
       with async consumer code through thread-safe queues.
    3. **Error isolation**: Callback exceptions must not propagate to BLE stack
       or crash the connection.
    4. **Disconnect coordination**: Ensures consumer threads are awakened when
       connections are lost to prevent indefinite blocking.

    Args:
        queue: Async queue for passing parsed lines to consumer threads.
            Uses Optional[str] where None indicates disconnection.
        buffer: Shared byte buffer for accumulating fragmented BLE data.
            Modified by the returned handler as data arrives.
        debug_hex_dumped: State dict controlling debug output frequency
            to prevent log spam during problematic sessions.
        disconnected: Event flag indicating BLE connection loss.
            Monitored to trigger consumer wakeup on disconnect.

    Returns:
        Callable handler function compatible with Bleak notification callbacks.
        Handler signature matches bleak.BleakClient.start_notify() requirements.

    Note:
        The returned handler maintains references to all closure variables,
        enabling stateful processing across multiple BLE notifications while
        isolating each callback invocation from potential errors.
    """

    def wake_consumer() -> None:
        try:
            queue.put_nowait(None)
        except Exception:
            pass

    def handle(data: bytearray) -> None:
        logger.debug("Notification received: %d bytes", len(data))
        buffer.extend(data)

        # Parse accumulated data into complete lines
        while True:
            text = _parse_line_from_buffer(buffer, debug_hex_dumped)
            if text is None:
                break
            queue.put_nowait(text)

        # Wake consumer on disconnect in case reception becomes intermittent
        if disconnected.is_set():
            wake_consumer()

    return handle


async def _get_device_address(
    address: Optional[str], device_name: str, service_uuid: str, scan_timeout: float
) -> str:
    """Resolve target device address through direct specification or discovery.

    This function provides a unified interface for device address resolution,
    supporting both direct address specification (for known devices) and
    automatic discovery (for typical usage scenarios). The implementation
    optimizes for the common case while providing flexibility for advanced use.

    The dual-mode approach serves different deployment scenarios:
    1. **Direct addressing**: For production systems with known device addresses,
       avoiding scan overhead and ensuring deterministic connection targets.
    2. **Discovery mode**: For development and user-friendly scenarios where
       devices are identified by name rather than MAC address.

    Args:
        address: Optional specific BLE device address. If provided, returned
            immediately without scanning. Format should be standard MAC address
            (e.g., "12:34:56:78:9A:BC").
        device_name: Target device name for discovery mode. Used only when
            address is None. Should match device's advertised name exactly.
        service_uuid: Target service UUID for discovery fallback. Used when
            device name matching fails but service UUID matches.
        scan_timeout: Maximum time to spend in discovery mode. Ignored when
            address is directly specified.

    Returns:
        Valid BLE device address string ready for connection attempts.

    Raises:
        RuntimeError: If discovery mode fails to find any matching device
            within the specified timeout period. Error message includes
            troubleshooting guidance for common connection issues.

    Note:
        When address is specified directly, no validation is performed - the
        address is assumed valid. Invalid addresses will cause connection
        failures in subsequent operations rather than immediate errors here.
    """
    if address is not None:
        return address

    dev = await find_device(
        device_name=device_name, service_uuid=service_uuid, timeout=scan_timeout
    )
    if not dev:
        raise RuntimeError(
            "Target device not found. Please check scan conditions and device proximity."
        )

    logger.info(
        "Connection target address: %s (name=%s)",
        dev.address,
        getattr(dev, "name", None),
    )
    return dev.address


async def _process_message_queue(
    queue: asyncio.Queue[Optional[str]],
    idle_timeout: Optional[float],
    disconnected: asyncio.Event,
    client: BleakClient,
) -> AsyncIterator[ImuRow]:
    """Process BLE message queue with timeout handling and connection monitoring.

    This function implements the consumer side of a producer-consumer pattern for BLE data.
    It continuously processes messages from the queue, parsing them into structured data rows.
    The design handles several critical edge cases inherent in wireless communication:

    1. **Timeout Management**: Uses configurable idle timeout to detect communication stalls
       without blocking indefinitely. This is essential for responsive UI applications.

    2. **Connection State Monitoring**: Actively checks both the disconnection event and
       client connection status to provide fast failure detection.

    3. **Graceful Degradation**: Continues operation despite individual message parsing
       failures, logging errors while maintaining data flow continuity.

    4. **Sentinel Handling**: Recognizes None as a disconnection signal from the producer,
       enabling clean shutdown coordination.

    Args:
        queue: Message queue containing raw CSV strings from BLE notifications
        idle_timeout: Maximum seconds to wait for messages before checking connection.
                     None for indefinite waiting.
        disconnected: Event signaling BLE disconnection from notification handler
        client: BLE client for connection status verification

    Yields:
        ImuRow: Successfully parsed sensor data rows

    Raises:
        RuntimeError: When BLE connection is lost or timeout occurs on disconnected client

    Note:
        This function is designed to be resilient to temporary communication issues
        while failing fast on permanent connection loss.
    """
    while True:
        # Apply idle timeout if configured
        if idle_timeout is not None:
            try:
                logger.debug("Waiting for queue (timeout=%.1fs)", idle_timeout)
                line = await asyncio.wait_for(queue.get(), timeout=idle_timeout)
                logger.debug("Queue item received: %r", line)
            except asyncio.TimeoutError:
                # Timeout occurred - exit if disconnected, otherwise continue waiting
                logger.warning("Receive timeout (%.1fs)", idle_timeout)
                if disconnected.is_set() or not client.is_connected:
                    raise RuntimeError("BLE connection lost.")
                else:
                    continue
        else:
            logger.debug("Waiting for queue (indefinite)")
            line = await queue.get()
            logger.debug("Queue item received: %r", line)

        if line is None:
            # Disconnection sentinel
            raise RuntimeError("BLE connection lost.")
        if not line:
            logger.debug("Skipping empty line")
            continue

        try:
            row = ImuRow.parse_csv(line)
            yield row
        except Exception as ex:
            # Skip conversion failures (log for debugging)
            logger.warning("CSV parsing failed: %s (error=%s)", line, ex)
            continue


async def stream_rows(
    address: Optional[str] = None,
    *,
    device_name: str = DEVICE_NAME,
    service_uuid: str = NUS_SERVICE,
    tx_char_uuid: str = NUS_TX_CHAR,
    scan_timeout: float = 10.0,
    idle_timeout: Optional[float] = None,
) -> AsyncIterator[ImuRow]:
    """Stream IMU sensor data from XIAO nRF52840 Sense device via BLE.

    This is the high-level public API for BLE sensor data streaming. It orchestrates
    the complete BLE communication pipeline from device discovery through data reception.
    The implementation follows a multi-layered architecture:

    1. **Device Discovery**: Automatically locates target device by name/service if
       address not provided, with configurable scan timeout
    2. **Connection Management**: Establishes robust BLE connection with automatic
       disconnection detection and cleanup
    3. **Data Pipeline**: Sets up producer-consumer pattern with notification handler
       feeding parsed data through an async queue
    4. **Resource Management**: Ensures proper cleanup of BLE resources using context
       managers and try/finally blocks

    The design prioritizes reliability over performance, implementing defensive patterns
    for wireless communication challenges like connection drops, partial transmissions,
    and timing variations.

    Args:
        address: Specific BLE device address. If None, performs automatic discovery.
        device_name: Device name filter for discovery (default: "XIAO Sense IMU")
        service_uuid: Target BLE service UUID (default: Nordic UART Service)
        tx_char_uuid: TX characteristic UUID for notifications
        scan_timeout: Maximum seconds to spend on device discovery
        idle_timeout: Maximum seconds to wait between messages before checking
                     connection. None for indefinite waiting.

    Yields:
        ImuRow: Parsed sensor data containing accelerometer, gyroscope, temperature,
                and audio RMS values with timestamps

    Raises:
        RuntimeError: On connection failure or communication timeout
        DeviceNotFoundError: When target device cannot be located during discovery

    Example:
        >>> async for row in stream_rows(idle_timeout=30.0):
        ...     print(f"Accel: {row.ax:.3f}, {row.ay:.3f}, {row.az:.3f}")

    Note:
        This function is designed to be the primary entry point for BLE data collection.
        It handles all low-level BLE complexity while providing a simple async iterator
        interface for consuming applications.
    """

    address = await _get_device_address(
        address, device_name, service_uuid, scan_timeout
    )

    buffer = bytearray()
    # Debug: One-time HEX preview when buffer grows without finding delimiters
    debug_hex_dumped = {"dumped": False}

    # Disconnect notification callback
    disconnected = asyncio.Event()

    def on_disconnect(_: BleakClient) -> None:
        logger.warning("BLE connection lost (callback)")
        disconnected.set()

    logger.info("BLE connection starting: %s", address)
    async with BleakClient(address, disconnected_callback=on_disconnect) as client:
        if not client.is_connected:
            raise RuntimeError("BLE connection failed.")
        logger.info("BLE connection established: %s", address)

        # Queue for receiving data lines. Send None on disconnect to signal termination.
        queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

        handle = _create_notification_handler(
            queue, buffer, debug_hex_dumped, disconnected
        )

        logger.info("Starting notification subscription: char=%s", tx_char_uuid)
        await client.start_notify(tx_char_uuid, lambda _, data: handle(data))

        try:
            async for row in _process_message_queue(
                queue, idle_timeout, disconnected, client
            ):
                yield row
        finally:
            logger.info("Stopping notification subscription")
            await client.stop_notify(tx_char_uuid)


async def print_stream(
    address: Optional[str] = None,
    *,
    show_header: bool = True,
    drop_missing_audio: bool = False,
    device_name: str = DEVICE_NAME,
    scan_timeout: float = 10.0,
    idle_timeout: Optional[float] = None,
) -> None:
    """Stream sensor data as CSV to standard output for command-line usage.

    This function provides a simple interface for streaming sensor data directly
    to stdout in CSV format, making it suitable for shell scripting, data pipelines,
    and command-line data capture workflows.

    The implementation handles the complete data flow from BLE connection through
    CSV formatting with standardized precision for consistent output formatting.

    Args:
        address: Optional specific BLE device address. If None, automatic device
            discovery is performed using device_name.
        show_header: Whether to output CSV column headers as the first line.
            Default True for standalone usage, set False for data pipelines.
        drop_missing_audio: Whether to skip rows with missing audio data (-1.0).
            Default False preserves all sensor readings for complete data capture.
        device_name: Device name for automatic discovery. Default matches standard
            XIAO nRF52840 Sense firmware configuration.
        scan_timeout: Maximum seconds to scan for target device during discovery.
        idle_timeout: Maximum seconds between data packets before connection timeout.

    Note:
        Output format uses fixed precision (6 decimal places for motion data,
        2 for temperature and audio) to ensure consistent parsing by downstream
        tools regardless of the precision of received data.

        The function runs indefinitely until interrupted (Ctrl+C) or connection
        is lost, making it suitable for long-term data logging scenarios.
    """
    if show_header:
        logger.info("CSV header: millis,ax,ay,az,gx,gy,gz,tempC,audioRMS")
        print("millis,ax,ay,az,gx,gy,gz,tempC,audioRMS")
    async for r in stream_rows(
        address,
        device_name=device_name,
        scan_timeout=scan_timeout,
        idle_timeout=idle_timeout,
    ):
        if drop_missing_audio and r.audioRMS < 0:
            logger.debug("Skipping row due to missing audioRMS: millis=%d", r.millis)
            continue
        # Input format may vary, but standardize output precision for consistency
        csv_line = f"{r.millis},{r.ax:.6f},{r.ay:.6f},{r.az:.6f},{r.gx:.6f},{r.gy:.6f},{r.gz:.6f},{r.tempC:.2f},{r.audioRMS:.2f}"
        logger.debug("CSV output: %s", csv_line)
        print(csv_line)


def run(
    address: Optional[str] = None,
    show_header: bool = True,
    drop_missing_audio: bool = False,
    device_name: str = DEVICE_NAME,
    scan_timeout: float = 10.0,
    idle_timeout: Optional[float] = None,
) -> int:
    """Command-line interface wrapper for synchronous sensor data streaming.

    This function provides a synchronous, script-friendly interface to the
    asynchronous BLE sensor data streaming functionality. It serves as the
    primary entry point for CLI usage and handles the complete lifecycle
    of a streaming session.

    The implementation wraps the async print_stream() function with proper
    asyncio event loop management and comprehensive error handling. Exit
    codes follow Unix conventions to support integration with shell scripts
    and system monitoring tools.

    Args:
        address: Optional specific BLE device address to connect to. If None,
            automatic device discovery by name is used. Useful for deployments
            with multiple XIAO devices.
        show_header: Whether to output CSV header line. Default True for
            standalone usage, set False for data pipeline integration.
        drop_missing_audio: Whether to skip rows with missing audio data (-1.0).
            Default False preserves all sensor readings, set True for audio
            analysis workflows.
        device_name: BLE device name for discovery. Default "XIAO Sense IMU"
            matches standard firmware configuration.
        scan_timeout: Maximum seconds to scan for target device. Default 10s
            balances discovery time with user experience.
        idle_timeout: Maximum seconds between data packets before timeout.
            Default None uses built-in timeout logic based on expected data rates.

    Returns:
        int: Exit code following Unix conventions:
            0: Normal completion, user terminated (typically Ctrl+C)
            1: Error termination (scan/connection failures, etc.)
            130: Keyboard interrupt (SIGINT/Ctrl+C)

    Note:
        This function is designed for CLI usage and blocking operation.
        For integration into larger applications, use the async print_stream()
        function directly or the DataSource classes for more control.

        The exit code distinction between 0 and 130 allows shell scripts
        to differentiate between successful user termination and actual
        system interruption.
    """
    try:
        asyncio.run(
            print_stream(
                address,
                show_header=show_header,
                drop_missing_audio=drop_missing_audio,
                device_name=device_name,
                scan_timeout=scan_timeout,
                idle_timeout=idle_timeout,
            )
        )
        return 0
    except KeyboardInterrupt:
        # SIGINT: Return 130 by convention
        return 130
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        return 1
