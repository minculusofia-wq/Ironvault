from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtGui import QPainter, QColor, QFont

class DepthBar(QWidget):
    """A single bar representing volume at a price level."""
    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self._color = color
        self._percent = 0.0
        self.setFixedHeight(8)
        
    def set_percent(self, percent: float):
        self._percent = max(0.0, min(1.0, percent))
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw background
        painter.setBrush(QColor(40, 40, 40))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 4, 4)
        
        # Draw fill
        width = int(self.width() * self._percent)
        if width > 0:
            painter.setBrush(self._color)
            painter.drawRoundedRect(0, 0, width, self.height(), 4, 4)

class OrderBookLevel(QWidget):
    """A row in the orderbook display."""
    def __init__(self, side: str, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 2, 5, 2)
        
        self.price_label = QLabel("0.000000")
        self.price_label.setFixedWidth(80)
        self.price_label.setStyleSheet("font-weight: bold; color: #ffffff;")
        
        self.size_label = QLabel("0.00")
        self.size_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.size_label.setFixedWidth(60)
        self.size_label.setStyleSheet("color: #aaaaaa;")
        
        color = QColor(0, 200, 100) if side == "BID" else QColor(255, 60, 60)
        self.bar = DepthBar(color)
        
        self.layout.addWidget(self.price_label)
        self.layout.addWidget(self.bar)
        self.layout.addWidget(self.size_label)

class OrderbookVisualizer(QFrame):
    """Widget to visualize real-time orderbook depth."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("OrderbookVisualizer")
        self.setStyleSheet("""
            #OrderbookVisualizer {
                background: #1e1e1e;
                border: 1px solid #333;
                border-radius: 8px;
            }
            QLabel { font-size: 11px; }
        """)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        
        title = QLabel("PROFONDEUR DU CARNET (LIVE)")
        title.setStyleSheet("font-weight: bold; color: #5555ff; margin-bottom: 5px;")
        self.layout.addWidget(title)
        
        # Asks (Red) - Top to Bottom
        self.asks_layout = QVBoxLayout()
        self.asks_widgets = [OrderBookLevel("ASK") for _ in range(5)]
        for w in reversed(self.asks_widgets):
            self.asks_layout.addWidget(w)
        self.layout.addLayout(self.asks_layout)
        
        # Spread Info
        self.spread_label = QLabel("SPREAD: 0.00% | MID: 0.0000")
        self.spread_label.setAlignment(Qt.AlignCenter)
        self.spread_label.setStyleSheet("color: #ffff00; padding: 5px; background: #2a2a2a; border-radius: 4px;")
        self.layout.addWidget(self.spread_label)
        
        # Bids (Green)
        self.bids_layout = QVBoxLayout()
        self.bids_widgets = [OrderBookLevel("BID") for _ in range(5)]
        for w in self.bids_widgets:
            self.bids_layout.addWidget(w)
        self.layout.addLayout(self.bids_layout)
        
        self.layout.addStretch()

    @Slot(dict)
    def update_data(self, data: dict):
        """Update display with new orderbook data."""
        # Expected format: {bids: [(p, s), ...], asks: [(p, s), ...], midpoint: m, spread_pct: s}
        bids = data.get("bids", [])[:5]
        asks = data.get("asks", [])[:5]
        
        max_vol = 0.0
        if bids or asks:
            max_vol = max(
                max([float(b[1]) for b in bids] if bids else [0]),
                max([float(a[1]) for a in asks] if asks else [0])
            )

        # Update Bids
        for i, widget in enumerate(self.bids_widgets):
            if i < len(bids):
                p, s = bids[i]
                widget.price_label.setText(f"{float(p):.6f}")
                widget.size_label.setText(f"{float(s):.2f}")
                widget.bar.set_percent(float(s) / max_vol if max_vol > 0 else 0)
                widget.show()
            else:
                widget.hide()

        # Update Asks
        for i, widget in enumerate(self.asks_widgets):
            if i < len(asks):
                p, s = asks[i]
                widget.price_label.setText(f"{float(p):.6f}")
                widget.size_label.setText(f"{float(s):.2f}")
                widget.bar.set_percent(float(s) / max_vol if max_vol > 0 else 0)
                widget.show()
            else:
                widget.hide()
                
        mid = data.get("midpoint", 0)
        spread = data.get("spread_pct", 0)
        self.spread_label.setText(f"SPREAD: {spread:.2f}% | MID: {mid:.4f}")
