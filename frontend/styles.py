"""
Frontend Styles Module
Visual styles for the trading bot GUI.
Modern dark theme with safety-focused color coding.
"""

# Color palette
COLORS = {
    "background": "#1a1a2e",
    "surface": "#16213e",
    "surface_light": "#1f3460",
    "primary": "#0f4c75",
    "primary_light": "#3282b8",
    "accent": "#00d9ff",
    "success": "#00c853",
    "warning": "#ffc107",
    "danger": "#ff1744",
    "text": "#e8e8e8",
    "text_dim": "#8892b0",
    "border": "#2a3f5f"
}

# Main stylesheet
MAIN_STYLESHEET = f"""
QMainWindow {{
    background-color: {COLORS['background']};
}}

QWidget {{
    background-color: {COLORS['background']};
    color: {COLORS['text']};
    font-family: 'Segoe UI', 'Roboto', sans-serif;
    font-size: 13px;
}}

QFrame {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 10px;
}}

QLabel {{
    background-color: transparent;
    border: none;
    padding: 2px;
}}

QLabel[class="title"] {{
    font-size: 18px;
    font-weight: bold;
    color: {COLORS['accent']};
}}

QLabel[class="section"] {{
    font-size: 14px;
    font-weight: bold;
    color: {COLORS['text']};
}}

QLabel[class="value"] {{
    font-size: 16px;
    font-weight: bold;
}}

QLabel[class="dim"] {{
    color: {COLORS['text_dim']};
    font-size: 12px;
}}

QPushButton {{
    background-color: {COLORS['surface_light']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 10px 20px;
    font-weight: bold;
    min-width: 120px;
}}

QPushButton:hover {{
    background-color: {COLORS['primary']};
    border-color: {COLORS['primary_light']};
}}

QPushButton:pressed {{
    background-color: {COLORS['primary_light']};
}}

QPushButton:disabled {{
    background-color: {COLORS['surface']};
    color: {COLORS['text_dim']};
    border-color: {COLORS['surface_light']};
}}

QPushButton[class="launch"] {{
    background-color: {COLORS['success']};
    color: #000;
}}

QPushButton[class="launch"]:hover {{
    background-color: #00e676;
}}

QPushButton[class="pause"] {{
    background-color: {COLORS['warning']};
    color: #000;
}}

QPushButton[class="pause"]:hover {{
    background-color: #ffca28;
}}

QPushButton[class="danger"] {{
    background-color: {COLORS['danger']};
    color: #fff;
}}

QPushButton[class="danger"]:hover {{
    background-color: #ff5252;
}}

QGroupBox {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: bold;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 5px;
    color: {COLORS['text']};
}}

QProgressBar {{
    background-color: {COLORS['surface_light']};
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
    height: 20px;
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {COLORS['primary_light']};
    border-radius: 3px;
}}

QStatusBar {{
    background-color: {COLORS['surface']};
    border-top: 1px solid {COLORS['border']};
    padding: 5px;
}}

QMessageBox {{
    background-color: {COLORS['surface']};
}}

QMessageBox QLabel {{
    color: {COLORS['text']};
}}

QMessageBox QPushButton {{
    min-width: 80px;
}}
"""

# Status indicator colors
STATUS_COLORS = {
    "IDLE": COLORS["text_dim"],
    "RUNNING": COLORS["success"],
    "PAUSED": COLORS["warning"],
    "KILLED": COLORS["danger"],
    "ACTIVE": COLORS["success"],
    "INACTIVE": COLORS["text_dim"],
    "ERROR": COLORS["danger"],
    "ACTIVATING": COLORS["warning"],
    "DEACTIVATING": COLORS["warning"]
}


def get_status_style(status: str) -> str:
    """Get style for status indicator."""
    color = STATUS_COLORS.get(status, COLORS["text_dim"])
    return f"color: {color}; font-weight: bold;"


def get_capital_bar_style(usage_percent: float) -> str:
    """Get style for capital usage bar based on percentage."""
    if usage_percent < 50:
        color = COLORS["success"]
    elif usage_percent < 80:
        color = COLORS["warning"]
    else:
        color = COLORS["danger"]
    
    return f"""
        QProgressBar::chunk {{
            background-color: {color};
            border-radius: 3px;
        }}
    """
