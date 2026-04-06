# main.py
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QMessageBox, QDialog, QLabel
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence

from thread.video_thread import VideoThread
from thread.record_thread import RecordThread
from tab.video_player_tab import VideoPlayerTab
from tab.record_motion_tab import RecordMotionTab
from connection.plc_connection import PLCConnection
from connection.connection_dialog import ConnectionDialog
from control.plc_data_sender import PLCDataSender

class MotionControlApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Motion Control Application")
        self.setGeometry(100, 100, 1200, 700)

        # Init PLC connection
        self.plc = PLCConnection()
        self.plc_connected = False
        
        # Init PLC data sender
        self.plc_sender = PLCDataSender(self.plc)
        
        # Flag untuk fullscreen
        self.is_fullscreen = False
        
        # Create threads TERLEBIH DAHULU sebelum setup UI
        self.video_thread = VideoThread()
        self.record_thread = RecordThread()
        
        # Inisialisasi atribut UI (akan di-set di setup_ui)
        self.plc_status_label = None
        self.plc_safety_label = None
        self.plc_stats_label = None
        self.video_tab = None
        self.record_tab = None
        self.tabs = None
        
        # Setup UI (sekarang video_thread sudah ada)
        self.setup_ui()
        self.setup_menu()
        
        # Connect PLC signals setelah UI siap
        self.plc.connection_status_changed.connect(self.on_plc_status_changed)
        self.plc.safety_status_changed.connect(self.on_plc_safety_changed)
        self.plc.error_occurred.connect(self.on_plc_error)
        
        # Connect PLC sender signals
        self.plc_sender.data_sent.connect(self.on_plc_data_sent)
        self.plc_sender.data_failed.connect(self.on_plc_data_failed)
        self.plc_sender.connection_error.connect(self.on_plc_connection_error)

        # Check PLC connection
        if not self.check_plc_connection():
            print("PLC connection failed - continuing in demo mode")
            # Tidak exit, lanjut dengan demo mode
        
        # Setup status timer
        self.setup_status_timer()
        
        # Start threads
        self.video_thread.start()
        self.record_thread.start()
        
        # Start PLC data sender (dalam mode idle)
        self.plc_sender.start_sending()

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

        # Status bar untuk PLC - inisialisasi setelah central widget dibuat
        self.status_bar = self.statusBar()
        
        # Buat label untuk status bar
        self.plc_status_label = QLabel()
        self.plc_safety_label = QLabel()
        self.plc_stats_label = QLabel()
        
        # Set initial text
        self.plc_status_label.setText("🔌 PLC: Checking...")
        self.plc_safety_label.setText("")
        self.plc_stats_label.setText("")
        
        # Tambahkan ke status bar
        self.status_bar.addPermanentWidget(self.plc_status_label)
        self.status_bar.addPermanentWidget(self.plc_safety_label)
        self.status_bar.addPermanentWidget(self.plc_stats_label)
        
        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Video Player Tab (pass PLC connection dan sender)
        # Pastikan video_thread sudah dibuat
        if not hasattr(self, 'video_thread') or self.video_thread is None:
            raise AttributeError("video_thread must be created before setup_ui")
        
        self.video_tab = VideoPlayerTab(self.video_thread, self.plc)
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
        
        # Update status setelah UI siap
        self.update_plc_status()
        
    def setup_menu(self):
        """Setup menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        # Reconnect PLC action
        reconnect_action = QAction("Reconnect PLC", self)
        reconnect_action.setShortcut(QKeySequence("Ctrl+R"))
        reconnect_action.triggered.connect(self.reconnect_plc)
        file_menu.addAction(reconnect_action)
        
        # Emergency stop action
        emergency_action = QAction("🔴 Emergency Stop", self)
        emergency_action.setShortcut(QKeySequence("Ctrl+E"))
        emergency_action.triggered.connect(self.emergency_stop)
        # emergency_action.setStyleSheet("color: red;")
        file_menu.addAction(emergency_action)
        
        file_menu.addSeparator()
        
        # Exit action
        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # View menu
        view_menu = menubar.addMenu("View")
        
        # Fullscreen action
        fullscreen_action = QAction("Fullscreen", self)
        fullscreen_action.setShortcut(QKeySequence("F11"))
        fullscreen_action.triggered.connect(self.toggle_fullscreen)
        view_menu.addAction(fullscreen_action)
        
        # Exit fullscreen action
        exit_fullscreen_action = QAction("Exit Fullscreen", self)
        exit_fullscreen_action.setShortcut(QKeySequence("Esc"))
        exit_fullscreen_action.triggered.connect(self.exit_fullscreen)
        view_menu.addAction(exit_fullscreen_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        shortcut_action = QAction("Shortcuts", self)
        shortcut_action.triggered.connect(self.show_shortcuts)
        help_menu.addAction(shortcut_action)
        
        # About action
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
    def setup_status_timer(self):
        """Setup timer untuk update status bar"""
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status_bar)
        self.status_timer.start(1000)  # Update setiap 1 detik
        
    def update_status_bar(self):
        """Update status bar dengan informasi PLC"""
        if self.plc_stats_label:  # Cek apakah label sudah ada
            stats = self.plc_sender.get_statistics()
            
            if self.plc_connected and not self.plc.safety_active:
                # Tampilkan statistik pengiriman
                self.plc_stats_label.setText(
                    f"📊 Sent: {stats['total_sent']} | "
                    f"Failed: {stats['total_failed']} | "
                    f"Rate: {stats['success_rate']:.1f}%"
                )
                self.plc_stats_label.setStyleSheet("color: #888; padding: 0 10px;")
            elif self.plc.safety_active:
                self.plc_stats_label.setText("⚠️ SAFETY MODE ACTIVE")
                self.plc_stats_label.setStyleSheet("color: orange; padding: 0 10px; font-weight: bold;")
            else:
                self.plc_stats_label.setText("")
            
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
        
    def exit_fullscreen(self):
        """Exit fullscreen mode"""
        self.is_fullscreen = False
        self.showNormal()
            
    def show_shortcuts(self):
        """Show keyboard shortcuts"""
        from PySide6.QtWidgets import QMessageBox
        
        shortcuts = """
        <h3>Keyboard Shortcuts</h3>
        <table border="0" cellpadding="5">
        <tr><td><b>F11</b></td><td>Toggle Fullscreen</td></tr>
        <tr><td><b>Esc</b></td><td>Exit Fullscreen</td></tr>
        <tr><td><b>Ctrl+R</b></td><td>Reconnect PLC</td></tr>
        <tr><td><b>Ctrl+E</b></td><td>Emergency Stop</td></tr>
        <tr><td><b>Ctrl+Q</b></td><td>Exit Application</td></tr>
        <tr><td colspan="2"><hr></td></tr>
        <tr><td colspan="2"><b>Video Player:</b></td></tr>
        <tr><td><b>Space</b></td><td>Play/Pause</td></tr>
        <tr><td><b>←</b></td><td>Seek Backward</td></tr>
        <tr><td><b>→</b></td><td>Seek Forward</td></tr>
        </table>
        """
        
        msg = QMessageBox(self)
        msg.setWindowTitle("Keyboard Shortcuts")
        msg.setText(shortcuts)
        msg.exec()
        
    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(
            self,
            "About Motion Control Application",
            """
            <h3>Motion Control Application</h3>
            <p>Version 1.0</p>
            <p>Application untuk kontrol motion dengan video synchronization.</p>
            <p>Features:</p>
            <ul>
                <li>Video playback dengan motion data synchronization</li>
                <li>PLC communication via Modbus TCP</li>
                <li>Real-time servo control</li>
                <li>Motion recording dengan joystick</li>
            </ul>
            """
        )

    def update_plc_status(self):
        """Update status PLC di status bar"""
        # Cek apakah label sudah ada
        if not hasattr(self, 'plc_status_label') or self.plc_status_label is None:
            return
            
        if self.plc_connected:
            if self.plc.safety_active:
                self.plc_status_label.setText("⚠️ SAFETY ACTIVE")
                self.plc_status_label.setStyleSheet("color: orange; padding: 0 10px; font-weight: bold;")
            else:
                self.plc_status_label.setText(f"🔌 PLC: {self.plc.ip_address}:{self.plc.port} ✓")
                self.plc_status_label.setStyleSheet("color: green; padding: 0 10px;")
        else:
            self.plc_status_label.setText("🔌 PLC: Not Connected ✗")
            self.plc_status_label.setStyleSheet("color: red; padding: 0 10px;")
    
    def on_plc_status_changed(self, connected, message):
        """Handle PLC status change"""
        self.plc_connected = connected
        self.update_plc_status()
        
        if connected:
            print(f"PLC Status: {message}")
            # Update safety label
            if hasattr(self, 'plc_safety_label') and self.plc_safety_label:
                self.plc_safety_label.setText("")
        else:
            print(f"PLC Disconnected: {message}")
            # Update safety label
            if hasattr(self, 'plc_safety_label') and self.plc_safety_label:
                self.plc_safety_label.setText("⚠️ DISCONNECTED")
                self.plc_safety_label.setStyleSheet("color: red; padding: 0 10px;")
            
            # Tampilkan warning jika video sedang diputar
            if hasattr(self, 'video_tab') and self.video_tab and self.video_tab.is_playing:
                QMessageBox.warning(
                    self,
                    "PLC Disconnected",
                    "PLC connection lost during playback.\n"
                    "Motion control is disabled until reconnection."
                )
    
    def on_plc_safety_changed(self, safety_active):
        """Handle PLC safety status change"""
        self.update_plc_status()
        
        if safety_active:
            # Update safety label
            if hasattr(self, 'plc_safety_label') and self.plc_safety_label:
                self.plc_safety_label.setText("🔴 SAFETY")
                self.plc_safety_label.setStyleSheet("color: red; padding: 0 10px; font-weight: bold;")
            
            # Stop video playback jika safety aktif
            if hasattr(self, 'video_tab') and self.video_tab and self.video_tab.is_playing:
                self.video_tab.pause_video()
            
            QMessageBox.critical(
                self,
                "SAFETY MODE ACTIVATED",
                "Safety mode has been activated!\n\n"
                "All servo outputs are disabled.\n"
                "Please check the system and reset safety."
            )
        # else:
        #     # Clear safety label
        #     if hasattr(self, 'plc_safety_label') and self.plc_safety_label:
        #         self.plc_safety_label.setText("")
            
        #     QMessageBox.information(
        #         self,
        #         "Safety Mode Deactivated",
        #         "Safety mode has been deactivated.\n"
        #         "Normal operation resumed."
        #     )
    
    def on_plc_error(self, error_msg):
        """Handle PLC error"""
        print(f"PLC Error: {error_msg}")
        # Log error untuk debugging
        if "timeout" in error_msg.lower():
            self.statusBar().showMessage(f"PLC Timeout: {error_msg}", 3000)
    
    def on_plc_data_sent(self, data):
        """Handle successful data sent to PLC"""
        # Update status bar dengan timestamp
        if data['timestamp'] % 1.0 < 0.05:  # Update setiap detik
            self.statusBar().showMessage(
                f"PLC Data Sent: S1={data['servo1']}, S2={data['servo2']}, S3={data['servo3']}",
                1000
            )
    
    def on_plc_data_failed(self, error_msg):
        """Handle failed data sent"""
        print(f"PLC Data Send Failed: {error_msg}")
        self.statusBar().showMessage(f"PLC Send Failed: {error_msg}", 2000)
    
    def on_plc_connection_error(self, error_msg):
        """Handle PLC connection error"""
        print(f"PLC Connection Error: {error_msg}")
        self.plc_connected = False
        self.update_plc_status()
        
        # Tampilkan warning sekali saja
        if not hasattr(self, '_connection_error_shown'):
            self._connection_error_shown = True
            QMessageBox.warning(
                self,
                "PLC Connection Error",
                f"Failed to communicate with PLC:\n{error_msg}\n\n"
                "Motion control may not work properly.\n"
                "Try reconnecting via File > Reconnect PLC"
            )
            QTimer.singleShot(5000, lambda: setattr(self, '_connection_error_shown', False))
    
    def reconnect_plc(self):
        """Reconnect to PLC"""
        reply = QMessageBox.question(
            self,
            "Reconnect PLC",
            "Do you want to reconnect to PLC?\n\n"
            "Current connection will be closed.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Disconnect existing
            self.plc.disconnect()
            
            # Show connection dialog
            if self.show_connection_dialog():
                QMessageBox.information(
                    self,
                    "Reconnection Successful",
                    "PLC reconnected successfully."
                )
            else:
                QMessageBox.warning(
                    self,
                    "Reconnection Failed",
                    "Failed to reconnect to PLC.\n"
                    "Please check PLC connection and try again."
                )
    
    def emergency_stop(self):
        """Emergency stop all motion"""
        reply = QMessageBox.question(
            self,
            "EMERGENCY STOP",
            "⚠️ EMERGENCY STOP ⚠️\n\n"
            "This will immediately stop all motion and send stop command to PLC.\n\n"
            "Are you sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Stop video playback
            if hasattr(self, 'video_tab') and self.video_tab:
                self.video_tab.stop_video()
            
            # Send emergency stop to PLC
            if self.plc_sender.send_emergency_stop():
                QMessageBox.critical(
                    self,
                    "Emergency Stop",
                    "EMERGENCY STOP ACTIVATED!\n\n"
                    "All servo outputs have been set to 0.\n"
                    "Please reset the system before continuing."
                )
            else:
                QMessageBox.critical(
                    self,
                    "Emergency Stop Failed",
                    "Failed to send emergency stop command to PLC!\n\n"
                    "Please check PLC connection."
                )
    
    def closeEvent(self, event):
        """Handle close event"""
        # Send neutral position before closing
        if hasattr(self, 'plc_sender'):
            # self.plc_sender.send_neutral_position()
            self.plc_sender.stop_sending()
        
        # Stop threads
        if hasattr(self, 'video_thread'):
            self.video_thread.stop_thread()
        if hasattr(self, 'record_thread'):
            self.record_thread.stop_thread()
        
        # Disconnect PLC
        if hasattr(self, 'plc'):
            self.plc.disconnect()
        
        event.accept()

def main():
    app = QApplication(sys.argv)
    window = MotionControlApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()