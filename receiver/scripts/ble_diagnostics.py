#!/usr/bin/env python3
"""
BLE connection diagnostics and troubleshooting tool.
"""

import sys
import os
import asyncio
import subprocess
import platform
import logging

# Add the receiver module to the path (from scripts/ to src/)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Configure logging for diagnostics tool
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",  # Simple format for user-friendly output
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

try:
    from bleak import BleakScanner
except ImportError:
    logger.error("❌ Bleak library not found. Run 'uv sync' to install dependencies.")
    sys.exit(1)


async def check_bluetooth_status() -> bool:
    """Check if Bluetooth is available and working."""
    logger.info("🔵 Checking Bluetooth status...")

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
                logger.info("✅ Bluetooth is enabled on macOS")
                return True
            else:
                logger.error("❌ Bluetooth appears to be disabled on macOS")
                return False
        except Exception as e:
            logger.warning(f"⚠️ Could not check Bluetooth status on macOS: {e}")
            return True  # Assume it's working

    elif system == "linux":
        try:
            result = subprocess.run(
                ["bluetoothctl", "show"], capture_output=True, text=True, timeout=10
            )
            if "Powered: yes" in result.stdout:
                logger.info("✅ Bluetooth is powered on Linux")
                return True
            else:
                logger.error("❌ Bluetooth appears to be powered off on Linux")
                return False
        except Exception as e:
            logger.warning(f"⚠️ Could not check Bluetooth status on Linux: {e}")
            return True  # Assume it's working

    else:
        logger.warning(f"⚠️ Bluetooth status check not implemented for {system}")
        return True  # Assume it's working


async def scan_for_devices(duration: float = 10.0) -> None:
    """Scan for nearby BLE devices."""
    logger.info(f"📡 Scanning for BLE devices for {duration}s...")

    try:
        devices = await BleakScanner.discover(timeout=duration)

        if not devices:
            logger.error("❌ No BLE devices found")
            logger.info("💡 Troubleshooting:")
            logger.info("   - Make sure your XIAO device is powered on")
            logger.info("   - Check that the device is advertising")
            logger.info("   - Move closer to the device")
            return

        logger.info(f"✅ Found {len(devices)} BLE device(s):")

        xiao_devices = []
        for device in devices:
            device_name = device.name or "Unknown"
            rssi = device.rssi if hasattr(device, "rssi") else "Unknown"

            logger.info(f"   📱 {device_name} ({device.address}) RSSI: {rssi}dBm")

            if "XIAO" in device_name or "Sense" in device_name or "IMU" in device_name:
                xiao_devices.append(device)
                logger.info("      🎯 Potential XIAO device found!")

        if xiao_devices:
            logger.info(f"\n🎯 Found {len(xiao_devices)} potential XIAO device(s)")
        else:
            logger.warning("\n⚠️ No devices matching 'XIAO', 'Sense', or 'IMU' found")
            logger.info("💡 Your XIAO device should advertise as 'XIAO Sense IMU'")

    except Exception as e:
        logger.error(f"❌ Error during BLE scan: {e}")


async def test_connection_to_xiao() -> None:
    """Attempt to connect to XIAO device."""
    logger.info("\n🔌 Testing connection to XIAO Sense IMU...")

    try:
        from xiao_nrf52840_sense_receiver.ble_receiver import BleDataSource

        ble_source = BleDataSource(scan_timeout=15.0, idle_timeout=20.0)

        logger.info("🔄 Attempting connection...")
        await ble_source.start()

        if await ble_source.is_connected():
            logger.info("✅ Successfully connected to XIAO device!")

            # Try to receive a few data points
            logger.info("📊 Testing data reception...")
            data_count = 0
            start_time = asyncio.get_event_loop().time()

            try:
                async for row in ble_source.get_data_stream():
                    data_count += 1
                    current_time = asyncio.get_event_loop().time()

                    logger.info(
                        f"📈 Data point {data_count}: "
                        f"ax={row.ax:.2f}, ay={row.ay:.2f}, az={row.az:.2f}"
                    )

                    if data_count >= 3 or (current_time - start_time) > 10:
                        break

                logger.info(f"✅ Successfully received {data_count} data points")

            except asyncio.TimeoutError:
                logger.warning("⏱️ Timeout waiting for data")
            except Exception as e:
                logger.error(f"❌ Error receiving data: {e}")

        else:
            logger.error("❌ Failed to connect to XIAO device")

    except Exception as e:
        logger.error(f"❌ Connection test failed: {e}")

    finally:
        try:
            await ble_source.stop()
        except Exception:
            pass


async def main() -> None:
    """Run BLE diagnostics."""
    logger.info("🔧 XIAO nRF52840 Sense BLE Diagnostics")
    logger.info("=" * 40)

    # Check Bluetooth status
    bt_ok = await check_bluetooth_status()
    if not bt_ok:
        logger.error(
            "\n❌ Bluetooth issues detected. Please enable Bluetooth and try again."
        )
        return

    # Scan for devices
    await scan_for_devices(duration=15.0)

    # Test connection
    await test_connection_to_xiao()

    logger.info("\n🏁 Diagnostics complete")
    logger.info("\n💡 If you're still having connection issues:")
    logger.info("   1. Restart your XIAO device")
    logger.info("   2. Move closer to reduce interference")
    logger.info("   3. Check for other Bluetooth devices causing interference")
    logger.info(
        "   4. Try running the oscilloscope with the 'y' option for connection testing"
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Diagnostics cancelled by user")
    except Exception as e:
        logger.error(f"❌ Diagnostics error: {e}")
        sys.exit(1)
