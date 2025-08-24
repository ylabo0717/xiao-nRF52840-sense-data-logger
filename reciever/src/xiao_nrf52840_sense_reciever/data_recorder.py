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
    """Central coordinator for recording operations.

    Manages recording sessions and provides simple start/stop interface.
    Ensures data collection is never blocked by recording operations.
    """

    def __init__(self, buffer: DataBuffer, output_dir: Path):
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
        """Start a new recording session."""
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
        """Stop current recording session."""
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
        """Cleanup resources after failed recording."""
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
        """Get current recording status."""
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
        """Check if currently recording."""
        with self._lock:
            return self._is_recording

    def list_recordings(self, limit: int = 50) -> List[SessionInfo]:
        """List recent recording sessions."""
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
