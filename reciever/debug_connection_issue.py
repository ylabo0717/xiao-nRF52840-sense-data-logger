#!/usr/bin/env python3
"""
Debug script to identify the exact issue with BLE oscilloscope data display.
"""

import sys
import os
import asyncio
import time

# Add the receiver module to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

try:
    from xiao_nrf52840_sense_reciever.ble_receiver import BleDataSource, DataBuffer
    from xiao_nrf52840_sense_reciever.oscilloscope import create_app
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)


async def test_ble_and_buffer() -> None:
    """Test BLE connection and buffer integration."""
    print("🔧 BLE Connection and Buffer Debug Test")
    print("=" * 50)

    # Create BLE source and buffer (same as oscilloscope)
    ble_source = BleDataSource(scan_timeout=20.0, idle_timeout=60.0)
    buffer = DataBuffer(max_size=2000)  # Same as oscilloscope

    try:
        print("🔄 Starting BLE connection...")
        await ble_source.start()

        if not await ble_source.is_connected():
            print("❌ BLE connection failed")
            return

        print("✅ BLE connected!")
        print("📊 Collecting data into buffer...")

        data_count = 0
        start_time = time.time()

        # Collect data for 30 seconds
        async for row in ble_source.get_data_stream():
            buffer.append(row)
            data_count += 1

            current_time = time.time()
            elapsed = current_time - start_time

            # Print status every 10 samples
            if data_count % 10 == 0:
                stats = buffer.stats
                recent_data = buffer.get_recent(500)  # Same as UI

                print(
                    f"📈 #{data_count}: Buffer size={buffer.size}, "
                    f"Recent data={len(recent_data)}, "
                    f"Sample rate={stats.sample_rate:.1f}Hz, "
                    f"Fill level={stats.fill_level}"
                )

                # Test what the UI sees
                if len(recent_data) > 0:
                    print(f"   🔍 UI would see: {len(recent_data)} data points")
                    print(
                        f"   🔍 Latest data: ax={recent_data[-1].ax:.2f}, "
                        f"temp={recent_data[-1].tempC:.1f}°C"
                    )
                else:
                    print("   ❌ UI would see: NO DATA")

            # Test for 30 seconds or 100 samples
            if elapsed > 30 or data_count >= 100:
                break

        print("\n✅ Test complete!")
        print(f"📊 Total samples collected: {data_count}")
        print(f"📈 Final buffer size: {buffer.size}")
        print(f"🎯 Final buffer stats: {buffer.stats}")

        # Final test of what UI would see
        final_recent = buffer.get_recent(500)
        print(f"🔍 UI would display: {len(final_recent)} data points")

        if len(final_recent) > 0:
            print("✅ UI should show data!")
        else:
            print("❌ UI would show NO DATA - this is the problem!")

    except KeyboardInterrupt:
        print("\n🛑 Test interrupted")
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        try:
            await ble_source.stop()
            print("🔌 BLE connection closed cleanly")
        except Exception as e:
            print(f"⚠️ Error closing BLE: {e}")


def test_oscilloscope_data_flow() -> None:
    """Test the actual oscilloscope data flow."""
    print("\n" + "=" * 50)
    print("🔧 Oscilloscope Data Flow Test")
    print("=" * 50)

    ble_source = BleDataSource(scan_timeout=20.0, idle_timeout=60.0)
    app = create_app(data_source=ble_source, buffer_size=2000, update_rate=15)

    # Start data collection in background
    app.start_data_collection()

    try:
        print("🔄 Oscilloscope data collection started...")
        print("⏰ Waiting 30 seconds to collect data...")

        for i in range(30):
            time.sleep(1)

            # Check buffer status every 5 seconds
            if i % 5 == 4:
                buffer_size = app.buffer.size
                stats = app.buffer.stats
                recent_data = app.buffer.get_recent(500)

                print(
                    f"🕐 {i + 1}s: Buffer={buffer_size}, Recent={len(recent_data)}, "
                    f"Rate={stats.sample_rate:.1f}Hz"
                )

        final_size = app.buffer.size
        final_recent = app.buffer.get_recent(500)

        print("\n📊 Final results:")
        print(f"   Buffer size: {final_size}")
        print(f"   UI data points: {len(final_recent)}")

        if len(final_recent) > 0:
            print("✅ Oscilloscope should work!")
        else:
            print("❌ Oscilloscope will show no data!")

    except KeyboardInterrupt:
        print("\n🛑 Test interrupted")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        app.stop_data_collection()
        print("🔌 Data collection stopped")


async def main() -> None:
    """Run debug tests."""
    choice = input(
        "Choose test:\n1. BLE + Buffer test\n2. Oscilloscope data flow test\n3. Both\nChoice (1-3): "
    )

    if choice in ["1", "3"]:
        await test_ble_and_buffer()

    if choice in ["2", "3"]:
        test_oscilloscope_data_flow()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Debug cancelled")
    except Exception as e:
        print(f"❌ Debug error: {e}")
        sys.exit(1)
