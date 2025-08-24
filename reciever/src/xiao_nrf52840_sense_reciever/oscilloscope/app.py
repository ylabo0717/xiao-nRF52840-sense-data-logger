"""
Dash application for oscilloscope visualization.
"""

import asyncio
import threading
from typing import Optional

import dash  # type: ignore
from dash import dcc, html, Input, Output

from ..ble_receiver import DataBuffer, DataSource, MockDataSource
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
                                "width": "65%",
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
            ],
            [Input("interval-component", "n_intervals")],
        )
        def update_plots(n_intervals: int):  # type: ignore
            # Get recent data
            data = self.buffer.get_recent(500)  # Show last 500 points
            stats = self.buffer.stats

            # Debug logging - much more frequent for troubleshooting
            if n_intervals % 5 == 0:  # Log every 5 updates (~0.3 seconds at 15fps)
                print(
                    f"🔍 UI Debug: n_intervals={n_intervals}, Buffer size={self.buffer.size}, Recent data={len(data)}, Sample rate={stats.sample_rate:.1f}Hz"
                )
                if len(data) > 0:
                    print(
                        f"🔍 UI Sample data: ax={data[-1].ax:.2f}, temp={data[-1].tempC:.1f}°C"
                    )
                else:
                    print("🔍 UI: NO DATA AVAILABLE")

            # Create multi-sensor plot layout
            multi_fig = create_multi_plot_layout(data)

            # Enhanced connection status
            is_connected = self.buffer.size > 0

            # Debug: Log connection status periodically
            if n_intervals % 60 == 0:  # Every ~4 seconds
                print(
                    f"🔍 UI Debug: is_connected={is_connected}, buffer_size={self.buffer.size}, "
                    f"stats.fill_level={stats.fill_level}, stats.sample_rate={stats.sample_rate:.1f}"
                )

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
            else:
                connection_status = "🔴 Disconnected"
                status_color = "red"

            status_style = {
                "color": status_color,
                "fontWeight": "bold",
                "fontSize": "16px",
            }

            # Detailed connection information
            data_source_type = type(self.data_source).__name__
            if data_source_type == "BleDataSource":
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
            buffer_info = html.Div(
                [
                    html.P(
                        f"Buffer Fill: {stats.fill_level}/{self.buffer.max_size} "
                        f"({stats.fill_level / self.buffer.max_size * 100:.1f}%)",
                        style={"margin": "5px 0"},
                    ),
                    html.P(
                        f"Displaying: {len(data)} data points "
                        f"({len(data) / 25:.1f}s @ 25Hz)",
                        style={"margin": "5px 0"},
                    ),
                    html.P(
                        f"Buffer Duration: {self.buffer.max_size / 25:.1f}s "
                        f"({self.buffer.max_size / 25 / 60:.1f}min)",
                        style={"margin": "5px 0"},
                    ),
                ]
            )

            return (
                multi_fig,
                html.Span(connection_status, style=status_style),
                connection_details,
                buffer_info,
            )

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

                        self.buffer.append(row)
                        data_count += 1

                        # Log progress more frequently for debugging
                        if data_count % 5 == 1:  # Log every 5 samples (~0.2 second)
                            print(
                                f"📊 Background: Collected {data_count} samples, "
                                f"buffer: {self.buffer.size}/{self.buffer.max_size} "
                                f"Last data: ax={row.ax:.2f}, ay={row.ay:.2f}, temp={row.tempC:.1f}°C"
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


def create_app(
    data_source: Optional[DataSource] = None, **kwargs: int
) -> OscilloscopeApp:
    """Factory function to create an oscilloscope app."""
    if data_source is None:
        data_source = MockDataSource()

    return OscilloscopeApp(data_source=data_source, **kwargs)


if __name__ == "__main__":
    # Run with mock data for testing
    app = create_app()
    app.run(debug=True)
