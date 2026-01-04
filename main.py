"""
IRONVAULT Trading Bot
Main entry point.
"""

import sys
from PySide6.QtWidgets import QApplication
from frontend.main_window import MainWindow


def main():
    """Application entry point."""
    # v2.5 Performance Optimization: Use uvloop if available
    if sys.platform != "win32":
        try:
            import uvloop
            import asyncio
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            print("🚀 uvloop activated for high-performance async I/O")
        except ImportError:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("IRONVAULT Trading Bot")
    app.setOrganizationName("IRONVAULT")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
