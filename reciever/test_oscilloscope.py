#!/usr/bin/env python3
"""
Test script for the oscilloscope visualization.
"""

import sys
import os

# Add the receiver module to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "reciever", "src"))

try:
    from xiao_nrf52840_sense_reciever.oscilloscope import create_app

    print("✓ Successfully imported oscilloscope module")

    # Create app with mock data
    app = create_app()
    print("✓ Successfully created oscilloscope app")

    print("Starting oscilloscope with mock data...")
    print("Open your browser to http://127.0.0.1:8050")
    print("Press Ctrl+C to stop")

    # Run the app
    app.run(debug=True)

except KeyboardInterrupt:
    print("\n✓ Application stopped by user")
except ImportError as e:
    print(f"✗ Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"✗ Error: {e}")
    sys.exit(1)
