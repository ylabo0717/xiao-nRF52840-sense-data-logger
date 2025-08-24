#!/usr/bin/env python3
"""
Debug script to test BLE data collection without the web UI.
"""

import sys
import os
import asyncio
import time

# Add the receiver module to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

try:
    from xiao_nrf52840_sense_reciever.ble_receiver import BleDataSource, DataBuffer
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)


async def test_data_collection() -> None:
    """Test data collection and buffer functionality."""
    print("🔧 BLE Data Collection Debug Test")
    print("=" * 40)

    # Create data source and buffer
    ble_source = BleDataSource(scan_timeout=15.0, idle_timeout=30.0)
    buffer = DataBuffer(max_size=100)  # Small buffer for testing

    print("🔄 Starting BLE data collection...")

    try:
        await ble_source.start()

        if not await ble_source.is_connected():
            print("❌ Failed to connect to BLE device")
            return

        print("✅ BLE connected, collecting data...")

        data_count = 0
        start_time = time.time()

        async for row in ble_source.get_data_stream():
            # Add to buffer
            buffer.append(row)
            data_count += 1

            current_time = time.time()
            elapsed = current_time - start_time

            print(
                f"📊 #{data_count}: ax={row.ax:.2f}, ay={row.ay:.2f}, az={row.az:.2f}, "
                f"temp={row.tempC:.1f}°C, buffer_size={buffer.size}"
            )

            # Test buffer statistics
            stats = buffer.stats
            print(
                f"   📈 Stats: fill_level={stats.fill_level}, sample_rate={stats.sample_rate:.1f}Hz"
            )

            # Test get_recent function
            recent_data = buffer.get_recent(5)
            print(f"   🔍 Recent data count: {len(recent_data)}")

            # Stop after collecting some data
            if data_count >= 20 or elapsed > 30:
                print(
                    f"\n✅ Test complete! Collected {data_count} samples in {elapsed:.1f}s"
                )
                break

    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        try:
            await ble_source.stop()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(test_data_collection())
    except KeyboardInterrupt:
        print("\n👋 Debug test cancelled")
    except Exception as e:
        print(f"❌ Debug test error: {e}")
        sys.exit(1)
