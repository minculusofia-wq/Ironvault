"""
IRONVAULT Trading Bot
Main entry point.
"""

import sys
from PySide6.QtWidgets import QApplication
from frontend.main_window import MainWindow


def main():
    """Application entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName("IRONVAULT Trading Bot")
    app.setOrganizationName("IRONVAULT")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
