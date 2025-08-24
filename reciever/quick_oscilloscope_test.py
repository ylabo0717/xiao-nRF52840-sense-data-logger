#!/usr/bin/env python3
"""
Quick oscilloscope test to identify background thread issues.
"""

import sys
import os
import time
import signal

# Add the receiver module to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

try:
    from xiao_nrf52840_sense_reciever.ble_receiver import BleDataSource
    from xiao_nrf52840_sense_reciever.oscilloscope import create_app

    def signal_handler(signum: int, frame: object) -> None:
        print(f"\n🛑 Received signal {signum}, exiting...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    def main() -> None:
        print("🔧 Quick Oscilloscope Background Thread Test")
        print("=" * 50)

        # Create BLE source and app
        ble_source = BleDataSource(
            scan_timeout=10.0, idle_timeout=20.0
        )  # Shorter timeouts
        app = create_app(
            data_source=ble_source, buffer_size=100, update_rate=5
        )  # Smaller buffer

        print("🚀 Starting background data collection...")
        app.start_data_collection()

        print("⏰ Waiting 30 seconds to see background thread activity...")

        try:
            for i in range(30):
                time.sleep(1)

                if i % 5 == 4:  # Every 5 seconds
                    buffer_size = app.buffer.size
                    stats = app.buffer.stats
                    print(
                        f"🕐 {i + 1}s: Buffer={buffer_size}, Rate={stats.sample_rate:.1f}Hz"
                    )

                    if buffer_size > 0:
                        print("✅ Background thread is working!")
                        break
            else:
                print("❌ Background thread not collecting data after 30s")

        except KeyboardInterrupt:
            print("\n🛑 Test interrupted")

        finally:
            print("🛑 Stopping data collection...")
            app.stop_data_collection()
            print("🏁 Test complete")

    if __name__ == "__main__":
        main()

except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
