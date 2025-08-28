"""
Dash application for oscilloscope visualization.
"""

import asyncio
import logging
import threading
from typing import Any, List, Optional, Tuple

import dash  # type: ignore
from dash import dcc, html, Input, Output

from ..ble_receiver import DataBuffer, DataSource
from .plots import create_multi_plot_layout

logger = logging.getLogger(__name__)


class OscilloscopeApp:
    """Real-time sensor data visualization application with comprehensive control interface.

    This class implements a complete web-based oscilloscope for XIAO nRF52840 Sense
    sensor data, providing real-time visualization, data recording, and interactive
    controls. The design prioritizes user experience and system reliability in
    challenging deployment scenarios.

    Architecture highlights:

    1. **Asynchronous data collection**: Background thread with asyncio event loop
       handles all BLE communication without blocking the web interface. This
       ensures responsive UI even during connection issues.

    2. **Producer-consumer decoupling**: Data collection (producer) and visualization
       (consumer) are completely independent. Visualization continues even if
       data source encounters issues.

    3. **Robust error handling**: Multiple retry mechanisms with exponential backoff
       handle the inherent instability of BLE connections. Connection failures
       don't crash the application.

    4. **Interactive data control**: Users can start/pause data collection independently
       of device connection, allowing selective data capture for experiments.

    5. **Integrated recording**: Built-in data recording with session management
       enables seamless data capture alongside visualization.

    6. **Responsive web interface**: Dash-based UI updates in real-time (15fps default)
       with configurable refresh rates and visualization parameters.

    The implementation handles the complex lifecycle of BLE connections while
    providing a stable, user-friendly interface for sensor data analysis.

    Attributes:
        data_source: Abstract data source (BLE or Mock) providing sensor readings.
        buffer: Thread-safe circular buffer storing live sensor data for visualization.
        update_interval: UI refresh interval in milliseconds (derived from FPS).
        recorder: Integrated recording manager for session-based data capture.
        app: Dash web application instance with complete UI layout.
        _data_thread: Background thread handling asynchronous data collection.
        _stop_event: Threading event for coordinated shutdown of background operations.
        _loop: Asyncio event loop dedicated to the data collection thread.
        _collection_paused: User-controlled pause state for selective data capture.
        _collection_running: Overall data collection state tracking.

    Note:
        The class is designed to be instantiated once per application session.
        Multiple instances may conflict due to shared BLE resources and port usage.
    """

    def __init__(
        self, data_source: DataSource, buffer_size: int = 1000, update_rate: int = 10
    ):
        """Initialize oscilloscope application with data source and performance parameters.

        Args:
            data_source: Data source implementation (BleDataSource for real devices,
                MockDataSource for testing). Must implement the DataSource interface.
            buffer_size: Maximum samples to retain in memory. Default 1000 provides
                ~40 seconds at 25Hz, balancing memory usage with visualization history.
                Larger values increase memory usage but provide longer time windows.
            update_rate: UI refresh rate in frames per second. Default 15fps balances
                responsiveness with CPU usage. Higher values increase system load.

        Note:
            Buffer size affects both memory usage and maximum displayable time window.
            Update rate impacts system performance - use lower values on resource-
            constrained systems.
        """
        self.data_source = data_source
        self.buffer = DataBuffer(max_size=buffer_size)
        self.update_interval = 1000 // update_rate  # Convert FPS to milliseconds

        # Background thread for data collection
        self._data_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Data collection control state
        self._collection_paused = False
        self._collection_running = False

        # Recording manager (new)
        from ..data_recorder import RecorderManager
        from pathlib import Path

        recordings_dir = Path.cwd() / "recordings"
        self.recorder = RecorderManager(self.buffer, recordings_dir)

        # Create Dash app
        self.app = dash.Dash(__name__)
        self._setup_layout()
        self._setup_callbacks()

    def _setup_layout(self) -> None:
        """Setup the comprehensive web interface layout with all control panels.

        Creates a sophisticated dashboard layout optimized for real-time sensor
        monitoring. The design provides immediate visual feedback on system status
        while offering granular control over data collection and visualization.

        Layout structure:
        - Header with application title
        - Top control row: Connection status, Buffer statistics, Recording controls
        - Second control row: Data collection controls, View controls, Plot visibility
        - Main visualization area with multi-sensor plots
        - Hidden state storage components for callback management

        The layout is designed for both desktop and tablet viewing, with responsive
        elements that adapt to different screen sizes.

        Note:
            The layout includes numerous interactive components (buttons, dropdowns,
            checklists) that are managed through Dash callbacks for real-time updates.
        """
        self.app.layout = html.Div(
            [
                html.H1(
                    "XIAO nRF52840 Sense - Oscilloscope", style={"textAlign": "center"}
                ),
                # Top control panels row
                html.Div(
                    [
                        html.Div(
                            [
                                html.H3("Connection Status"),
                                html.Div(
                                    id="connection-status", children="Initializing..."
                                ),
                                html.Div(id="connection-details", children=""),
                            ],
                            style={
                                "width": "30%",
                                "display": "inline-block",
                                "verticalAlign": "top",
                                "padding": "10px",
                                "border": "1px solid #ddd",
                                "borderRadius": "5px",
                                "margin": "5px",
                            },
                        ),
                        html.Div(
                            [
                                html.H3("Buffer Statistics"),
                                html.Div(id="buffer-stats", children="No data"),
                            ],
                            style={
                                "width": "35%",
                                "display": "inline-block",
                                "verticalAlign": "top",
                                "padding": "10px",
                                "border": "1px solid #ddd",
                                "borderRadius": "5px",
                                "margin": "5px",
                            },
                        ),
                        # Recording Controls Panel
                        html.Div(
                            [
                                html.H3("Recording Controls"),
                                html.Div(
                                    [
                                        html.Button(
                                            "🔴 Record",
                                            id="start-recording-btn",
                                            style={
                                                "marginRight": "10px",
                                                "padding": "8px 16px",
                                                "backgroundColor": "#dc3545",
                                                "color": "white",
                                                "border": "none",
                                                "borderRadius": "4px",
                                                "cursor": "pointer",
                                            },
                                        ),
                                        html.Button(
                                            "⏹️ Stop",
                                            id="stop-recording-btn",
                                            disabled=True,
                                            style={
                                                "marginRight": "10px",
                                                "padding": "8px 16px",
                                                "backgroundColor": "#6c757d",
                                                "color": "white",
                                                "border": "none",
                                                "borderRadius": "4px",
                                                "cursor": "pointer",
                                            },
                                        ),
                                    ],
                                    style={"marginBottom": "10px"},
                                ),
                                html.Div(
                                    id="recording-status", children="⚪ Ready to record"
                                ),
                                html.Div(id="recording-info", children=""),
                            ],
                            style={
                                "width": "30%",
                                "display": "inline-block",
                                "verticalAlign": "top",
                                "padding": "10px",
                                "border": "1px solid #ddd",
                                "borderRadius": "5px",
                                "margin": "5px",
                            },
                        ),
                    ],
                    style={"margin": "20px", "display": "flex", "gap": "10px"},
                ),
                # Second control panels row - Interactive Controls
                html.Div(
                    [
                        # Data Collection Controls
                        html.Div(
                            [
                                html.H3("Data Collection"),
                                html.Div(
                                    [
                                        html.Button(
                                            "▶️ Start Collection",
                                            id="start-collection-btn",
                                            style={
                                                "marginRight": "10px",
                                                "padding": "8px 16px",
                                                "backgroundColor": "#28a745",
                                                "color": "white",
                                                "border": "none",
                                                "borderRadius": "4px",
                                                "cursor": "pointer",
                                            },
                                        ),
                                        html.Button(
                                            "⏸️ Pause Collection",
                                            id="pause-collection-btn",
                                            disabled=True,
                                            style={
                                                "padding": "8px 16px",
                                                "backgroundColor": "#6c757d",
                                                "color": "white",
                                                "border": "none",
                                                "borderRadius": "4px",
                                                "cursor": "pointer",
                                            },
                                        ),
                                    ],
                                    style={"marginBottom": "10px"},
                                ),
                                html.Div(
                                    id="collection-status",
                                    children="⏹️ Collection Stopped",
                                ),
                            ],
                            style={
                                "width": "30%",
                                "display": "inline-block",
                                "verticalAlign": "top",
                                "padding": "10px",
                                "border": "1px solid #ddd",
                                "borderRadius": "5px",
                                "margin": "5px",
                            },
                        ),
                        # View Controls
                        html.Div(
                            [
                                html.H3("View Controls"),
                                html.Div(
                                    [
                                        html.Label(
                                            "Time Window:",
                                            style={
                                                "fontSize": "12px",
                                                "marginBottom": "5px",
                                            },
                                        ),
                                        dcc.Dropdown(
                                            id="time-window-dropdown",
                                            options=[
                                                {"label": "5 seconds", "value": 5},
                                                {"label": "10 seconds", "value": 10},
                                                {"label": "30 seconds", "value": 30},
                                                {"label": "60 seconds", "value": 60},
                                            ],
                                            value=5,  # Default to 5 seconds (~125 samples @ 25Hz)
                                            style={
                                                "marginBottom": "10px",
                                                "fontSize": "12px",
                                            },
                                        ),
                                        html.Div(
                                            [
                                                dcc.Checklist(
                                                    id="auto-scale-checklist",
                                                    options=[
                                                        {
                                                            "label": " Auto-scale Y-axis",
                                                            "value": "auto",
                                                        }
                                                    ],
                                                    value=[],  # Start with auto-scale off
                                                    style={"fontSize": "12px"},
                                                ),
                                                html.Div(
                                                    [
                                                        html.Label(
                                                            "Decimation (display only):",
                                                            style={
                                                                "fontSize": "12px",
                                                                "marginTop": "8px",
                                                                "marginBottom": "5px",
                                                            },
                                                        ),
                                                        dcc.Dropdown(
                                                            id="decimation-dropdown",
                                                            options=[
                                                                {"label": "x1 (no skip)", "value": 1},
                                                                {"label": "x2", "value": 2},
                                                                {"label": "x3", "value": 3},
                                                                {"label": "x4", "value": 4},
                                                                {"label": "x5", "value": 5},
                                                                {"label": "x10", "value": 10},
                                                                {"label": "x20", "value": 20},
                                                            ],
                                                            value=4,
                                                            style={
                                                                "marginBottom": "10px",
                                                                "fontSize": "12px",
                                                            },
                                                            clearable=False,
                                                        ),
                                                        html.Div(
                                                            "Rendering will down-sample points for plots only; acquisition and recording are unaffected.",
                                                            style={
                                                                "fontSize": "11px",
                                                                "color": "#666",
                                                            },
                                                        ),
                                                    ]
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                            ],
                            style={
                                "width": "35%",
                                "display": "inline-block",
                                "verticalAlign": "top",
                                "padding": "10px",
                                "border": "1px solid #ddd",
                                "borderRadius": "5px",
                                "margin": "5px",
                            },
                        ),
                        # Plot Visibility Controls
                        html.Div(
                            [
                                html.H3("Show/Hide Plots"),
                                dcc.Checklist(
                                    id="plot-visibility-checklist",
                                    options=[
                                        {"label": " Accelerometer", "value": "accel"},
                                        {"label": " Gyroscope", "value": "gyro"},
                                        {"label": " Temperature", "value": "temp"},
                                        {"label": " Audio", "value": "audio"},
                                    ],
                                    value=[
                                        "accel",
                                        "gyro",
                                        "temp",
                                        "audio",
                                    ],  # All visible by default
                                    style={"fontSize": "12px"},
                                ),
                            ],
                            style={
                                "width": "30%",
                                "display": "inline-block",
                                "verticalAlign": "top",
                                "padding": "10px",
                                "border": "1px solid #ddd",
                                "borderRadius": "5px",
                                "margin": "5px",
                            },
                        ),
                    ],
                    style={"margin": "20px", "display": "flex", "gap": "10px"},
                ),
                # Multi-sensor plots
                html.Div(
                    [
                        dcc.Graph(
                            id="multi-plot",
                            config={"displayModeBar": True},
                            style={"height": "650px"},
                        ),
                    ]
                ),
                # Update interval component
                dcc.Interval(
                    id="interval-component",
                    interval=self.update_interval,  # in milliseconds
                    n_intervals=0,
                ),
                # Hidden divs to store states
                html.Div(id="recording-state-store", style={"display": "none"}),
                html.Div(id="collection-state-store", style={"display": "none"}),
            ]
        )

    def _setup_callbacks(self) -> None:
        """Setup comprehensive Dash callbacks for real-time interface updates.

        This method registers all the callback functions that handle user interactions
        and automatic UI updates. The callback system handles complex state management
        across multiple UI components while maintaining responsive performance.

        Callback categories:
        1. **Main update callback**: Handles real-time plot updates, status displays,
           and button state management (runs at configured FPS)
        2. **Recording callbacks**: Handle recording start/stop user interactions
        3. **Collection callbacks**: Handle data collection start/pause user interactions

        The implementation uses Dash's dependency injection system to efficiently
        update only the UI components that need refreshing, minimizing browser
        rendering overhead.

        Note:
            Callbacks include comprehensive error handling and logging to support
            debugging in production deployments. State management ensures UI
            consistency even during error conditions.
        """

        @self.app.callback(  # type: ignore
            [
                Output("multi-plot", "figure"),
                Output("connection-status", "children"),
                Output("connection-details", "children"),
                Output("buffer-stats", "children"),
                Output("recording-status", "children"),
                Output("recording-info", "children"),
                Output("start-recording-btn", "disabled"),
                Output("stop-recording-btn", "disabled"),
                Output("start-recording-btn", "style"),
                Output("stop-recording-btn", "style"),
                # New interactive control outputs
                Output("collection-status", "children"),
                Output("start-collection-btn", "disabled"),
                Output("pause-collection-btn", "disabled"),
                Output("start-collection-btn", "style"),
                Output("pause-collection-btn", "style"),
            ],
            [
                Input("interval-component", "n_intervals"),
                Input("time-window-dropdown", "value"),
                Input("plot-visibility-checklist", "value"),
                Input("auto-scale-checklist", "value"),
                Input("decimation-dropdown", "value"),
            ],
        )
        def update_plots(
            n_intervals: int,
            time_window: int,
            visible_plots: List[str],
            auto_scale_list: List[str],
            decimation_factor: Optional[int],
        ) -> Tuple[Any, ...]:
            # Provide default values for optional inputs
            if time_window is None:
                time_window = 5
            if visible_plots is None:
                visible_plots = ["accel", "gyro", "temp", "audio"]
            if auto_scale_list is None:
                auto_scale_list = []
            if not decimation_factor:
                decimation_factor = 1

            # Get recent data based on time window
            if time_window and time_window > 0:
                sample_rate = 25  # Hz, approximate
                max_samples = int(time_window * sample_rate)
                data = self.buffer.get_recent(max_samples)
            else:
                data = self.buffer.get_recent(500)  # Default

            raw_points = len(data)

            # Decimate for rendering only (keep latest sample included)
            if decimation_factor > 1 and raw_points > 2:
                step = decimation_factor
                # Choose offset so the last element is retained
                offset = (raw_points - 1) % step
                decimated = data[offset::step]
                # Safety: ensure last sample is included
                if decimated and decimated[-1] is not data[-1]:
                    decimated = decimated + [data[-1]]
                data = decimated

            stats = self.buffer.stats
            auto_scale = "auto" in auto_scale_list if auto_scale_list else False

            # Enhanced connection status with startup detection
            buffer_has_data = self.buffer.size > 0
            data_source_type = type(self.data_source).__name__

            # Check if BLE is in startup phase
            is_ble_startup = (
                data_source_type == "BleDataSource"
                and not buffer_has_data
                and hasattr(self, "_data_thread")
                and self._data_thread is not None
                and self._data_thread.is_alive()
            )

            is_connected = buffer_has_data

            # Connection status logic
            if is_connected:
                if stats.sample_rate > 20:
                    connection_status = "🟢 Connected (Excellent)"
                    status_color = "green"
                elif stats.sample_rate > 15:
                    connection_status = "🟡 Connected (Good)"
                    status_color = "orange"
                else:
                    connection_status = "🔴 Connected (Poor)"
                    status_color = "red"
            elif is_ble_startup:
                connection_status = "🟡 Connecting to BLE device..."
                status_color = "orange"
            else:
                connection_status = "🔴 Disconnected"
                status_color = "red"

            # Debug logging - reduced frequency after fixing buffer issue
            if n_intervals % 100 == 0:  # Log every ~7 seconds at 15fps
                logger.debug(
                    f"🔍 UI Debug: Buffer size={self.buffer.size}, Sample rate={stats.sample_rate:.1f}Hz, Status: {connection_status}"
                )

            # Create multi-sensor plot layout with new parameters
            # 軽量化: 表示点数の上限キャップ（既定400）を適用
            multi_fig = create_multi_plot_layout(
                data,
                time_window_seconds=time_window,
                visible_plots=visible_plots,
                auto_scale=auto_scale,
                max_points_cap=400,
            )

            # Debug: Log connection status periodically
            if n_intervals % 60 == 0:  # Every ~4 seconds
                logger.debug(
                    f"🔍 UI Debug: is_connected={is_connected}, buffer_size={self.buffer.size}, "
                    f"stats.fill_level={stats.fill_level}, stats.sample_rate={stats.sample_rate:.1f}"
                )

            status_style = {
                "color": status_color,
                "fontWeight": "bold",
                "fontSize": "16px",
            }

            # Detailed connection information
            if data_source_type == "BleDataSource":
                if is_ble_startup:
                    device_info = "🔵 BLE Device: XIAO Sense IMU (connecting...)"
                else:
                    device_info = "🔵 BLE Device: XIAO Sense IMU"
            elif data_source_type == "MockDataSource":
                device_info = "🔵 Mock Device: Test Data"
            else:
                device_info = f"🔵 Device: {data_source_type}"

            connection_details = html.Div(
                [
                    html.P(device_info, style={"margin": "5px 0", "fontSize": "14px"}),
                    html.P(
                        f"⏱️ Update Rate: {stats.sample_rate:.1f} Hz",
                        style={"margin": "5px 0", "fontSize": "14px"},
                    ),
                    html.P(
                        f"📈 Buffer Fill: {stats.fill_level} samples",
                        style={"margin": "5px 0", "fontSize": "14px"},
                    ),
                ]
            )

            # Buffer statistics
            display_time = (raw_points / 25.0) if raw_points else 0
            buffer_info = html.Div(
                [
                    html.P(
                        f"Buffer Fill: {stats.fill_level}/{self.buffer.max_size} "
                        f"({stats.fill_level / self.buffer.max_size * 100:.1f}%)",
                        style={"margin": "5px 0"},
                    ),
                    html.P(
                        f"Displaying: {len(data)} points (from {raw_points} samples, x{decimation_factor})",
                        style={"margin": "5px 0"},
                    ),
                    html.P(
                        f"Time Window: {time_window}s",
                        style={"margin": "5px 0"},
                    ),
                    html.P(
                        f"Approx. Window Coverage: {display_time:.1f}s @ 25Hz",
                        style={"margin": "5px 0", "color": "#666", "fontSize": "12px"},
                    ),
                ]
            )

            # Get recording status
            recording_status_obj = self.recorder.get_status()

            # Recording status display
            if recording_status_obj.is_recording:
                recording_status_text = "🔴 Recording"
                recording_status_color = "red"
                start_rec_btn_disabled = True
                stop_rec_btn_disabled = False
                start_rec_btn_bg = "#6c757d"  # Gray when disabled
                stop_rec_btn_bg = "#dc3545"  # Red when active
            else:
                recording_status_text = "⚪ Ready to record"
                recording_status_color = "gray"
                start_rec_btn_disabled = False
                stop_rec_btn_disabled = True
                start_rec_btn_bg = "#dc3545"  # Red when active
                stop_rec_btn_bg = "#6c757d"  # Gray when disabled

            recording_status_display = html.Span(
                recording_status_text,
                style={
                    "color": recording_status_color,
                    "fontWeight": "bold",
                    "fontSize": "16px",
                },
            )

            # Recording information display
            if recording_status_obj.is_recording:
                duration_str = f"{recording_status_obj.duration_seconds:.1f}s"
                samples_str = f"{recording_status_obj.samples_recorded:,}"
                file_size_mb = recording_status_obj.file_size_bytes / 1024 / 1024

                recording_info_display = html.Div(
                    [
                        html.P(
                            f"⏱️ Duration: {duration_str}",
                            style={"margin": "2px 0", "fontSize": "12px"},
                        ),
                        html.P(
                            f"📊 Samples: {samples_str}",
                            style={"margin": "2px 0", "fontSize": "12px"},
                        ),
                        html.P(
                            f"💾 Size: {file_size_mb:.1f} MB",
                            style={"margin": "2px 0", "fontSize": "12px"},
                        ),
                    ]
                )
            else:
                recording_info_display = html.Div(
                    [
                        html.P(
                            "Click Record to start capturing data",
                            style={
                                "margin": "2px 0",
                                "fontSize": "12px",
                                "color": "#666",
                            },
                        ),
                    ]
                )

            # Data collection status and button states
            if self._collection_running and not self._collection_paused:
                collection_status_text = "▶️ Collection Running"
                collection_status_color = "green"
                start_coll_btn_disabled = True
                pause_coll_btn_disabled = False
                start_coll_btn_bg = "#6c757d"
                pause_coll_btn_bg = "#ffc107"  # Warning color for pause
            elif self._collection_running and self._collection_paused:
                collection_status_text = "⏸️ Collection Paused"
                collection_status_color = "orange"
                start_coll_btn_disabled = False
                pause_coll_btn_disabled = True
                start_coll_btn_bg = "#28a745"
                pause_coll_btn_bg = "#6c757d"
            else:
                collection_status_text = "⏹️ Collection Stopped"
                collection_status_color = "gray"
                start_coll_btn_disabled = False
                pause_coll_btn_disabled = True
                start_coll_btn_bg = "#28a745"
                pause_coll_btn_bg = "#6c757d"

            collection_status_display = html.Span(
                collection_status_text,
                style={
                    "color": collection_status_color,
                    "fontWeight": "bold",
                    "fontSize": "16px",
                },
            )

            # Button styles
            start_rec_btn_style = {
                "marginRight": "10px",
                "padding": "8px 16px",
                "backgroundColor": start_rec_btn_bg,
                "color": "white",
                "border": "none",
                "borderRadius": "4px",
                "cursor": "pointer" if not start_rec_btn_disabled else "not-allowed",
                "opacity": "0.6" if start_rec_btn_disabled else "1.0",
            }

            stop_rec_btn_style = {
                "marginRight": "10px",
                "padding": "8px 16px",
                "backgroundColor": stop_rec_btn_bg,
                "color": "white",
                "border": "none",
                "borderRadius": "4px",
                "cursor": "pointer" if not stop_rec_btn_disabled else "not-allowed",
                "opacity": "0.6" if stop_rec_btn_disabled else "1.0",
            }

            start_coll_btn_style = {
                "marginRight": "10px",
                "padding": "8px 16px",
                "backgroundColor": start_coll_btn_bg,
                "color": "white",
                "border": "none",
                "borderRadius": "4px",
                "cursor": "pointer" if not start_coll_btn_disabled else "not-allowed",
                "opacity": "0.6" if start_coll_btn_disabled else "1.0",
            }

            pause_coll_btn_style = {
                "padding": "8px 16px",
                "backgroundColor": pause_coll_btn_bg,
                "color": "white",
                "border": "none",
                "borderRadius": "4px",
                "cursor": "pointer" if not pause_coll_btn_disabled else "not-allowed",
                "opacity": "0.6" if pause_coll_btn_disabled else "1.0",
            }

            return (
                multi_fig,
                html.Span(connection_status, style=status_style),
                connection_details,
                buffer_info,
                recording_status_display,
                recording_info_display,
                start_rec_btn_disabled,
                stop_rec_btn_disabled,
                start_rec_btn_style,
                stop_rec_btn_style,
                collection_status_display,
                start_coll_btn_disabled,
                pause_coll_btn_disabled,
                start_coll_btn_style,
                pause_coll_btn_style,
            )

        # Recording control callbacks
        @self.app.callback(  # type: ignore
            Output("recording-state-store", "children"),
            [Input("start-recording-btn", "n_clicks")],
            prevent_initial_call=True,
        )
        def start_recording(n_clicks: int):  # type: ignore
            if n_clicks and not self.recorder.is_recording:
                try:
                    self.recorder.start_recording()
                    logger.info("🎬 Recording started successfully")
                    return "recording"
                except Exception as e:
                    logger.error(f"❌ Failed to start recording: {e}")
                    return "error"
            return "idle"

        @self.app.callback(  # type: ignore
            Output("recording-state-store", "children", allow_duplicate=True),
            [Input("stop-recording-btn", "n_clicks")],
            prevent_initial_call=True,
        )
        def stop_recording(n_clicks: int):  # type: ignore
            if n_clicks and self.recorder.is_recording:
                try:
                    session_info = self.recorder.stop_recording()
                    logger.info(
                        f"🏁 Recording stopped: {session_info.total_samples} samples, "
                        f"{session_info.duration_seconds:.1f}s, "
                        f"{session_info.file_size_bytes} bytes"
                    )
                    return "stopped"
                except Exception as e:
                    logger.error(f"❌ Failed to stop recording: {e}")
                    return "error"
            return "idle"

        # Data collection control callbacks
        @self.app.callback(  # type: ignore
            Output("collection-state-store", "children"),
            [Input("start-collection-btn", "n_clicks")],
            prevent_initial_call=True,
        )
        def start_collection(n_clicks: int):  # type: ignore
            if n_clicks:
                try:
                    if not self._collection_running:
                        # Start new collection
                        self.start_data_collection()
                        self._collection_running = True
                        self._collection_paused = False
                        logger.info("▶️ Data collection started")
                    elif self._collection_paused:
                        # Resume paused collection
                        self._collection_paused = False
                        logger.info("▶️ Data collection resumed")
                    return "running"
                except Exception as e:
                    logger.error(f"❌ Failed to start/resume collection: {e}")
                    return "error"
            return "idle"

        @self.app.callback(  # type: ignore
            Output("collection-state-store", "children", allow_duplicate=True),
            [Input("pause-collection-btn", "n_clicks")],
            prevent_initial_call=True,
        )
        def pause_collection(n_clicks: int):  # type: ignore
            if n_clicks and self._collection_running and not self._collection_paused:
                try:
                    self._collection_paused = True
                    logger.info("⏸️ Data collection paused")
                    return "paused"
                except Exception as e:
                    logger.error(f"❌ Failed to pause collection: {e}")
                    return "error"
            return "idle"

    def _data_collection_worker(self) -> None:
        """Background worker managing robust data collection with comprehensive retry logic.

        This method runs in a dedicated thread with its own asyncio event loop,
        handling all BLE communication asynchronously. The implementation provides
        sophisticated error handling and retry mechanisms designed for the inherent
        instability of BLE connections.

        Key features:
        1. **Exponential backoff retry**: Multiple retry attempts with increasing
           delays prevent overwhelming failed connections.
        2. **Comprehensive error classification**: Different error types get
           specific handling and user guidance.
        3. **Graceful degradation**: Connection failures are logged but don't
           crash the application or UI.
        4. **Resource management**: Proper cleanup of asyncio resources and
           data source connections.
        5. **User feedback**: Regular progress logging helps users understand
           system status during challenging connection scenarios.

        The worker handles the complete BLE lifecycle: device discovery,
        connection establishment, data streaming, error recovery, and cleanup.
        It's designed to run continuously until explicitly stopped by the UI.

        Note:
            This method creates and manages its own asyncio event loop to avoid
            conflicts with Dash's event loop. All BLE operations are async to
            prevent blocking the data stream during I/O operations.
        """

        async def collect_data_with_retry() -> None:
            retry_count = 0
            max_retries = 5  # Increased retries
            retry_delay = 3.0  # Reduced initial delay
            backoff_multiplier = 1.5  # Exponential backoff

            while not self._stop_event.is_set() and retry_count < max_retries:
                try:
                    logger.info(
                        f"🔄 Starting data source (attempt {retry_count + 1}/{max_retries})..."
                    )
                    await self.data_source.start()

                    data_count = 0

                    logger.info("✅ Data source started, beginning data collection...")

                    async for row in self.data_source.get_data_stream():
                        if self._stop_event.is_set():
                            logger.info(
                                "🛑 Stop event received, ending data collection"
                            )
                            break

                        # Check if collection is paused
                        if self._collection_paused:
                            # When paused, sleep briefly and check again
                            await asyncio.sleep(0.1)
                            continue

                        self.buffer.append(row)
                        data_count += 1

                        # Log progress periodically
                        if data_count % 25 == 1:  # Log every 25 samples (~1 second)
                            buffer_stats = self.buffer.stats
                            logger.debug(
                                f"📊 Background: Collected {data_count} samples, "
                                f"buffer: {self.buffer.size}/{self.buffer.max_size}, "
                                f"rate: {buffer_stats.sample_rate:.1f}Hz"
                            )

                    # If we exit the loop normally, we're done
                    if not self._stop_event.is_set():
                        logger.warning("⚠️ Data stream ended unexpectedly")
                    break

                except asyncio.CancelledError:
                    logger.info("🛑 Data collection cancelled")
                    break

                except Exception as e:
                    retry_count += 1
                    logger.error(
                        f"❌ Data collection error (attempt {retry_count}/{max_retries}): {e}"
                    )
                    logger.error(f"❌ Error type: {type(e).__name__}")
                    import traceback

                    logger.error("❌ Full traceback:")
                    traceback.print_exc()

                    if retry_count < max_retries:
                        current_delay = retry_delay * (
                            backoff_multiplier ** (retry_count - 1)
                        )
                        logger.info(
                            f"⏳ Retrying in {current_delay:.1f} seconds... (retry {retry_count}/{max_retries})"
                        )
                        try:
                            await asyncio.sleep(current_delay)
                        except asyncio.CancelledError:
                            break
                    else:
                        logger.error(
                            f"💥 Max retries ({max_retries}) exceeded. Giving up."
                        )
                        logger.info("💡 Troubleshooting tips:")
                        logger.info("   - Check if XIAO device is powered on")
                        logger.info(
                            "   - Verify device is advertising as 'XIAO Sense IMU'"
                        )
                        logger.info("   - Move device closer to reduce interference")
                        logger.info("   - Restart the device and try again")

                finally:
                    try:
                        await self.data_source.stop()
                    except Exception as e:
                        logger.warning(f"⚠️ Error stopping data source: {e}")

            logger.info("🏁 Data collection worker finished")

        # Create new event loop for this thread
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(collect_data_with_retry())
        except Exception as e:
            logger.error(f"💥 Worker fatal error: {e}")
        finally:
            self._loop.close()

    def start_data_collection(self) -> None:
        """Start background data collection thread with proper lifecycle management.

        This method initializes and starts the background worker thread responsible
        for all data collection operations. The implementation ensures only one
        data collection thread runs at a time and properly handles thread lifecycle.

        The background thread is marked as daemon to ensure clean application
        shutdown even if the thread is still running when the main process exits.

        Note:
            This method is idempotent - calling it multiple times won't create
            multiple threads if one is already running. The existing thread
            continues operation.
        """
        if self._data_thread is None or not self._data_thread.is_alive():
            self._stop_event.clear()
            self._data_thread = threading.Thread(
                target=self._data_collection_worker, daemon=True
            )
            self._data_thread.start()

    def stop_data_collection(self) -> None:
        """Stop background data collection with graceful shutdown and cleanup.

        This method coordinates the shutdown of all background data collection
        operations, including thread termination and asyncio event loop cleanup.
        The implementation provides reasonable timeout values to ensure responsive
        shutdown while allowing ongoing operations to complete cleanly.

        Cleanup is comprehensive - both the worker thread and its associated
        asyncio event loop are properly terminated to prevent resource leaks.

        Note:
            If the worker thread doesn't respond to shutdown requests within the
            timeout period, it's left running as a daemon thread that will be
            terminated when the main process exits.
        """
        logger.info("🛑 Stopping data collection...")
        self._stop_event.set()

        if self._data_thread and self._data_thread.is_alive():
            logger.info("⏳ Waiting for data collection thread to stop...")
            self._data_thread.join(timeout=5.0)  # Increased timeout

            if self._data_thread.is_alive():
                logger.warning("⚠️ Data collection thread did not stop gracefully")
            else:
                logger.info("✅ Data collection thread stopped")

        # Close the event loop if it exists
        if self._loop and not self._loop.is_closed():
            try:
                self._loop.close()
                logger.info("✅ Event loop closed")
            except Exception as e:
                logger.warning(f"⚠️ Error closing event loop: {e}")

    def run(
        self, host: str = "127.0.0.1", port: int = 8050, debug: bool = False
    ) -> None:
        """Start the complete oscilloscope application with automatic data collection.

        This method starts both the background data collection system and the
        Dash web server, providing a complete sensor monitoring solution.
        The implementation ensures proper cleanup even if the application is
        interrupted.

        Args:
            host: Network interface to bind the web server. Default "127.0.0.1"
                restricts access to localhost. Use "0.0.0.0" for network access.
            port: TCP port for the web server. Default 8050 is standard for Dash.
                Change if port conflicts occur.
            debug: Enable Dash debug mode with hot reloading and detailed error
                messages. Should be False for production use.

        Note:
            The application runs indefinitely until interrupted (Ctrl+C) or
            terminated. Data collection stops automatically when the web server
            shuts down, ensuring proper resource cleanup.
        """
        self.start_data_collection()
        try:
            self.app.run(host=host, port=port, debug=debug)
        finally:
            self.stop_data_collection()


def create_app(data_source: DataSource, **kwargs: int) -> OscilloscopeApp:
    """Factory function to create an oscilloscope app.

    Args:
        data_source: Required data source (BleDataSource or MockDataSource)
        **kwargs: Additional arguments for OscilloscopeApp

    Returns:
        OscilloscopeApp instance
    """
    return OscilloscopeApp(data_source=data_source, **kwargs)


if __name__ == "__main__":
    # Run with mock data for testing
    from ..ble_receiver import MockDataSource

    app = create_app(MockDataSource())
    app.run(debug=True)
