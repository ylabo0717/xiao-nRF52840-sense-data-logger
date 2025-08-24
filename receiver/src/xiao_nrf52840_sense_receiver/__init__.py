from __future__ import annotations

import argparse
import logging
import sys

from .ble_receiver import run

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="xiao-nrf52840-sense-receiver",
        description="Receive CSV telemetry from XIAO nRF52840 Sense via BLE (NUS) and display as oscilloscope or output CSV to stdout.",
    )
    parser.add_argument(
        "--address",
        help="BLE address of the device to connect to (auto-detect if not specified)",
    )
    parser.add_argument(
        "--device-name",
        default="XIAO Sense IMU",
        help="Device name to search for preferentially during scan",
    )
    parser.add_argument(
        "--scan-timeout",
        type=float,
        default=10.0,
        help="Scan timeout in seconds",
    )
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=None,
        help="Exit with error if no data received for specified seconds (unlimited if not specified)",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=[
            "CRITICAL",
            "ERROR",
            "WARNING",
            "INFO",
            "DEBUG",
            "NOTSET",
        ],
        help="Log level (default: WARNING)",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Also output logs to file (default: stderr only)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8050,
        help="Oscilloscope server port (default: 8050)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock data for testing (no BLE device required)",
    )

    # CSV output mode options (default is oscilloscope)
    parser.add_argument(
        "--csv",
        action="store_true",
        help="CSV output mode (stream CSV to stdout)",
    )
    parser.add_argument(
        "--no-header",
        action="store_true",
        help="Do not output header row at the beginning (only valid in CSV output mode)",
    )
    parser.add_argument(
        "--drop-missing-audio",
        action="store_true",
        help="Exclude rows with audioRMS=-1.0 (only valid in CSV output mode)",
    )

    args = parser.parse_args()

    # Initialize logging (CSV output to stdout, logs to stderr/file)
    level = getattr(logging, str(args.log_level).upper(), logging.WARNING)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if args.log_file:
        try:
            file_handler = logging.FileHandler(args.log_file, encoding="utf-8")
            handlers.append(file_handler)
        except Exception:
            # Continue execution even if file handler fails (output only to stderr)
            pass
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,  # Force to avoid being affected by other basicConfig
    )

    if args.csv:
        # CSV output mode
        code = run(
            address=args.address,
            show_header=not args.no_header,
            drop_missing_audio=args.drop_missing_audio,
            device_name=args.device_name,
            scan_timeout=args.scan_timeout,
            idle_timeout=args.idle_timeout,
        )
        raise SystemExit(code)
    else:
        # Default: oscilloscope mode
        from .oscilloscope import create_app
        from .ble_receiver import BleDataSource, MockDataSource

        logger.info("🔧 XIAO nRF52840 Sense - Oscilloscope")
        logger.info("=" * 50)
        logger.info("🌐 Starting web interface...")
        logger.info("📊 BLE connection will take 10-15 seconds to establish")
        logger.info("⏱️ Please be patient while connecting to device...")
        logger.info(f"🔍 Open http://localhost:{args.port} in your browser")
        logger.info("=" * 50)

        # Select data source
        from .ble_receiver import DataSource

        data_source: DataSource
        if args.mock:
            logger.info("🔧 Using mock data for testing (no BLE device required)")
            data_source = MockDataSource()
        else:
            # Attempt BLE connection, exit with clear error on failure
            if args.address:
                logger.info(f"🔍 Connecting to specific BLE address: {args.address}")
            else:
                logger.info("🔍 Attempting to connect to BLE device...")
                logger.info("💡 Make sure XIAO Sense IMU is powered on and advertising")

            try:
                data_source = BleDataSource(
                    scan_timeout=args.scan_timeout, idle_timeout=args.idle_timeout
                )
            except Exception as e:
                logger.error(f"❌ Failed to connect to BLE device: {e}")
                logger.info("💡 Troubleshooting tips:")
                logger.info("   - Check if XIAO device is powered on")
                logger.info("   - Verify device is advertising as 'XIAO Sense IMU'")
                logger.info("   - Move device closer to reduce interference")
                logger.info("   - Check Bluetooth is enabled on this computer")
                logger.info("   - Try restarting the device and try again")
                logger.info("   - Use --mock option for testing without device")
                raise SystemExit(1)

        # Create and start application
        try:
            app = create_app(data_source=data_source)
            app.start_data_collection()

            try:
                app.app.run(debug=False, host="0.0.0.0", port=args.port)
            except KeyboardInterrupt:
                logger.info("\n🛑 Shutting down oscilloscope...")
            finally:
                logger.info("🛑 Stopping data collection...")
                app.stop_data_collection()
                logger.info("🏁 Oscilloscope stopped")

        except Exception as e:
            logger.error(f"❌ Failed to start oscilloscope: {e}")
            raise SystemExit(1)
