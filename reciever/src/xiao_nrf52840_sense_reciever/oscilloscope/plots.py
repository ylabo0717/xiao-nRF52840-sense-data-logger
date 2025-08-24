"""
Plot components and layouts for oscilloscope visualization.
"""

from typing import List

import plotly.graph_objects as go  # type: ignore
from plotly.subplots import make_subplots  # type: ignore

from ..ble_receiver import ImuRow


def create_accelerometer_plot(
    data: List[ImuRow], title: str = "Accelerometer Data"
) -> go.Figure:
    """Create accelerometer plot with 3 axes."""
    fig = go.Figure()

    if not data:
        fig.add_annotation(
            x=0.5,
            y=0.5,
            text="No data available",
            showarrow=False,
            xref="paper",
            yref="paper",
            font=dict(size=16, color="gray"),
        )
        fig.update_layout(
            title=title,
            xaxis_title="Time (seconds)",
            yaxis_title="Acceleration (g)",
            height=300,
        )
        return fig

    # Calculate relative timestamps
    timestamps = [(row.millis - data[0].millis) / 1000.0 for row in data]
    ax_data = [row.ax for row in data]
    ay_data = [row.ay for row in data]
    az_data = [row.az for row in data]

    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=ax_data,
            mode="lines",
            name="X-axis",
            line=dict(color="red", width=1.5),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=ay_data,
            mode="lines",
            name="Y-axis",
            line=dict(color="green", width=1.5),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=az_data,
            mode="lines",
            name="Z-axis",
            line=dict(color="blue", width=1.5),
        )
    )

    fig.update_layout(
        title=title,
        xaxis_title="Time (seconds)",
        yaxis_title="Acceleration (g)",
        showlegend=True,
        height=300,
        margin=dict(l=50, r=20, t=50, b=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    # Set axis ranges
    if timestamps:
        fig.update_xaxes(range=[timestamps[0], timestamps[-1]])
    fig.update_yaxes(range=[-2, 2])  # Typical accelerometer range

    return fig


def create_gyroscope_plot(
    data: List[ImuRow], title: str = "Gyroscope Data"
) -> go.Figure:
    """Create gyroscope plot with 3 axes."""
    fig = go.Figure()

    if not data:
        fig.add_annotation(
            x=0.5,
            y=0.5,
            text="No data available",
            showarrow=False,
            xref="paper",
            yref="paper",
            font=dict(size=16, color="gray"),
        )
        fig.update_layout(
            title=title,
            xaxis_title="Time (seconds)",
            yaxis_title="Angular Velocity (°/s)",
            height=300,
        )
        return fig

    # Calculate relative timestamps
    timestamps = [(row.millis - data[0].millis) / 1000.0 for row in data]
    gx_data = [row.gx for row in data]
    gy_data = [row.gy for row in data]
    gz_data = [row.gz for row in data]

    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=gx_data,
            mode="lines",
            name="X-rotation",
            line=dict(color="darkred", width=1.5),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=gy_data,
            mode="lines",
            name="Y-rotation",
            line=dict(color="darkgreen", width=1.5),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=gz_data,
            mode="lines",
            name="Z-rotation",
            line=dict(color="darkblue", width=1.5),
        )
    )

    fig.update_layout(
        title=title,
        xaxis_title="Time (seconds)",
        yaxis_title="Angular Velocity (°/s)",
        showlegend=True,
        height=300,
        margin=dict(l=50, r=20, t=50, b=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    # Set axis ranges
    if timestamps:
        fig.update_xaxes(range=[timestamps[0], timestamps[-1]])
    fig.update_yaxes(range=[-50, 50])  # Typical gyroscope range

    return fig


def create_temperature_plot(
    data: List[ImuRow], title: str = "Temperature"
) -> go.Figure:
    """Create temperature plot."""
    fig = go.Figure()

    if not data:
        fig.add_annotation(
            x=0.5,
            y=0.5,
            text="No data available",
            showarrow=False,
            xref="paper",
            yref="paper",
            font=dict(size=16, color="gray"),
        )
        fig.update_layout(
            title=title,
            xaxis_title="Time (seconds)",
            yaxis_title="Temperature (°C)",
            height=300,
        )
        return fig

    # Calculate relative timestamps
    timestamps = [(row.millis - data[0].millis) / 1000.0 for row in data]
    temp_data = [row.tempC for row in data]

    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=temp_data,
            mode="lines",
            name="Temperature",
            line=dict(color="orange", width=2),
        )
    )

    fig.update_layout(
        title=title,
        xaxis_title="Time (seconds)",
        yaxis_title="Temperature (°C)",
        showlegend=False,
        height=300,
        margin=dict(l=50, r=20, t=50, b=50),
    )

    # Set axis ranges
    if timestamps:
        fig.update_xaxes(range=[timestamps[0], timestamps[-1]])

    # Auto-scale temperature with some padding
    if temp_data:
        temp_min, temp_max = min(temp_data), max(temp_data)
        temp_range = temp_max - temp_min
        padding = max(1.0, temp_range * 0.1)  # At least 1°C padding
        fig.update_yaxes(range=[temp_min - padding, temp_max + padding])

    return fig


