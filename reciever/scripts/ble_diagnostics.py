#!/usr/bin/env python3
"""
BLE connection diagnostics and troubleshooting tool.
"""

import sys
import os
import asyncio
import subprocess
import platform

# Add the receiver module to the path (from scripts/ to src/)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    from bleak import BleakScanner
except ImportError:
    print("❌ Bleak library not found. Run 'uv sync' to install dependencies.")
    sys.exit(1)


async def check_bluetooth_status() -> bool:
    """Check if Bluetooth is available and working."""
    print("🔵 Checking Bluetooth status...")

    system = platform.system().lower()

    if system == "darwin":  # macOS
        try:
            result = subprocess.run(
                ["system_profiler", "SPBluetoothDataType"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if "State: On" in result.stdout:
                print("✅ Bluetooth is enabled on macOS")
                return True
            else:
                print("❌ Bluetooth appears to be disabled on macOS")
                return False
        except Exception as e:
            print(f"⚠️ Could not check Bluetooth status on macOS: {e}")
            return True  # Assume it's working

    elif system == "linux":
        try:
            result = subprocess.run(
                ["bluetoothctl", "show"], capture_output=True, text=True, timeout=10
            )
            if "Powered: yes" in result.stdout:
                print("✅ Bluetooth is powered on Linux")
                return True
            else:
                print("❌ Bluetooth appears to be powered off on Linux")
                return False
        except Exception as e:
            print(f"⚠️ Could not check Bluetooth status on Linux: {e}")
            return True  # Assume it's working

    else:
        print(f"⚠️ Bluetooth status check not implemented for {system}")
        return True  # Assume it's working


async def scan_for_devices(duration: float = 10.0) -> None:
    """Scan for nearby BLE devices."""
    print(f"📡 Scanning for BLE devices for {duration}s...")

    try:
        devices = await BleakScanner.discover(timeout=duration)

        if not devices:
            print("❌ No BLE devices found")
            print("💡 Troubleshooting:")
            print("   - Make sure your XIAO device is powered on")
            print("   - Check that the device is advertising")
            print("   - Move closer to the device")
            return

        print(f"✅ Found {len(devices)} BLE device(s):")

        xiao_devices = []
        for device in devices:
            device_name = device.name or "Unknown"
            rssi = device.rssi if hasattr(device, "rssi") else "Unknown"

            print(f"   📱 {device_name} ({device.address}) RSSI: {rssi}dBm")

            if "XIAO" in device_name or "Sense" in device_name or "IMU" in device_name:
                xiao_devices.append(device)
                print("      🎯 Potential XIAO device found!")

        if xiao_devices:
            print(f"\n🎯 Found {len(xiao_devices)} potential XIAO device(s)")
        else:
            print("\n⚠️ No devices matching 'XIAO', 'Sense', or 'IMU' found")
            print("💡 Your XIAO device should advertise as 'XIAO Sense IMU'")

    except Exception as e:
        print(f"❌ Error during BLE scan: {e}")


async def test_connection_to_xiao() -> None:
    """Attempt to connect to XIAO device."""
    print("\n🔌 Testing connection to XIAO Sense IMU...")

    try:
        from xiao_nrf52840_sense_reciever.ble_receiver import BleDataSource  # type: ignore[import-not-found]

        ble_source = BleDataSource(scan_timeout=15.0, idle_timeout=20.0)

        print("🔄 Attempting connection...")
        await ble_source.start()

        if await ble_source.is_connected():
            print("✅ Successfully connected to XIAO device!")

            # Try to receive a few data points
            print("📊 Testing data reception...")
            data_count = 0
            start_time = asyncio.get_event_loop().time()

            try:
                async for row in ble_source.get_data_stream():
                    data_count += 1
                    current_time = asyncio.get_event_loop().time()

                    print(
                        f"📈 Data point {data_count}: "
                        f"ax={row.ax:.2f}, ay={row.ay:.2f}, az={row.az:.2f}"
                    )

                    if data_count >= 3 or (current_time - start_time) > 10:
                        break

                print(f"✅ Successfully received {data_count} data points")

            except asyncio.TimeoutError:
                print("⏱️ Timeout waiting for data")
            except Exception as e:
                print(f"❌ Error receiving data: {e}")

        else:
            print("❌ Failed to connect to XIAO device")

    except Exception as e:
        print(f"❌ Connection test failed: {e}")

    finally:
        try:
            await ble_source.stop()
        except Exception:
            pass


async def main() -> None:
    """Run BLE diagnostics."""
    print("🔧 XIAO nRF52840 Sense BLE Diagnostics")
    print("=" * 40)

    # Check Bluetooth status
    bt_ok = await check_bluetooth_status()
    if not bt_ok:
        print("\n❌ Bluetooth issues detected. Please enable Bluetooth and try again.")
        return

    # Scan for devices
    await scan_for_devices(duration=15.0)

    # Test connection
    await test_connection_to_xiao()

    print("\n🏁 Diagnostics complete")
    print("\n💡 If you're still having connection issues:")
    print("   1. Restart your XIAO device")
    print("   2. Move closer to reduce interference")
    print("   3. Check for other Bluetooth devices causing interference")
    print(
        "   4. Try running the oscilloscope with the 'y' option for connection testing"
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Diagnostics cancelled by user")
    except Exception as e:
        print(f"❌ Diagnostics error: {e}")
        sys.exit(1)
