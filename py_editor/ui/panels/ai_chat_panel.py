"""
ai_chat_panel.py

Extracted AIChatWidget from main.py.
"""
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QTextBrowser, QPlainTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal

class ChatInputField(QPlainTextEdit):
    enter_pressed = pyqtSignal()
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.enter_pressed.emit()
            return
        super().keyPressEvent(event)

class AIChatWidget(QWidget):
    """AI chat panel for NodeCanvas assistant."""
    response_received = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        
        header = QWidget(); h_layout = QHBoxLayout(header)
        h_layout.addWidget(QLabel("AI ASSISTANT")); h_layout.addStretch()
        layout.addWidget(header)
        
        self.chat_display = QTextBrowser(); self.chat_display.setOpenExternalLinks(False)
        self.chat_display.setStyleSheet("background-color: #252526; color: #cccccc; border: none;")
        layout.addWidget(self.chat_display)
        
        self.input_field = ChatInputField(); self.input_field.setPlaceholderText("Ask the AI...")
        self.input_field.setMaximumHeight(80)
        layout.addWidget(self.input_field)
        
        self.send_btn = QPushButton("Send"); self.send_btn.clicked.connect(self._send_message)
        layout.addWidget(self.send_btn)

    def _send_message(self):
        # Placeholder for connection logic
        txt = self.input_field.toPlainText()
        if txt:
            self.chat_display.append(f"<b>You:</b> {txt}")
            self.input_field.clear()
            self.chat_display.append("<b>AI:</b> (Refactoring in progress...)")
