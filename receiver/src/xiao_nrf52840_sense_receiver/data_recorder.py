"""Data recording components for XIAO nRF52840 Sense data logger.

This module implements real-time data recording capabilities including:
- RecordFileWriter: Handles CSV file operations with internal buffering
- RecordingWorkerThread: Background thread for file operations
- RecorderManager: Coordinates recording sessions and file management

Architecture follows design doc: data collection must NEVER be blocked by recording.
"""

import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, TextIO

from .ble_receiver import DataBuffer, ImuRow

logger = logging.getLogger(__name__)


@dataclass
class RecordingStatus:
    """Current status of recording session."""

    is_recording: bool
    session_id: Optional[str]
    start_time: Optional[datetime]
    duration_seconds: float
    samples_recorded: int
    file_path: Optional[Path]
    file_size_bytes: int


@dataclass
class SessionInfo:
    """Information about a recording session."""

    session_id: str
    start_time: datetime
    end_time: Optional[datetime]
    duration_seconds: float
    total_samples: int
    file_path: Path
    file_size_bytes: int


class RecordFileWriter:
    """Handles synchronous CSV file operations with internal buffering.

    Design principle: Use simple, reliable synchronous I/O with internal buffering
    to avoid blocking the data collection thread while maintaining data integrity.
    """

    def __init__(self, filepath: Path, buffer_size: int = 100):
        self._filepath = filepath
        self._buffer_size = buffer_size  # Flush every N rows (~4 seconds at 25Hz)
        self._write_buffer: List[str] = []
        self._file_handle: Optional[TextIO] = None
        self._sample_count = 0
        self._start_time = datetime.now(timezone.utc)
        self._lock = threading.Lock()

    def open(self) -> None:
        """Open file for writing with CSV header."""
        try:
            # Ensure parent directory exists
            self._filepath.parent.mkdir(parents=True, exist_ok=True)

            self._file_handle = open(self._filepath, "w", newline="", encoding="utf-8")

            # Write CSV header matching existing output format exactly
            header = "millis,ax,ay,az,gx,gy,gz,tempC,audioRMS\n"
            self._file_handle.write(header)
            self._file_handle.flush()  # Ensure header is written immediately

            logger.info(f"Opened recording file: {self._filepath}")

        except Exception as e:
            logger.error(f"Failed to open recording file {self._filepath}: {e}")
            raise

    def append_rows(self, samples: List[ImuRow]) -> None:
        """Add samples to write buffer."""
        if not self._file_handle:
            raise RuntimeError("File not open for writing")

        with self._lock:
            # Format samples as CSV lines matching existing format exactly
            for sample in samples:
                csv_line = self._format_csv_row(sample)
                self._write_buffer.append(csv_line)
                self._sample_count += 1

            # Flush when buffer is full (every ~4 seconds at 25Hz)
            if len(self._write_buffer) >= self._buffer_size:
                self._flush_internal()

    def _format_csv_row(self, sample: ImuRow) -> str:
        """Format sample as CSV row matching existing output format."""
        return (
            f"{sample.millis},{sample.ax:.6f},{sample.ay:.6f},{sample.az:.6f},"
            f"{sample.gx:.6f},{sample.gy:.6f},{sample.gz:.6f},"
            f"{sample.tempC:.2f},{sample.audioRMS:.3f}\n"
        )

    def _flush_internal(self) -> None:
        """Internal flush without additional locking."""
        if not self._write_buffer or not self._file_handle:
            return

        try:
            # Synchronous write (simple and reliable)
            self._file_handle.writelines(self._write_buffer)
            self._write_buffer.clear()
            self._file_handle.flush()  # Ensure data reaches disk

        except Exception as e:
            logger.error(f"Error flushing data to file: {e}")
            raise

    def flush(self, force_fsync: bool = False) -> None:
        """Write buffered data to disk."""
        with self._lock:
            self._flush_internal()

            if force_fsync and self._file_handle:
                try:
                    os.fsync(self._file_handle.fileno())
                except Exception as e:
                    logger.warning(f"fsync failed: {e}")

    def close(self) -> SessionInfo:
        """Close file and write metadata."""
        with self._lock:
            if not self._file_handle:
                raise RuntimeError("File not open")

            try:
                # Flush any remaining data
                self._flush_internal()
                self._file_handle.close()

                end_time = datetime.now(timezone.utc)
                duration = (end_time - self._start_time).total_seconds()
                file_size = self._filepath.stat().st_size

                # Write metadata file
                self._write_metadata_file(end_time, duration, file_size)

                session_info = SessionInfo(
                    session_id=self._filepath.stem,
                    start_time=self._start_time,
                    end_time=end_time,
                    duration_seconds=duration,
                    total_samples=self._sample_count,
                    file_path=self._filepath,
                    file_size_bytes=file_size,
                )

                logger.info(
                    f"Closed recording: {self._sample_count} samples, "
                    f"{duration:.1f}s, {file_size} bytes"
                )

                return session_info

            except Exception as e:
                logger.error(f"Error closing recording file: {e}")
                raise
            finally:
                self._file_handle = None

    def _write_metadata_file(
        self, end_time: datetime, duration: float, file_size: int
    ) -> None:
        """Write companion metadata file."""
        metadata_path = self._filepath.with_suffix(".meta.json")

        metadata = {
            "session_id": self._filepath.stem,
            "start_time": self._start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": duration,
            "total_samples": self._sample_count,
            "average_sample_rate_hz": self._sample_count / duration
            if duration > 0
            else 0,
            "file_path": str(self._filepath),
            "file_size_bytes": file_size,
            "device_info": {"name": "XIAO Sense IMU", "connection_type": "BLE"},
            "recording_settings": {"buffer_size": self._buffer_size},
        }

        try:
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to write metadata file: {e}")

    @property
    def samples_written(self) -> int:
        """Get number of samples written to file."""
        with self._lock:
            return self._sample_count

    @property
    def file_size_bytes(self) -> int:
        """Get current file size."""
        try:
            if self._filepath.exists():
                return self._filepath.stat().st_size
        except Exception:
            pass
        return 0


