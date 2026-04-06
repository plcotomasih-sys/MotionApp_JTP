# connection_dialog.py
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QLineEdit, QPushButton, QMessageBox, QGroupBox,
                               QSpinBox, QFormLayout)
from PySide6.QtCore import Qt, QTimer
from connection.plc_connection import PLCConnection

class ConnectionDialog(QDialog):
    """Dialog untuk mengatur dan test koneksi PLC"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PLC Connection Setup")
        self.setModal(True)
        self.setMinimumWidth(450)

        self.plc = PLCConnection()
        
        # Variabel hasil
        self.result = None
        
        self.setup_ui()
        self.load_current_config()
        
    def setup_ui(self):
        """Setup UI dialog"""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Group untuk parameter koneksi
        conn_group = QGroupBox("Modbus TCP Connection Parameters")
        form_layout = QFormLayout()
        
        # IP Address
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("192.168.1.100")
        self.ip_input.setMinimumWidth(200)
        form_layout.addRow("IP Address:", self.ip_input)
        
        # Port
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(502)
        form_layout.addRow("Port:", self.port_input)
        
        # Unit ID (Slave ID)
        self.unit_id_input = QSpinBox()
        self.unit_id_input.setRange(1, 255)
        self.unit_id_input.setValue(1)
        form_layout.addRow("Unit ID:", self.unit_id_input)
        
        conn_group.setLayout(form_layout)
        layout.addWidget(conn_group)
        
        # Group untuk status koneksi
        status_group = QGroupBox("Connection Status")
        status_layout = QVBoxLayout()
        
        self.status_label = QLabel("⚪ Not tested")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: orange; font-weight: bold; padding: 10px;")
        status_layout.addWidget(self.status_label)
        
        self.detail_label = QLabel("")
        self.detail_label.setAlignment(Qt.AlignCenter)
        self.detail_label.setStyleSheet("color: gray; font-size: 10px;")
        status_layout.addWidget(self.detail_label)
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self.test_connection)
        self.test_btn.setMinimumHeight(35)
        button_layout.addWidget(self.test_btn)
        
        self.connect_btn = QPushButton("Save & Connect")
        self.connect_btn.setStyleSheet("background-color: green; color: white;")
        self.connect_btn.clicked.connect(self.save_and_connect)
        self.connect_btn.setEnabled(False)
        button_layout.addWidget(self.connect_btn)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
        
        # Info text
        info_label = QLabel(
            "📌 Note:\n"
            "• Make sure the PLC is powered on and reachable\n"
            "• Check that Modbus TCP Server is enabled on PLC\n"
            "• Default port is 502, Unit ID is usually 1\n"
            "• Click 'Test Connection' first to verify settings"
        )
        info_label.setStyleSheet("color: gray; font-size: 10px; background-color: #2b2b2b; padding: 8px; border-radius: 4px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
    def load_current_config(self):
        """Load konfigurasi yang ada"""
        config = self.plc.get_modbus_address()
        self.ip_input.setText(config['ip_address'])
        self.port_input.setValue(config['port'])
        self.unit_id_input.setValue(config['unit_id'])
        
    def test_connection(self):
        """Test koneksi ke PLC"""
        # Ambil nilai dari input
        ip = self.ip_input.text().strip()
        port = self.port_input.value()
        unit_id = self.unit_id_input.value()
        
        if not ip:
            QMessageBox.warning(self, "Invalid Input", "Please enter IP address")
            return
            
        # Update status
        self.status_label.setText("⏳ Testing connection...")
        self.status_label.setStyleSheet("color: orange; font-weight: bold; padding: 10px;")
        self.detail_label.setText(f"Connecting to {ip}:{port}...")
        
        # Set Modbus address
        self.plc.set_modbus_address(ip, port, unit_id)
        
        # Coba connect
        if self.plc.connect():
            # Test koneksi kirim heartbeat
            if self.plc.test_read_register():

                self.status_label.setText("✓ Connection Successful!")
                self.status_label.setStyleSheet("color: green; font-weight: bold; padding: 10px;")
                self.detail_label.setText(
                    f"Connected to {ip}:{port}\n"
                    f"Unit ID: {unit_id}\n"
                    f"Read test OK"
                )

                self.connect_btn.setEnabled(True)

            else:
                self.status_label.setText("⚠️ Connected but read failed")
                self.status_label.setStyleSheet("color: orange; font-weight: bold; padding: 10px;")
                self.detail_label.setText(
                    f"Connected but cannot read register.\n"
                    f"Check Unit ID ({unit_id}) or address"
                )

                self.connect_btn.setEnabled(True)
        else:
            self.status_label.setText("✗ Connection Failed")
            self.status_label.setStyleSheet("color: red; font-weight: bold; padding: 10px;")
            self.detail_label.setText(
                f"Could not connect to {ip}:{port}\n\n"
                "Please check:\n"
                "• IP address is correct\n"
                "• PLC is powered on\n"
                "• Network cable is connected\n"
                "• Modbus TCP Server is enabled"
            )
            self.connect_btn.setEnabled(True)  # Tetap bisa save setting
            self.plc.disconnect()
            
    def save_and_connect(self):
        """Save settings and accept dialog"""
        ip = self.ip_input.text().strip()
        port = self.port_input.value()
        unit_id = self.unit_id_input.value()
        
        # Set dan simpan konfigurasi
        self.plc.set_modbus_address(ip, port, unit_id)
        self.plc.save_config()
        
        # Coba connect terakhir
        connected = False
        if self.plc.connect():
            connected = True
            self.plc.disconnect()  # Disconnect setelah test
            
        # Simpan hasil
        self.result = {
            'ip_address': ip,
            'port': port,
            'unit_id': unit_id,
            'connected': connected
        }
        
        self.accept()