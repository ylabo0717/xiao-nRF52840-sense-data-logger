"""
Dash application for oscilloscope visualization.
"""

import asyncio
import threading
from typing import Optional

import dash  # type: ignore
from dash import dcc, html, Input, Output
import plotly.graph_objects as go  # type: ignore

from ..ble_receiver import DataBuffer, DataSource, MockDataSource


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
                                    id="connection-status", children="Disconnected"
                                ),
                            ],
                            style={"width": "30%", "display": "inline-block"},
                        ),
                        html.Div(
                            [
                                html.H3("Buffer Statistics"),
                                html.Div(id="buffer-stats", children="No data"),
                            ],
                            style={"width": "70%", "display": "inline-block"},
                        ),
                    ],
                    style={"margin": "20px"},
                ),
                # Accelerometer plot
                html.Div(
                    [
                        html.H3(
                            "Accelerometer Data (g)", style={"textAlign": "center"}
                        ),
                        dcc.Graph(id="accel-plot", config={"displayModeBar": True}),
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
                Output("accel-plot", "figure"),
                Output("connection-status", "children"),
                Output("buffer-stats", "children"),
            ],
            [Input("interval-component", "n_intervals")],
        )
        def update_plots(n_intervals: int):  # type: ignore
            # Get recent data
            data = self.buffer.get_recent(500)  # Show last 500 points
            stats = self.buffer.stats

            # Create accelerometer plot
            accel_fig = go.Figure()

            if data:
                # Convert to pandas for easier handling
                timestamps = [
                    (row.millis - data[0].millis) / 1000.0 for row in data
                ]  # Relative time in seconds
                ax_data = [row.ax for row in data]
                ay_data = [row.ay for row in data]
                az_data = [row.az for row in data]

                accel_fig.add_trace(
                    go.Scatter(
                        x=timestamps,
                        y=ax_data,
                        mode="lines",
                        name="X-axis",
                        line=dict(color="red", width=2),
                    )
                )

                accel_fig.add_trace(
                    go.Scatter(
                        x=timestamps,
                        y=ay_data,
                        mode="lines",
                        name="Y-axis",
                        line=dict(color="green", width=2),
                    )
                )

                accel_fig.add_trace(
                    go.Scatter(
                        x=timestamps,
                        y=az_data,
                        mode="lines",
                        name="Z-axis",
                        line=dict(color="blue", width=2),
                    )
                )

                accel_fig.update_layout(
                    title="Accelerometer Data",
                    xaxis_title="Time (seconds)",
                    yaxis_title="Acceleration (g)",
                    showlegend=True,
                    height=400,
                    margin=dict(l=50, r=50, t=50, b=50),
                )

                # Set axis ranges for better visualization
                accel_fig.update_xaxes(
                    range=[
                        timestamps[0] if timestamps else 0,
                        timestamps[-1] if timestamps else 10,
                    ]
                )
                accel_fig.update_yaxes(range=[-2, 2])  # Typical accelerometer range

            else:
                accel_fig.add_annotation(
                    x=0.5,
                    y=0.5,
                    text="No data available",
                    showarrow=False,
                    xref="paper",
                    yref="paper",
                    font=dict(size=20, color="gray"),
                )
                accel_fig.update_layout(
                    title="Accelerometer Data",
                    xaxis_title="Time (seconds)",
                    yaxis_title="Acceleration (g)",
                    height=400,
                )

            # Connection status
            connection_status = "Connected" if self.buffer.size > 0 else "Disconnected"
            status_style = {"color": "green" if self.buffer.size > 0 else "red"}

            # Buffer statistics
            buffer_info = html.Div(
                [
                    html.P(f"Buffer Size: {stats.fill_level}/1000"),
                    html.P(f"Sample Rate: {stats.sample_rate:.1f} Hz"),
                    html.P(f"Data Points: {len(data)}"),
                ]
            )

            return (
                accel_fig,
                html.Span(connection_status, style=status_style),
                buffer_info,
            )

    def _data_collection_worker(self) -> None:
        """Background worker to collect data from the data source."""

        async def collect_data() -> None:
            try:
                await self.data_source.start()
                async for row in self.data_source.get_data_stream():
                    if self._stop_event.is_set():
                        break
                    self.buffer.append(row)
            except Exception as e:
                print(f"Data collection error: {e}")
            finally:
                await self.data_source.stop()

        # Create new event loop for this thread
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(collect_data())
        except Exception as e:
            print(f"Worker error: {e}")
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