def create_audio_plot(data: List[ImuRow], title: str = "Audio RMS") -> go.Figure:
    """Create audio RMS plot with missing value handling."""
    fig = go.Figure()

    if not data:
        fig.add_annotation(
            x=0.5,
            y=0.5,
            text="No data available",
            showarrow=False,
            xref="paper",
            yref="paper",
            font=dict(size=16, color="gray"),
        )
        fig.update_layout(
            title=title,
            xaxis_title="Time (seconds)",
            yaxis_title="RMS Level",
            height=300,
        )
        return fig

    # Calculate relative timestamps and filter out missing values (-1.0)
    timestamps = []
    audio_data = []

    for row in data:
        timestamp = (row.millis - data[0].millis) / 1000.0
        if row.audioRMS >= 0:  # Filter out missing values (-1.0)
            timestamps.append(timestamp)
            audio_data.append(row.audioRMS)

    if not audio_data:
        fig.add_annotation(
            x=0.5,
            y=0.5,
            text="No audio data available",
            showarrow=False,
            xref="paper",
            yref="paper",
            font=dict(size=16, color="gray"),
        )
    else:
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=audio_data,
                mode="lines",
                name="Audio RMS",
                line=dict(color="purple", width=2),
                connectgaps=False,  # Don't connect across missing values
            )
        )

    fig.update_layout(
        title=title,
        xaxis_title="Time (seconds)",
        yaxis_title="RMS Level",
        showlegend=False,
        height=300,
        margin=dict(l=50, r=20, t=50, b=50),
    )

    # Set axis ranges
    if data:
        all_timestamps = [(row.millis - data[0].millis) / 1000.0 for row in data]
        fig.update_xaxes(range=[all_timestamps[0], all_timestamps[-1]])

    # Auto-scale audio with some padding, or use default range
    if audio_data:
        audio_min, audio_max = min(audio_data), max(audio_data)
        audio_range = audio_max - audio_min
        padding = max(50.0, audio_range * 0.1)  # At least 50 units padding
        fig.update_yaxes(range=[max(0, audio_min - padding), audio_max + padding])
    else:
        fig.update_yaxes(range=[0, 2000])  # Default range when no data

    return fig


