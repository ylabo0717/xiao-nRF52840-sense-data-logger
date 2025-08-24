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

            # Create multi-sensor plot layout
            multi_fig = create_multi_plot_layout(data)

            # Enhanced connection status
            is_connected = self.buffer.size > 0
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
            max_retries = 3
            retry_delay = 5.0  # seconds

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

                        # Log progress for BLE connections
                        if isinstance(
                            self.data_source, type(self.data_source)
                        ) and hasattr(self.data_source, "_connected"):
                            if data_count % 100 == 1:  # Log every 100 samples
                                print(
                                    f"📊 Collected {data_count} samples, "
                                    f"buffer: {self.buffer.size}/{self.buffer.max_size}"
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

                    if retry_count < max_retries:
                        print(f"⏳ Retrying in {retry_delay} seconds...")
                        try:
                            await asyncio.sleep(retry_delay)
                        except asyncio.CancelledError:
                            break
                    else:
                        print(f"💥 Max retries ({max_retries}) exceeded. Giving up.")

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
        self._stop_event.set()
        if self._data_thread and self._data_thread.is_alive():
            self._data_thread.join(timeout=2.0)

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
