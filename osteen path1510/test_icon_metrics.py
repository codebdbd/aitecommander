#!/usr/bin/env python3
"""Test script to verify icon metrics are working correctly."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

try:
    # Import PyQt6 components for GUI thread testing
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    def test_in_gui_thread():
        try:
            from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
            from app.utils.ui.icon.path_service import get_icon_metrics_stats

            print("Testing icon metrics in GUI thread...")

            # Get initial metrics
            initial_metrics = get_icon_metrics_stats()
            print(f"Initial metrics: {initial_metrics}")

            # Try to load a test icon (this should trigger metrics recording)
            test_icon_path = r"B:\osteen path\app\resources\logo\logo.png"
            if os.path.exists(test_icon_path):
                print(f"Loading test icon: {test_icon_path}")
                icon = create_icon_from_path(test_icon_path)
                print(f"Icon loaded successfully: {not icon.isNull()}")

                # Get metrics after loading
                final_metrics = get_icon_metrics_stats()
                print(f"Final metrics: {final_metrics}")

                # Check if metrics were recorded properly
                if final_metrics.get("disk_loads", 0) > initial_metrics.get(
                    "disk_loads", 0
                ):
                    print("✅ Disk load was recorded in metrics")
                else:
                    print("❌ Disk load was NOT recorded in metrics")

                if final_metrics.get("load_count", 0) > initial_metrics.get(
                    "load_count", 0
                ):
                    print("✅ Load timing was recorded in metrics")
                else:
                    print("❌ Load timing was NOT recorded in metrics")

            else:
                print(f"Test icon not found: {test_icon_path}")

        except Exception as e:
            print(f"Error during test: {e}")
            import traceback

            traceback.print_exc()
        finally:
            # Exit the application
            QApplication.quit()

    if __name__ == "__main__":
        # Create QApplication for GUI thread testing
        app = (
            QApplication(sys.argv)
            if not QApplication.instance()
            else QApplication.instance()
        )

        # Use QTimer to run the test in the GUI thread
        QTimer.singleShot(100, test_in_gui_thread)

        # Start the event loop
        sys.exit(app.exec())

except Exception as e:
    print(f"Error setting up GUI test: {e}")
    import traceback

    traceback.print_exc()