def create_multi_plot_layout(data: List[ImuRow]) -> go.Figure:
    """Create a 2x2 subplot layout with all sensor data."""
    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            "Accelerometer Data (g)",
            "Gyroscope Data (°/s)",
            "Temperature (°C)",
            "Audio RMS Level",
        ),
        specs=[
            [{"secondary_y": False}, {"secondary_y": False}],
            [{"secondary_y": False}, {"secondary_y": False}],
        ],
        vertical_spacing=0.15,
        horizontal_spacing=0.10,
    )

    if not data:
        # Add "No data" annotations to all subplots
        for row in [1, 2]:
            for col in [1, 2]:
                fig.add_annotation(
                    x=0.5,
                    y=0.5,
                    text="No data available",
                    showarrow=False,
                    xref="paper",
                    yref="paper",
                    font=dict(size=14, color="gray"),
                    row=row,
                    col=col,
                )

        fig.update_layout(height=600, showlegend=False)
        return fig

    # Calculate relative timestamps
    timestamps = [(row.millis - data[0].millis) / 1000.0 for row in data]

    # Accelerometer data (top-left)
    ax_data = [row.ax for row in data]
    ay_data = [row.ay for row in data]
    az_data = [row.az for row in data]

    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=ax_data,
            mode="lines",
            name="X-axis",
            line=dict(color="red", width=1.5),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=ay_data,
            mode="lines",
            name="Y-axis",
            line=dict(color="green", width=1.5),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=az_data,
            mode="lines",
            name="Z-axis",
            line=dict(color="blue", width=1.5),
        ),
        row=1,
        col=1,
    )

    # Gyroscope data (top-right)
    gx_data = [row.gx for row in data]
    gy_data = [row.gy for row in data]
    gz_data = [row.gz for row in data]

    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=gx_data,
            mode="lines",
            name="X-rotation",
            line=dict(color="darkred", width=1.5),
            showlegend=False,
        ),
        row=1,
        col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=gy_data,
            mode="lines",
            name="Y-rotation",
            line=dict(color="darkgreen", width=1.5),
            showlegend=False,
        ),
        row=1,
        col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=gz_data,
            mode="lines",
            name="Z-rotation",
            line=dict(color="darkblue", width=1.5),
            showlegend=False,
        ),
        row=1,
        col=2,
    )

    # Temperature data (bottom-left)
    temp_data = [row.tempC for row in data]
    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=temp_data,
            mode="lines",
            name="Temperature",
            line=dict(color="orange", width=2),
            showlegend=False,
        ),
        row=2,
        col=1,
    )

    # Audio data (bottom-right) - filter out missing values
    audio_timestamps: List[float] = []
    audio_data: List[float] = []
    for idx, imu_row in enumerate(data):
        if imu_row.audioRMS >= 0:  # Filter out missing values (-1.0)
            audio_timestamps.append(timestamps[idx])
            audio_data.append(imu_row.audioRMS)

    if audio_data:
        fig.add_trace(
            go.Scatter(
                x=audio_timestamps,
                y=audio_data,
                mode="lines",
                name="Audio RMS",
                line=dict(color="purple", width=2),
                connectgaps=False,
                showlegend=False,
            ),
            row=2,
            col=2,
        )

    # Update axis ranges and labels
    fig.update_xaxes(range=[timestamps[0], timestamps[-1]], title_text="Time (seconds)")

    # Set specific Y-axis ranges for each subplot
    fig.update_yaxes(range=[-2, 2], title_text="Acceleration (g)", row=1, col=1)
    fig.update_yaxes(range=[-50, 50], title_text="Angular Velocity (°/s)", row=1, col=2)

    # Auto-scale temperature
    if temp_data:
        temp_min, temp_max = min(temp_data), max(temp_data)
        temp_range = temp_max - temp_min
        padding = max(1.0, temp_range * 0.1)
        fig.update_yaxes(
            range=[temp_min - padding, temp_max + padding],
            title_text="Temperature (°C)",
            row=2,
            col=1,
        )

    # Auto-scale audio
    if audio_data:
        audio_min, audio_max = min(audio_data), max(audio_data)
        audio_range = audio_max - audio_min
        padding = max(50.0, audio_range * 0.1)
        fig.update_yaxes(
            range=[max(0, audio_min - padding), audio_max + padding],
            title_text="RMS Level",
            row=2,
            col=2,
        )
    else:
        fig.update_yaxes(range=[0, 2000], title_text="RMS Level", row=2, col=2)

    # Update layout
    fig.update_layout(
        height=600,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=50, t=80, b=50),
    )

    return fig
