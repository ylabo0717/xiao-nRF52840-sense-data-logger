#!/usr/bin/env python3
"""
Test script for BLE oscilloscope with real XIAO nRF52840 Sense device.
"""

import sys
import os
import asyncio

# Add the receiver module to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

try:
    from xiao_nrf52840_sense_reciever.ble_receiver import BleDataSource
    from xiao_nrf52840_sense_reciever.oscilloscope import create_app

    print("✓ Successfully imported BLE oscilloscope modules")

    async def test_ble_connection() -> bool:
        """Test BLE connection before starting the app."""
        print("\n🔍 Testing BLE connection to XIAO device...")

        ble_source = BleDataSource()

        try:
            print("🔄 Starting BLE data source...")
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

        # Create BLE data source
        ble_source = BleDataSource()

        # Create oscilloscope app with BLE source
        app = create_app(data_source=ble_source, buffer_size=2000, update_rate=20)

        print("🌐 Starting web interface...")
        print("📊 Open your browser to http://127.0.0.1:8052")
        print("⚡ Data update rate: 20 FPS")
        print("💾 Buffer size: 2000 samples (~80 seconds at 25Hz)")
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
        try:
            test_first = (
                input("\n🤔 Test BLE connection before starting oscilloscope? (y/N): ")
                .strip()
                .lower()
            )

            if test_first in ["y", "yes"]:
                connection_ok = await test_ble_connection()
                if not connection_ok:
                    print(
                        "\n❌ BLE connection test failed. Please check your device and try again."
                    )
                    return

                print("\n✅ BLE connection test passed!")
                input("Press Enter to start the oscilloscope...")

        except KeyboardInterrupt:
            print("\n👋 Test cancelled by user")
            return

        # Run the oscilloscope
        run_ble_oscilloscope()

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
