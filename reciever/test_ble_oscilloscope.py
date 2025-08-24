#!/usr/bin/env python3
"""
Test script for BLE oscilloscope with real XIAO nRF52840 Sense device.
"""

import sys
import os
import asyncio
import signal
import atexit

# Add the receiver module to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

try:
    from xiao_nrf52840_sense_reciever.ble_receiver import BleDataSource
    from xiao_nrf52840_sense_reciever.oscilloscope import create_app
    from typing import Optional

    # Global variables for cleanup
    _ble_source: Optional[BleDataSource] = None
    _app_instance = None

    print("✓ Successfully imported BLE oscilloscope modules")

    def cleanup_resources() -> None:
        """Clean up resources on exit."""
        global _ble_source, _app_instance
        print("\n🧹 Cleaning up resources...")

        try:
            if _app_instance:
                _app_instance.stop_data_collection()
                print("✅ Stopped data collection")
        except Exception as e:
            print(f"⚠️ Error stopping data collection: {e}")

        try:
            if _ble_source:
                # Note: Cannot use asyncio in cleanup, but BLE should auto-disconnect
                print("🔌 BLE resources marked for cleanup")
        except Exception as e:
            print(f"⚠️ Error cleaning BLE: {e}")

        print("🏁 Cleanup complete")

    def signal_handler(signum: int, frame: object) -> None:
        """Handle SIGINT/SIGTERM signals."""
        print(f"\n🛑 Received signal {signum}, shutting down...")
        cleanup_resources()
        sys.exit(0)

    # Register cleanup handlers
    atexit.register(cleanup_resources)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    async def test_ble_connection() -> bool:
        """Test BLE connection before starting the app."""
        print("\n🔍 Testing BLE connection to XIAO device...")

        # Use the same enhanced stability settings for testing
        ble_source = BleDataSource(scan_timeout=20.0, idle_timeout=30.0)

        try:
            print("🔄 Starting BLE data source with enhanced stability settings...")
            print("⚙️ Scan timeout: 20s, Test timeout: 30s")
            await ble_source.start()

            if await ble_source.is_connected():
                print("✅ BLE connection successful!")

                # Test receiving a few data points
                print("📊 Testing data reception...")
                data_count = 0
                async for row in ble_source.get_data_stream():
                    data_count += 1
                    print(
                        f"📈 Received data point {data_count}: "
                        f"ax={row.ax:.2f}, ay={row.ay:.2f}, az={row.az:.2f}, "
                        f"temp={row.tempC:.1f}°C"
                    )

                    if data_count >= 5:  # Test with 5 data points
                        print("✅ Data reception test successful!")
                        break

            else:
                print("❌ BLE connection failed")
                return False

        except Exception as e:
            print(f"❌ BLE test failed: {e}")
            return False
        finally:
            await ble_source.stop()

        return True

    def run_ble_oscilloscope() -> None:
        """Run oscilloscope with real BLE data source."""
        print("\n🚀 Starting BLE oscilloscope...")
        print("📱 Make sure your XIAO nRF52840 Sense device is:")
        print("   - Powered on and running the sensor firmware")
        print("   - Within Bluetooth range")
        print("   - Advertising as 'XIAO Sense IMU'")
        print()

        # Create BLE data source with enhanced stability settings
        ble_source = BleDataSource(scan_timeout=20.0, idle_timeout=60.0)

        # Create oscilloscope app with BLE source (reduced update rate for stability)
        app = create_app(data_source=ble_source, buffer_size=2000, update_rate=15)

        print("🌐 Starting web interface...")
        print("📊 Open your browser to http://127.0.0.1:8052")
        print("⚡ Data update rate: 15 FPS (reduced for stability)")
        print("💾 Buffer size: 2000 samples (~80 seconds at 25Hz)")
        print("⚙️ Enhanced stability settings: 20s scan timeout, 60s idle timeout")
        print()
        print("🔍 Debug mode enabled - watch terminal for data flow logs")
        print("💡 If browser shows no data:")
        print("   - Check terminal for '📊 Collected X samples' messages")
        print("   - Look for '🔍 UI Debug' and '🔍 Debug' messages")
        print("   - Verify buffer size is increasing")
        print()
        print("🛑 Press Ctrl+C to stop")
        print("=" * 50)

        try:
            # Use different port to avoid conflicts with mock version
            app.run(host="127.0.0.1", port=8052, debug=False)
        except KeyboardInterrupt:
            print("\n✅ BLE oscilloscope stopped by user")
        except Exception as e:
            print(f"❌ Error running BLE oscilloscope: {e}")
            sys.exit(1)

    def run_ble_oscilloscope_with_source(ble_source: Optional[BleDataSource]) -> None:
        """Run oscilloscope with existing or new BLE data source."""
        global _ble_source, _app_instance

        print("\n🚀 Starting BLE oscilloscope...")

        if ble_source is None:
            print("📱 Make sure your XIAO nRF52840 Sense device is:")
            print("   - Powered on and running the sensor firmware")
            print("   - Within Bluetooth range")
            print("   - Advertising as 'XIAO Sense IMU'")
            print()
            # Create BLE data source with enhanced stability settings
            ble_source = BleDataSource(scan_timeout=20.0, idle_timeout=60.0)
        else:
            print("🔄 Using existing BLE connection from test...")

        # Store references for cleanup
        _ble_source = ble_source

        # Create oscilloscope app with BLE source (reduced update rate for stability)
        app = create_app(data_source=ble_source, buffer_size=2000, update_rate=15)
        _app_instance = app

        print("🌐 Starting web interface...")
        print("📊 Open your browser to http://127.0.0.1:8052")
        print("⚡ Data update rate: 15 FPS (reduced for stability)")
        print("💾 Buffer size: 2000 samples (~80 seconds at 25Hz)")
        print("⚙️ Enhanced stability settings: 20s scan timeout, 60s idle timeout")
        print()
        print("🔍 Debug mode enabled - watch terminal for data flow logs")
        print("💡 If browser shows no data:")
        print("   - Check terminal for '📊 Collected X samples' messages")
        print("   - Look for '🔍 UI Debug' and '🔍 Debug' messages")
        print("   - Verify buffer size is increasing")
        print()
        print("🛑 Press Ctrl+C to stop")
        print("=" * 50)

        try:
            # Use different port to avoid conflicts with mock version
            app.run(host="127.0.0.1", port=8052, debug=False)
        except KeyboardInterrupt:
            print("\n✅ BLE oscilloscope stopped by user")
        except Exception as e:
            print(f"❌ Error running BLE oscilloscope: {e}")
            sys.exit(1)

    async def main() -> None:
        """Main entry point with connection test option."""
        print("XIAO nRF52840 Sense BLE Oscilloscope Test")
        print("=" * 40)

        # Ask user if they want to test connection first
        ble_source = None
        try:
            test_first = (
                input("\n🤔 Test BLE connection before starting oscilloscope? (y/N): ")
                .strip()
                .lower()
            )

            if test_first in ["y", "yes"]:
                # Test connection and keep the same BLE source instance
                print("\n🔍 Testing BLE connection to XIAO device...")
                ble_source = BleDataSource(scan_timeout=20.0, idle_timeout=60.0)

                print("🔄 Starting BLE data source with enhanced stability settings...")
                print("⚙️ Scan timeout: 20s, Test timeout: 60s")
                await ble_source.start()

                if await ble_source.is_connected():
                    print("✅ BLE connection successful!")
                    print("📊 Connection is ready for data streaming")

                    print("\n✅ BLE connection test passed!")
                    print("🔄 Using the same BLE connection for oscilloscope...")
                    print("⚠️ Connection will remain active for oscilloscope use")
                    input("Press Enter to start the oscilloscope...")
                else:
                    print("❌ BLE connection failed")
                    await ble_source.stop()
                    return

        except KeyboardInterrupt:
            print("\n👋 Test cancelled by user")
            if ble_source:
                await ble_source.stop()
            return

        # Run the oscilloscope with existing or new BLE source
        run_ble_oscilloscope_with_source(ble_source)

    if __name__ == "__main__":
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print("\n👋 Application stopped by user")

except ImportError as e:
    print(f"❌ Import error: {e}")
    print("\n💡 Try running:")
    print("   uv sync")
    print("   uv run python test_ble_oscilloscope.py")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
