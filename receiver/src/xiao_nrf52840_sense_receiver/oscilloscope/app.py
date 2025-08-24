"""
Dash application for oscilloscope visualization.
"""

import asyncio
import threading
from typing import Any, List, Optional, Tuple

import dash  # type: ignore
from dash import dcc, html, Input, Output

from ..ble_receiver import DataBuffer, DataSource
from .plots import create_multi_plot_layout


class OscilloscopeApp:
    """Main Dash application for oscilloscope visualization."""

    def __init__(
        self, data_source: DataSource, buffer_size: int = 1000, update_rate: int = 15
    ):
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
        """Setup the Dash application layout."""
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
                                            value=20,  # Default to 20 seconds (500 samples / 25Hz)
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
        """Setup Dash callbacks."""

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
            ],
        )
        def update_plots(
            n_intervals: int,
            time_window: int,
            visible_plots: List[str],
            auto_scale_list: List[str],
        ) -> Tuple[Any, ...]:
            # Provide default values for optional inputs
            if time_window is None:
                time_window = 20
            if visible_plots is None:
                visible_plots = ["accel", "gyro", "temp", "audio"]
            if auto_scale_list is None:
                auto_scale_list = []

            # Get recent data based on time window
            if time_window and time_window > 0:
                sample_rate = 25  # Hz, approximate
                max_samples = int(time_window * sample_rate)
                data = self.buffer.get_recent(max_samples)
            else:
                data = self.buffer.get_recent(500)  # Default

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
                print(
                    f"🔍 UI Debug: Buffer size={self.buffer.size}, Sample rate={stats.sample_rate:.1f}Hz, Status: {connection_status}"
                )

            # Create multi-sensor plot layout with new parameters
            multi_fig = create_multi_plot_layout(
                data,
                time_window_seconds=time_window,
                visible_plots=visible_plots,
                auto_scale=auto_scale,
            )

            # Debug: Log connection status periodically
            if n_intervals % 60 == 0:  # Every ~4 seconds
                print(
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
            display_time = len(data) / 25.0 if data else 0
            buffer_info = html.Div(
                [
                    html.P(
                        f"Buffer Fill: {stats.fill_level}/{self.buffer.max_size} "
                        f"({stats.fill_level / self.buffer.max_size * 100:.1f}%)",
                        style={"margin": "5px 0"},
                    ),
                    html.P(
                        f"Displaying: {len(data)} data points "
                        f"({display_time:.1f}s @ 25Hz)",
                        style={"margin": "5px 0"},
                    ),
                    html.P(
                        f"Time Window: {time_window}s",
                        style={"margin": "5px 0"},
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
                    print("🎬 Recording started successfully")
                    return "recording"
                except Exception as e:
                    print(f"❌ Failed to start recording: {e}")
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
                    print(
                        f"🏁 Recording stopped: {session_info.total_samples} samples, "
                        f"{session_info.duration_seconds:.1f}s, "
                        f"{session_info.file_size_bytes} bytes"
                    )
                    return "stopped"
                except Exception as e:
                    print(f"❌ Failed to stop recording: {e}")
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
                        print("▶️ Data collection started")
                    elif self._collection_paused:
                        # Resume paused collection
                        self._collection_paused = False
                        print("▶️ Data collection resumed")
                    return "running"
                except Exception as e:
                    print(f"❌ Failed to start/resume collection: {e}")
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
                    print("⏸️ Data collection paused")
                    return "paused"
                except Exception as e:
                    print(f"❌ Failed to pause collection: {e}")
                    return "error"
            return "idle"

    def _data_collection_worker(self) -> None:
        """Background worker to collect data from the data source with retry logic."""

        async def collect_data_with_retry() -> None:
            retry_count = 0
            max_retries = 5  # Increased retries
            retry_delay = 3.0  # Reduced initial delay
            backoff_multiplier = 1.5  # Exponential backoff

            while not self._stop_event.is_set() and retry_count < max_retries:
                try:
                    print(
                        f"🔄 Starting data source (attempt {retry_count + 1}/{max_retries})..."
                    )
                    await self.data_source.start()

                    data_count = 0

                    print("✅ Data source started, beginning data collection...")

                    async for row in self.data_source.get_data_stream():
                        if self._stop_event.is_set():
                            print("🛑 Stop event received, ending data collection")
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
                            print(
                                f"📊 Background: Collected {data_count} samples, "
                                f"buffer: {self.buffer.size}/{self.buffer.max_size}, "
                                f"rate: {buffer_stats.sample_rate:.1f}Hz"
                            )

                    # If we exit the loop normally, we're done
                    if not self._stop_event.is_set():
                        print("⚠️ Data stream ended unexpectedly")
                    break

                except asyncio.CancelledError:
                    print("🛑 Data collection cancelled")
                    break

                except Exception as e:
                    retry_count += 1
                    print(
                        f"❌ Data collection error (attempt {retry_count}/{max_retries}): {e}"
                    )
                    print(f"❌ Error type: {type(e).__name__}")
                    import traceback

                    print("❌ Full traceback:")
                    traceback.print_exc()

                    if retry_count < max_retries:
                        current_delay = retry_delay * (
                            backoff_multiplier ** (retry_count - 1)
                        )
                        print(
                            f"⏳ Retrying in {current_delay:.1f} seconds... (retry {retry_count}/{max_retries})"
                        )
                        try:
                            await asyncio.sleep(current_delay)
                        except asyncio.CancelledError:
                            break
                    else:
                        print(f"💥 Max retries ({max_retries}) exceeded. Giving up.")
                        print("💡 Troubleshooting tips:")
                        print("   - Check if XIAO device is powered on")
                        print("   - Verify device is advertising as 'XIAO Sense IMU'")
                        print("   - Move device closer to reduce interference")
                        print("   - Restart the device and try again")

                finally:
                    try:
                        await self.data_source.stop()
                    except Exception as e:
                        print(f"⚠️ Error stopping data source: {e}")

            print("🏁 Data collection worker finished")

        # Create new event loop for this thread
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(collect_data_with_retry())
        except Exception as e:
            print(f"💥 Worker fatal error: {e}")
        finally:
            self._loop.close()

    def start_data_collection(self) -> None:
        """Start background data collection."""
        if self._data_thread is None or not self._data_thread.is_alive():
            self._stop_event.clear()
            self._data_thread = threading.Thread(
                target=self._data_collection_worker, daemon=True
            )
            self._data_thread.start()

    def stop_data_collection(self) -> None:
        """Stop background data collection."""
        print("🛑 Stopping data collection...")
        self._stop_event.set()

        if self._data_thread and self._data_thread.is_alive():
            print("⏳ Waiting for data collection thread to stop...")
            self._data_thread.join(timeout=5.0)  # Increased timeout

            if self._data_thread.is_alive():
                print("⚠️ Data collection thread did not stop gracefully")
            else:
                print("✅ Data collection thread stopped")

        # Close the event loop if it exists
        if self._loop and not self._loop.is_closed():
            try:
                self._loop.close()
                print("✅ Event loop closed")
            except Exception as e:
                print(f"⚠️ Error closing event loop: {e}")

    def run(
        self, host: str = "127.0.0.1", port: int = 8050, debug: bool = False
    ) -> None:
        """Run the Dash application."""
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