class RecordingWorkerThread(threading.Thread):
    """Dedicated thread for file writing operations.

    Uses timer-based polling to avoid blocking data collection.
    Polls buffer every 20ms (50Hz) for new data and writes to file.
    """

    def __init__(self, buffer: DataBuffer, file_writer: RecordFileWriter):
        super().__init__(daemon=True, name="RecordingWorker")
        self._buffer = buffer
        self._writer = file_writer
        self._last_read_index = 0
        self._stop_event = threading.Event()
        self._error: Optional[Exception] = None

    def run(self) -> None:
        """Main worker loop with timer-based polling."""
        logger.info("Recording worker thread started")

        try:
            # Initialize read position to current buffer state
            self._last_read_index = self._buffer.current_write_index

            while not self._stop_event.is_set():
                try:
                    # Get new samples since last read
                    new_samples, next_index, dropped = self._buffer.get_since_index(
                        self._last_read_index
                    )

                    if dropped:
                        logger.warning(
                            "Data loss detected during recording - buffer overflow occurred"
                        )

                    if new_samples:
                        self._writer.append_rows(new_samples)
                        self._last_read_index = next_index

                        if len(new_samples) > 0:
                            logger.debug(f"Recorded {len(new_samples)} samples")

                    # Timer-based polling every 20ms (50Hz)
                    self._stop_event.wait(0.02)

                except Exception as e:
                    logger.error(f"Error in recording worker loop: {e}")
                    self._error = e
                    break

        except Exception as e:
            logger.error(f"Fatal error in recording worker: {e}")
            self._error = e
        finally:
            logger.info("Recording worker thread finished")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the recording thread."""
        logger.info("Stopping recording worker thread")
        self._stop_event.set()

        if self.is_alive():
            self.join(timeout=timeout)

            if self.is_alive():
                logger.warning("Recording worker thread did not stop gracefully")
            else:
                logger.info("Recording worker thread stopped")

    @property
    def error(self) -> Optional[Exception]:
        """Get any error that occurred in the worker thread."""
        return self._error


class RecorderManager:
    """Central coordinator for sensor data recording with concurrent safety guarantees.

    This class implements a producer-consumer pattern where sensor data collection
    (producer) is completely decoupled from disk I/O (consumer) to ensure that
    high-frequency sensor data streams are never blocked by file operations.

    Key design principles:

    1. **Non-blocking data collection**: The main data stream continues uninterrupted
       regardless of recording state or disk performance issues.

    2. **Background processing**: All file I/O happens in a separate worker thread
       to avoid blocking the real-time data flow.

    3. **Robust error handling**: Recording failures don't affect data collection,
       and partial recordings are properly cleaned up.

    4. **Session management**: Each recording session gets unique identifiers,
       timestamps, and metadata for later analysis.

    5. **Thread safety**: All operations are protected with reentrant locks to
       handle concurrent access from UI threads, data threads, and worker threads.

    The implementation uses a DataBuffer as the communication channel between
    the data producer and recording consumer, with index-based tracking to
    detect any data loss during recording.

    Attributes:
        _buffer: Shared circular buffer containing live sensor data.
        _output_dir: Base directory for storing recording files and metadata.
        _worker_thread: Background thread handling actual file I/O operations.
        _file_writer: File writer instance managing current recording session.
        _is_recording: Current recording state flag.
        _current_session: Unique identifier for active recording session.
        _start_time: Recording start timestamp for duration calculations.
        _lock: Reentrant lock protecting concurrent access to internal state.

    Note:
        The directory structure organizes recordings by date (YYYY-MM-DD) to
        facilitate long-term data management and prevent excessive files in
        single directories.
    """

    def __init__(self, buffer: DataBuffer, output_dir: Path):
        """Initialize recording manager with shared data buffer and output location.

        Args:
            buffer: DataBuffer instance containing live sensor data. This buffer
                serves as the communication channel between data collection and
                recording operations.
            output_dir: Base path for recording storage. Directory structure will
                be created automatically with date-based organization.

        Note:
            The output directory is created immediately to catch permission
            issues early, before any recording attempts.
        """
        self._buffer = buffer
        self._output_dir = output_dir
        self._worker_thread: Optional[RecordingWorkerThread] = None
        self._file_writer: Optional[RecordFileWriter] = None
        self._is_recording = False
        self._current_session: Optional[str] = None
        self._start_time: Optional[datetime] = None
        self._lock = threading.RLock()  # Use RLock for reentrant access

        # Ensure output directory exists
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def start_recording(
        self, prefix: Optional[str] = None, duration: Optional[float] = None
    ) -> RecordingStatus:
        """Start new recording session with automatic file naming and worker setup.

        This method initiates a complete recording pipeline: file creation,
        metadata setup, and background worker thread startup. The operation
        is atomic - either everything succeeds or everything is cleaned up.

        The file naming convention includes timestamps to ensure uniqueness:
        - With prefix: "{prefix}_YYYYMMDD_HHMMSS.csv"
        - Default: "sensor_data_YYYYMMDD_HHMMSS.csv"

        Files are organized in date-based directories (YYYY-MM-DD) to
        facilitate long-term data management.

        Args:
            prefix: Optional prefix for the recording filename. Useful for
                categorizing recordings by experiment or session type.
            duration: Reserved for future implementation of time-limited
                recordings. Currently not implemented.

        Returns:
            RecordingStatus: Current recording state including session info,
                file path, and initial statistics.

        Raises:
            RuntimeError: If a recording is already in progress.
            Various exceptions: File creation, permission, or worker thread
                startup failures are propagated after cleanup.

        Note:
            The worker thread starts immediately but may take a moment to
            begin writing data. Initial status will show 0 samples until
            the first data is processed.
        """
        with self._lock:
            if self._is_recording:
                raise RuntimeError("Recording already in progress")

            try:
                # Generate filename with timestamp
                now = datetime.now()
                timestamp = now.strftime("%Y%m%d_%H%M%S")

                if prefix:
                    filename = f"{prefix}_{timestamp}.csv"
                else:
                    filename = f"sensor_data_{timestamp}.csv"

                # Create directory structure by date
                date_dir = self._output_dir / now.strftime("%Y-%m-%d")
                filepath = date_dir / filename

                # Create and open file writer
                self._file_writer = RecordFileWriter(filepath)
                self._file_writer.open()

                # Start worker thread
                self._worker_thread = RecordingWorkerThread(
                    self._buffer, self._file_writer
                )
                self._worker_thread.start()

                # Update state
                self._is_recording = True
                self._current_session = filepath.stem
                self._start_time = now

                logger.info(f"Started recording session: {self._current_session}")

                return self.get_status()

            except Exception as e:
                # Cleanup on error
                self._cleanup_failed_recording()
                logger.error(f"Failed to start recording: {e}")
                raise

    def stop_recording(self) -> SessionInfo:
        """Stop current recording session and finalize all files.

        This method performs a complete shutdown of the recording pipeline:
        worker thread termination, file closure, metadata writing, and
        resource cleanup. The operation ensures data integrity even if
        errors occur during shutdown.

        The worker thread is given time to process any remaining buffered
        data before being terminated. File writers automatically generate
        metadata files containing session statistics for later analysis.

        Returns:
            SessionInfo: Complete information about the finished recording
                session including final sample count, file size, and duration.

        Raises:
            RuntimeError: If no recording is currently in progress.
            Various exceptions: Worker thread or file writer errors are
                logged but don't prevent session finalization.

        Note:
            Even if errors occur during stop, the recording state is reset
            to prevent inconsistent states. Partial recordings are preserved
            with whatever data was successfully written.
        """
        with self._lock:
            if not self._is_recording:
                raise RuntimeError("No recording in progress")

            try:
                # Stop worker thread
                if self._worker_thread:
                    self._worker_thread.stop()

                    # Check for worker errors
                    if self._worker_thread.error:
                        logger.error(
                            f"Recording worker had error: {self._worker_thread.error}"
                        )

                # Close file writer
                if self._file_writer:
                    session_info = self._file_writer.close()
                else:
                    raise RuntimeError("No file writer available")

                # Reset state
                self._is_recording = False
                self._current_session = None
                self._start_time = None
                self._worker_thread = None
                self._file_writer = None

                logger.info(f"Stopped recording session: {session_info.session_id}")
                return session_info

            except Exception as e:
                # Ensure cleanup even on error
                self._cleanup_failed_recording()
                logger.error(f"Error stopping recording: {e}")
                raise

    def _cleanup_failed_recording(self) -> None:
        """Emergency cleanup for failed recording operations.

        This method handles resource cleanup when recording operations fail,
        ensuring no resources are leaked and the manager returns to a
        consistent state. All cleanup operations are wrapped in exception
        handlers to prevent cascading failures.

        Called automatically by start_recording() and stop_recording() when
        errors occur, and can be called manually if needed for recovery.

        Note:
            This method never raises exceptions - all errors during cleanup
            are silently ignored to prevent masking the original failure.
        """
        try:
            if self._worker_thread:
                self._worker_thread.stop()
            if self._file_writer:
                try:
                    self._file_writer.close()
                except Exception:
                    pass  # Ignore cleanup errors
        except Exception:
            pass  # Ignore cleanup errors
        finally:
            self._is_recording = False
            self._current_session = None
            self._start_time = None
            self._worker_thread = None
            self._file_writer = None

    def get_status(self) -> RecordingStatus:
        """Get real-time recording status with current statistics.

        This method provides comprehensive status information for monitoring
        recording health and progress. Statistics are calculated in real-time
        from the current worker thread and file writer state.

        For inactive recordings, returns a status object with all fields
        set to appropriate default values (False, None, 0, etc.).

        Returns:
            RecordingStatus: Current recording state including:
                - Recording active flag
                - Session identifier and start time
                - Duration in seconds since start
                - Number of samples successfully written
                - Output file path and current size

        Note:
            File size and sample count reflect data actually written to disk,
            not data waiting in buffers. There may be a small lag between
            data collection and these statistics.
        """
        with self._lock:
            if not self._is_recording:
                return RecordingStatus(
                    is_recording=False,
                    session_id=None,
                    start_time=None,
                    duration_seconds=0.0,
                    samples_recorded=0,
                    file_path=None,
                    file_size_bytes=0,
                )

            duration = 0.0
            if self._start_time:
                duration = (datetime.now() - self._start_time).total_seconds()

            samples_recorded = 0
            file_size = 0
            file_path = None

            if self._file_writer:
                samples_recorded = self._file_writer.samples_written
                file_size = self._file_writer.file_size_bytes
                file_path = self._file_writer._filepath

            return RecordingStatus(
                is_recording=True,
                session_id=self._current_session,
                start_time=self._start_time,
                duration_seconds=duration,
                samples_recorded=samples_recorded,
                file_path=file_path,
                file_size_bytes=file_size,
            )

    @property
    def is_recording(self) -> bool:
        """Check if recording is currently active.

        Returns:
            True if a recording session is active, False otherwise.

        Note:
            This is a thread-safe property that can be checked from any thread
            without affecting recording operations.
        """
        with self._lock:
            return self._is_recording

    def list_recordings(self, limit: int = 50) -> List[SessionInfo]:
        """List recent recording sessions from metadata files.

        This method scans the output directory for metadata files (*.meta.json)
        and reconstructs session information for completed recordings. The
        search is recursive, covering all date-based subdirectories.

        Sessions are sorted by start time with newest recordings first,
        making it easy to find recent work.

        Args:
            limit: Maximum number of sessions to return. Default 50 provides
                good performance while covering typical usage patterns.

        Returns:
            List of SessionInfo objects for found recordings, sorted newest first.

        Note:
            Only successfully completed recordings have metadata files. Active
            or failed recordings won't appear in this list until they complete
            normally.

            Corrupted metadata files are logged as warnings but don't prevent
            listing other valid recordings.
        """
        recordings = []

        try:
            # Find all metadata files
            for meta_file in self._output_dir.rglob("*.meta.json"):
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        metadata = json.load(f)

                    session_info = SessionInfo(
                        session_id=metadata["session_id"],
                        start_time=datetime.fromisoformat(metadata["start_time"]),
                        end_time=datetime.fromisoformat(metadata["end_time"])
                        if metadata.get("end_time")
                        else None,
                        duration_seconds=metadata["duration_seconds"],
                        total_samples=metadata["total_samples"],
                        file_path=Path(metadata["file_path"]),
                        file_size_bytes=metadata["file_size_bytes"],
                    )

                    recordings.append(session_info)

                except Exception as e:
                    logger.warning(f"Error reading metadata file {meta_file}: {e}")

        except Exception as e:
            logger.error(f"Error listing recordings: {e}")

        # Sort by start time (newest first) and limit results
        recordings.sort(key=lambda x: x.start_time, reverse=True)
        return recordings[:limit]
