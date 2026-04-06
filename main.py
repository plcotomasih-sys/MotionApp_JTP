# main.py
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QMessageBox, QDialog, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence

from thread.video_thread import VideoThread
from thread.record_thread import RecordThread
from tab.video_player_tab import VideoPlayerTab
from tab.record_motion_tab import RecordMotionTab
from connection.plc_connection import PLCConnection
from connection.connection_dialog import ConnectionDialog
from styles import apply_styles

class MotionControlApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Motion Control Application")
        self.setGeometry(100, 100, 1200, 700)

        # Init PLC connection
        self.plc = PLCConnection()
        self.plc_connected = False

        if not self.check_plc_connection():
            print("PLC connection failed")
            sys.exit(0)
        
        # Flag untuk fullscreen
        self.is_fullscreen = False
        
        # Create threads
        self.video_thread = VideoThread()
        self.record_thread = RecordThread()
        
        # Setup UI
        self.setup_ui()
        self.setup_menu()
        
        # Start threads
        self.video_thread.start()
        self.record_thread.start()

    def check_plc_connection(self):
        """Cek koneksi PLC, tampilkan dialog jika tidak terhubung"""
        # Coba load konfigurasi yang sudah ada
        self.plc.load_config()
        
        # Coba connect dengan konfigurasi yang ada
        if self.plc.connect():
            self.plc_connected = True
            print(f"PLC Connected to {self.plc.ip_address}:{self.plc.port}")
            return True
        else:
            # Tampilkan dialog koneksi
            return self.show_connection_dialog()
            
    def show_connection_dialog(self):
        """Tampilkan dialog untuk setting koneksi PLC"""
        dialog = ConnectionDialog(self)
        
        if dialog.exec() == QDialog.Accepted:
            result = dialog.result
            if result:
                self.plc.set_modbus_address(
                    result['ip_address'],
                    result['port'],
                    result['unit_id']
                )
                self.plc_connected = result['connected']
                
                if self.plc_connected:
                    QMessageBox.information(
                        self, 
                        "Connection Successful",
                        f"PLC connected to {result['ip_address']}:{result['port']}"
                    )
                else:
                    reply = QMessageBox.question(
                        self, 
                        "Continue without PLC?",
                        "PLC is not connected. Motion control will not work.\n\n"
                        "Do you want to continue in demo mode?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if reply == QMessageBox.Yes:
                        return True
                    else:
                        return False
                return True
            else:
                return False
        else:
            return False
        
    def setup_ui(self):
        """Setup main UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        # Status bar untuk PLC
        self.status_bar = self.statusBar()
        self.plc_status_label = QLabel()
        self.update_plc_status()
        self.status_bar.addPermanentWidget(self.plc_status_label)
        
        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Video Player Tab
        self.video_tab = VideoPlayerTab(self.video_thread)
        self.tabs.addTab(self.video_tab, "Video Player")
        
        # Record Motion Tab
        self.record_tab = RecordMotionTab(self.record_thread, self.plc)
        self.tabs.addTab(self.record_tab, "Record Motion")
        
        # Set style
        self.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; }
            QTabWidget::pane {
                border: 1px solid #444;
                background-color: #353535;
            }
            QTabBar::tab {
                background-color: #2b2b2b;
                color: #ccc;
                padding: 8px 16px;
            }
            QTabBar::tab:selected {
                background-color: #353535;
                color: white;
            }
            QPushButton {
                background-color: #4a4a4a;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #5a5a5a; }
            QPushButton:pressed { background-color: #3a3a3a; }
            QSlider::groove:horizontal {
                height: 4px;
                background: #3a3a3a;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #7a7a7a;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:hover { background: #9a9a9a; }
            QLabel { color: #ccc; }
            QGroupBox {
                color: #ccc;
                border: 1px solid #444;
                border-radius: 4px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QMenuBar {
                background-color: #2b2b2b;
                color: #ccc;
            }
            QMenuBar::item:selected {
                background-color: #4a4a4a;
            }
            QMenu {
                background-color: #2b2b2b;
                color: #ccc;
                border: 1px solid #444;
            }
            QMenu::item:selected {
                background-color: #4a4a4a;
            }
        """)
        
    def setup_menu(self):
        """Setup menu bar"""
        menubar = self.menuBar()
        
        # View menu
        view_menu = menubar.addMenu("View")
        
        # Fullscreen action
        fullscreen_action = QAction("Fullscreen", self)
        fullscreen_action.setShortcut(QKeySequence("F11"))
        fullscreen_action.triggered.connect(self.toggle_fullscreen)
        view_menu.addAction(fullscreen_action)
        
        # Exit fullscreen action
        exit_fullscreen_action = QAction("Exit Fulls...", self)
        exit_fullscreen_action.setShortcut(QKeySequence("Esc"))
        exit_fullscreen_action.triggered.connect(self.exit_fullscreen)
        view_menu.addAction(exit_fullscreen_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        shortcut_action = QAction("Shortcuts", self)
        shortcut_action.triggered.connect(self.show_shortcuts)
        help_menu.addAction(shortcut_action)
        
    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        if self.is_fullscreen:
            self.exit_fullscreen()
        else:
            self.enter_fullscreen()
            
    def enter_fullscreen(self):
        """Enter fullscreen mode"""
        self.is_fullscreen = True
        self.showFullScreen()
        
        # self.menuBar().hide()
        # self.tabs.tabBar().hide()
        
    def exit_fullscreen(self):
        """Exit fullscreen mode"""
        self.is_fullscreen = False
        self.showNormal()
            
    def show_shortcuts(self):
        """Show keyboard shortcuts"""
        from PySide6.QtWidgets import QMessageBox
        
        shortcuts = """
        <h3>Keyboard Shortcuts</h3>
        <table>
        <tr><td><b>F11</b></td><td>Toggle Fullscreen</td></tr>
        <tr><td><b>Esc</b></td><td>Exit Fullscreen</td></tr>
        </table>
        """
        
        QMessageBox.information(self, "Keyboard Shortcuts", shortcuts)

    def update_plc_status(self):
        """Update status PLC di status bar"""
        if self.plc_connected:
            self.plc_status_label.setText(f"🔌 PLC: {self.plc.ip_address}:{self.plc.port} ✓")
            self.plc_status_label.setStyleSheet("color: green; padding: 0 10px;")
        else:
            self.plc_status_label.setText("🔌 PLC: Not Connected ✗")
            self.plc_status_label.setStyleSheet("color: red; padding: 0 10px;")
        
    def closeEvent(self, event):
        """Handle close event"""
        self.video_thread.stop_thread()
        self.record_thread.stop_thread()
        event.accept()

def main():
    app = QApplication(sys.argv)
    window = MotionControlApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()