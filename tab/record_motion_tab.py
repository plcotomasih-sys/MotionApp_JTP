# record_motion_tab.py
import os
import json
from datetime import datetime
from PySide6.QtWidgets import (QLineEdit, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QSlider, QLabel, QFileDialog, QMessageBox, QProgressBar,
                               QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
                               QComboBox, QSpinBox, QDoubleSpinBox, QSplitter, QFrame, QGridLayout)
from PySide6.QtCore import Qt, QTime, Signal, QTimer
from PySide6.QtGui import QImage, QPixmap, QColor
from control.joystick_control import JoystickController
# from plc_connection import PLCConnection
from control.servo_controller import ServoController


class RecordMotionTab(QWidget):
    """Tab untuk record motion dengan joystick"""
    
    position_recorded = Signal(dict)
    
    def __init__(self, record_thread, plc_connection):
        super().__init__()
        self.record_thread = record_thread
        self.plc = plc_connection
        self.servo = ServoController(self.plc)
        
        # Video related variables
        self.video_loaded = False
        self.is_playing = False
        self.total_frames = 0
        self.fps = 30
        self.is_loading = False
        
        # Recording related variables
        self.is_recording = False
        self.recorded_data = []
        self.last_recorded_timestamp = -1
        
        # Joystick related variables
        self.joystick = JoystickController()
        self.joystick_enabled = False
        self.last_joystick_lx = 0.0
        self.last_joystick_ly = 0.0
        self.last_joystick_ry = 0.0
        
        # Mode recording (dalam detik)
        self.record_modes = {
            "0.02s (50Hz)": 0.02,
            "0.05s (20Hz)": 0.05,
            "0.1s (10Hz)": 0.1,
            "0.5s (2Hz)": 0.5,
            "1.0s (1Hz)": 1.0,
            "Every Frame": "every_frame"
        }
        
        # Connect video thread signals
        self.record_thread.frame_ready.connect(self.update_video_display)
        self.record_thread.position_changed.connect(self.on_position_changed)
        self.record_thread.video_loaded.connect(self.on_video_loaded)
        self.record_thread.loading_error.connect(self.on_loading_error)
        self.record_thread.video_ended.connect(self.on_video_ended)
        
        # Connect joystick signals
        self.joystick.joystick_moved.connect(self.on_joystick_moved)
        self.joystick.button_pressed.connect(self.on_joystick_button)
        self.joystick.joystick_connected.connect(self.on_joystick_connection)

        self.servo_enabled_status = False
        
        # Setup UI
        self.setup_ui()
        
        # Refresh joystick list
        self.refresh_joystick_list()

        if self.plc:
            self.update_plc_status_display()

        # self.update_servo_status()
        
    def setup_ui(self):
        """Setup UI untuk record motion tab dengan panel kanan dan tabel di bawah"""
        # Main layout vertical
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)
        
        # ========== TOP SECTION: Splitter untuk Video dan Panel Kanan ==========
        top_splitter = QSplitter(Qt.Horizontal)
        
        # ----- LEFT: Video Display -----
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_panel.setLayout(left_layout)
        
        # Video display
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("""
            background-color: black;
            border: 2px solid #444;
            border-radius: 5px;
        """)
        self.video_label.setMinimumSize(512, 384)
        self.video_label.setText("No Video Loaded\n\nClick 'Load Video' to start")
        left_layout.addWidget(self.video_label)
        
        # Loading indicator
        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setVisible(False)
        self.loading_bar.setMaximumHeight(3)
        left_layout.addWidget(self.loading_bar)
        
        # Video Controls
        video_group = QGroupBox("Video Control")
        video_layout = QHBoxLayout()
        
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.clicked.connect(self.play_video)
        self.play_btn.setEnabled(False)
        video_layout.addWidget(self.play_btn)
        
        self.pause_btn = QPushButton("⏸ Pause")
        self.pause_btn.clicked.connect(self.pause_video)
        self.pause_btn.setEnabled(False)
        video_layout.addWidget(self.pause_btn)
        
        self.stop_btn = QPushButton("■ Stop")
        self.stop_btn.clicked.connect(self.stop_video)
        self.stop_btn.setEnabled(False)
        video_layout.addWidget(self.stop_btn)
        
        self.load_btn = QPushButton("📂 Load Video")
        self.load_btn.clicked.connect(self.load_video)
        video_layout.addWidget(self.load_btn)
        
        video_group.setLayout(video_layout)
        left_layout.addWidget(video_group)
        
        # Progress Slider
        slider_layout = QHBoxLayout()
        
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setEnabled(False)
        self.slider.sliderPressed.connect(self.slider_pressed)
        self.slider.sliderReleased.connect(self.slider_released)
        self.slider.valueChanged.connect(self.slider_value_changed)
        slider_layout.addWidget(self.slider)
        
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setMinimumWidth(100)
        slider_layout.addWidget(self.time_label)
        
        left_layout.addLayout(slider_layout)
        
        # Info Panel
        info_layout = QHBoxLayout()
        
        self.info_label = QLabel("No video loaded")
        self.info_label.setStyleSheet("color: #888;")
        info_layout.addWidget(self.info_label)
        
        self.frame_label = QLabel("Frame: 0 / 0")
        self.frame_label.setStyleSheet("color: #888;")
        info_layout.addWidget(self.frame_label)
        
        self.time_display = QLabel("Time: 0.00s")
        self.time_display.setStyleSheet("color: #4a9eff; font-family: monospace;")
        info_layout.addWidget(self.time_display)
        
        left_layout.addLayout(info_layout)

        info_group = QGroupBox("Information")
        info_layout = QVBoxLayout()
        
        self.plc_info_label = QLabel("PLC: Not Connected")
        self.plc_info_label.setStyleSheet("color: #888; font-size: 10px;")
        info_layout.addWidget(self.plc_info_label)
        
        self.joystick_info_label = QLabel("Joystick: Not connected")
        self.joystick_info_label.setStyleSheet("color: #888; font-size: 10px;")
        info_layout.addWidget(self.joystick_info_label)

        self.video_info_label = QLabel("Video : Not loaded")
        self.video_info_label.setStyleSheet("color: #888; font-size: 10px;")
        info_layout.addWidget(self.video_info_label)
        
        self.recording_info_label = QLabel("Recording: Not started")
        self.recording_info_label.setStyleSheet("color: #888; font-size: 10px;")
        info_layout.addWidget(self.recording_info_label)
        
        info_group.setLayout(info_layout)
        left_layout.addWidget(info_group)

        left_layout.addStretch()
        
        # ----- RIGHT: Control Panel -----
        right_panel = QWidget()
        right_panel.setMaximumWidth(380)
        right_panel.setMinimumWidth(350)
        right_layout = QVBoxLayout()
        right_panel.setLayout(right_layout)
        
        right_panel.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

         # ========== PLC Status ==========
        plc_group = QGroupBox("PLC Connection")
        plc_layout = QVBoxLayout()
        
        # Baris 1: IP Address dan B2 Port
        ip_layout_self = QHBoxLayout()
        ip_layout_self.addWidget(QLabel("IP Address:"))
        self.plc_ip_input = QLineEdit()
        self.plc_ip_input.setPlaceholderText("192.168.1.100")
        self.plc_ip_input.setText(self.plc.ip_address if self.plc else "")
        ip_layout_self.addWidget(self.plc_ip_input)

        plc_layout.addLayout(ip_layout_self)

        ip_layout = QHBoxLayout()
        
        ip_layout.addWidget(QLabel("Port:"))
        self.plc_port_input = QSpinBox()
        self.plc_port_input.setRange(1, 65535)
        self.plc_port_input.setValue(self.plc.port if self.plc else 502)
        ip_layout.addWidget(self.plc_port_input)
        
        ip_layout.addWidget(QLabel("Unit ID:"))
        self.plc_unit_input = QSpinBox()
        self.plc_unit_input.setRange(1, 255)
        self.plc_unit_input.setValue(self.plc.unit_id if self.plc else 1)
        ip_layout.addWidget(self.plc_unit_input)
        
        plc_layout.addLayout(ip_layout)
        
        # Baris 2: Tombol Koneksi
        button_layout = QHBoxLayout()
        
        self.plc_connect_btn = QPushButton("🔌 Connect")
        self.plc_connect_btn.clicked.connect(self.connect_plc)
        button_layout.addWidget(self.plc_connect_btn)
        
        self.plc_disconnect_btn = QPushButton("🔌 Disconnect")
        self.plc_disconnect_btn.clicked.connect(self.disconnect_plc)
        self.plc_disconnect_btn.setEnabled(False)
        button_layout.addWidget(self.plc_disconnect_btn)
        
        self.plc_test_btn = QPushButton("🔍 Test Connection")
        self.plc_test_btn.clicked.connect(self.test_plc_connection)
        button_layout.addWidget(self.plc_test_btn)
        
        plc_layout.addLayout(button_layout)
        
        # Baris 3: Status
        status_layout = QHBoxLayout()
        
        self.plc_status_label = QLabel("⚪ PLC: Not Connected")
        self.plc_status_label.setStyleSheet("color: orange; font-weight: bold;")
        status_layout.addWidget(self.plc_status_label)
        
        self.plc_safety_label = QLabel("🟢 Safety: Normal")
        self.plc_safety_label.setStyleSheet("color: green; font-weight: bold;")
        status_layout.addWidget(self.plc_safety_label)
        
        status_layout.addStretch()
        plc_layout.addLayout(status_layout)
        
        # Baris 4: Info detail
        self.plc_detail_label = QLabel("Waiting for connection...")
        self.plc_detail_label.setStyleSheet("color: gray; font-size: 10px;")
        plc_layout.addWidget(self.plc_detail_label)
        
        plc_group.setLayout(plc_layout)
        right_layout.addWidget(plc_group)
        
        # ========== 1. Joystick Control ==========
        joystick_group = QGroupBox("Joystick Control")
        joystick_layout = QVBoxLayout()
        
        # Pilih joystick
        select_layout = QHBoxLayout()
        select_layout.addWidget(QLabel("Joystick:"))
        
        self.joystick_combo = QComboBox()
        self.joystick_combo.addItem("No Joystick", -1)
        select_layout.addWidget(self.joystick_combo)
        
        self.refresh_joystick_btn = QPushButton("🔄")
        self.refresh_joystick_btn.setMaximumWidth(30)
        self.refresh_joystick_btn.clicked.connect(self.refresh_joystick_list)
        select_layout.addWidget(self.refresh_joystick_btn)
        
        self.connect_joystick_btn = QPushButton("Connect")
        self.connect_joystick_btn.clicked.connect(self.connect_joystick)
        select_layout.addWidget(self.connect_joystick_btn)
        
        self.disconnect_joystick_btn = QPushButton("Disconnect")
        self.disconnect_joystick_btn.clicked.connect(self.disconnect_joystick)
        self.disconnect_joystick_btn.setEnabled(False)
        select_layout.addWidget(self.disconnect_joystick_btn)
        
        joystick_layout.addLayout(select_layout)
        
        # Deadzone setting
        deadzone_layout = QHBoxLayout()
        deadzone_layout.addWidget(QLabel("Deadzone:"))
        self.deadzone_spin = QDoubleSpinBox()
        self.deadzone_spin.setRange(0.0, 0.3)
        self.deadzone_spin.setSingleStep(0.01)
        self.deadzone_spin.setValue(0.1)
        self.deadzone_spin.valueChanged.connect(self.on_deadzone_changed)
        deadzone_layout.addWidget(self.deadzone_spin)
        deadzone_layout.addStretch()
        joystick_layout.addLayout(deadzone_layout)
        
        # Joystick status
        self.joystick_status = QLabel("⚪ Not Connected")
        self.joystick_status.setStyleSheet("color: gray; font-weight: bold;")
        joystick_layout.addWidget(self.joystick_status)
        
        # Joystick values display
        values_layout = QGridLayout()
        values_layout.setColumnStretch(5, 0)
        
        values_layout.addWidget(QLabel("LX:"), 0, 0)
        self.lx_value = QLabel("0.000")
        self.lx_value.setStyleSheet("color: #888888; font-family: monospace; font-weight: bold; font-size: 14px;")
        values_layout.addWidget(self.lx_value, 0, 1)
        
        values_layout.addWidget(QLabel("LY:"), 0, 2)
        self.ly_value = QLabel("0.000")
        self.ly_value.setStyleSheet("color: #888888; font-family: monospace; font-weight: bold; font-size: 14px;")
        values_layout.addWidget(self.ly_value, 0, 3)
        
        values_layout.addWidget(QLabel("RY:"), 0, 4)
        self.ry_value = QLabel("0.000")
        self.ry_value.setStyleSheet("color: #888888; font-family: monospace; font-weight: bold; font-size: 14px;")
        values_layout.addWidget(self.ry_value, 0, 5)
        
        joystick_layout.addLayout(values_layout)
        
        joystick_group.setLayout(joystick_layout)
        right_layout.addWidget(joystick_group)

        # ====================== SERVO BUTTON
        servo_group = QGroupBox("Servo Control")    
        servo_layout = QVBoxLayout()

        self.status_servo_label = QLabel("⚪ Servo: Please Enable First!")
        servo_layout.addWidget(self.status_servo_label)

        # button1_layout = QHBoxLayout()

        # self.servo_en_btn = QPushButton("🟢 Enable Servo")
        # button1_layout.addWidget(self.servo_en_btn)

        # self.servo_dis_btn = QPushButton("🔴 Disable Servo")
        # button1_layout.addWidget(self.servo_dis_btn)

        # servo_layout.addLayout(button1_layout)

        # Baris 2: Tombol Homing dan Reset
        button2_layout = QHBoxLayout()

        self.servo_en_btn = QPushButton("Enable")
        self.servo_en_btn.clicked.connect(self.servo_enabled)
        button2_layout.addWidget(self.servo_en_btn)

        self.servo_dis_btn = QPushButton("Disable")
        self.servo_dis_btn.setEnabled(False)
        self.servo_dis_btn.clicked.connect(self.servo_disabled)
        button2_layout.addWidget(self.servo_dis_btn)
        
        self.servo_home_btn = QPushButton("Homing")
        self.servo_home_btn.setEnabled(False)
        self.servo_home_btn.clicked.connect(self.servo_home)
        button2_layout.addWidget(self.servo_home_btn)

        self.servo_reset_btn = QPushButton("Reset")
        self.servo_reset_btn.clicked.connect(self.servo_reset)
        button2_layout.addWidget(self.servo_reset_btn)

        servo_layout.addLayout(button2_layout)

        servo_group.setLayout(servo_layout)
        right_layout.addWidget(servo_group) 
        
        # ========== 2. Recording Control ==========
        record_group = QGroupBox("Recording Control")
        record_layout = QVBoxLayout()
        
        # Mode recording
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Record Mode:"))
        
        self.record_mode = QComboBox()
        self.record_mode.addItems(list(self.record_modes.keys()))
        self.record_mode.setCurrentText("0.05s (20Hz)")
        mode_layout.addWidget(self.record_mode)
        mode_layout.addStretch()
        
        record_layout.addLayout(mode_layout)
        
        # Recording buttons
        buttons_layout = QHBoxLayout()
        
        self.record_btn = QPushButton("🔴 Start Recording")
        self.record_btn.setStyleSheet("background-color: red; color: white;")
        self.record_btn.clicked.connect(self.start_recording)
        self.record_btn.setEnabled(False)
        buttons_layout.addWidget(self.record_btn)
        
        self.stop_record_btn = QPushButton("⏹ Stop Recording")
        self.stop_record_btn.clicked.connect(self.stop_recording)
        self.stop_record_btn.setEnabled(False)
        buttons_layout.addWidget(self.stop_record_btn)
        
        record_layout.addLayout(buttons_layout)
        
        # Save and Clear buttons
        save_clear_layout = QHBoxLayout()
        
        self.save_btn = QPushButton("💾 Save Recording")
        self.save_btn.clicked.connect(self.save_recording)
        self.save_btn.setEnabled(False)
        save_clear_layout.addWidget(self.save_btn)
        
        self.clear_btn = QPushButton("🗑 Clear Data")
        self.clear_btn.clicked.connect(self.clear_recording)
        self.clear_btn.setEnabled(False)
        save_clear_layout.addWidget(self.clear_btn)
        
        record_layout.addLayout(save_clear_layout)
        
        # Status
        status_layout = QVBoxLayout()
        
        self.status_label = QLabel("⚪ Not recording")
        self.status_label.setStyleSheet("color: gray; font-weight: bold;")
        status_layout.addWidget(self.status_label)
        
        self.record_counter = QLabel("Recorded: 0")
        self.record_counter.setStyleSheet("color: #888;")
        status_layout.addWidget(self.record_counter)
        
        self.sampling_info = QLabel("Sampling: 20Hz (0.05s)")
        self.sampling_info.setStyleSheet("color: #4a9eff;")
        status_layout.addWidget(self.sampling_info)
        
        record_layout.addLayout(status_layout)
        
        record_group.setLayout(record_layout)
        right_layout.addWidget(record_group)
        
        # ========== 3. Info Panel (Ringkasan) ==========
        
        right_layout.addStretch()
        
        # Tambahkan ke splitter
        top_splitter.addWidget(left_panel)
        top_splitter.addWidget(right_panel)
        top_splitter.setSizes([800, 380])
        
        # ========== BOTTOM SECTION: Tabel Data ==========
        table_group = QGroupBox("Recorded Motion Data")
        table_layout = QVBoxLayout()
        
        self.data_table = QTableWidget()
        self.data_table.setColumnCount(9)
        self.data_table.setHorizontalHeaderLabels([
            "Frame", "Time (s)", "Position Ratio", 
            "LX", "LY", "RY",
            "S1", "S2", "S3"
        ])
        self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.data_table.setAlternatingRowColors(True)
        table_layout.addWidget(self.data_table)
        
        table_group.setLayout(table_layout)
        
        # ========== Gabungkan semua ke main layout ==========
        main_layout.addWidget(top_splitter, 2)  # 2 bagian dari 3 untuk atas
        main_layout.addWidget(table_group, 1)   # 1 bagian dari 3 untuk tabel
        
        # Connect signal untuk update sampling info
        self.record_mode.currentTextChanged.connect(self.update_sampling_info)
        
        # Save status text
        self.status_text = "⚪ Not recording"

    # ========= PLC Conn Functions
    def connect_plc(self):
        """Connect ke PLC dengan setting yang diinput"""
        ip = self.plc_ip_input.text().strip()
        port = self.plc_port_input.value()
        unit_id = self.plc_unit_input.value()
        
        if not ip:
            QMessageBox.warning(self, "Invalid Input", "Please enter IP address")
            return
            
        self.plc_connect_btn.setEnabled(False)
        self.plc_status_label.setText("⏳ Connecting to PLC...")
        self.plc_status_label.setStyleSheet("color: orange; font-weight: bold;")
        
        if self.plc.connect(ip, port, unit_id):
            self.plc_connect_btn.setEnabled(False)
            self.plc_disconnect_btn.setEnabled(True)
            self.update_plc_status_display()
        else:
            self.plc_connect_btn.setEnabled(True)
            self.plc_status_label.setText("✗ Connection failed")
            self.plc_status_label.setStyleSheet("color: red; font-weight: bold;")
            
    def disconnect_plc(self):
        """Disconnect dari PLC"""
        self.plc.disconnect()
        self.plc_connect_btn.setEnabled(True)
        self.plc_disconnect_btn.setEnabled(False)
        self.update_plc_status_display()
        
    def test_plc_connection(self):
        """Test koneksi PLC"""
        ip = self.plc_ip_input.text().strip()
        port = self.plc_port_input.value()
        unit_id = self.plc_unit_input.value()
        
        if not ip:
            QMessageBox.warning(self, "Invalid Input", "Please enter IP address")
            return
            
        self.plc_status_label.setText("⏳ Testing connection...")
        self.plc_status_label.setStyleSheet("color: orange; font-weight: bold;")
        
        # Simpan setting sementara
        temp_plc = self.plc
        
        if temp_plc.connect(ip, port, unit_id):
            self.plc_status_label.setText("✓ Test successful!")
            self.plc_status_label.setStyleSheet("color: green; font-weight: bold;")
            self.plc_detail_label.setText(f"Successfully connected to {ip}:{port}")
            QMessageBox.information(self, "Success", f"PLC connected to {ip}:{port}")
            temp_plc.disconnect()
        else:
            self.plc_status_label.setText("✗ Test failed!")
            self.plc_status_label.setStyleSheet("color: red; font-weight: bold;")
            self.plc_detail_label.setText(f"Cannot connect to {ip}:{port}")
            QMessageBox.warning(self, "Failed", f"Cannot connect to PLC at {ip}:{port}")
            
    def update_plc_status_display(self):
        """Update tampilan status PLC"""
        if self.plc.is_connected:
            self.plc_status_label.setText(f"🟢 PLC: Connected to {self.plc.ip_address}:{self.plc.port}")
            self.plc_status_label.setStyleSheet("color: green; font-weight: bold;")
            self.plc_detail_label.setText(f"Unit ID: {self.plc.unit_id} | Heartbeat OK")
            self.plc_connect_btn.setEnabled(False)
            self.plc_disconnect_btn.setEnabled(True)
        else:
            self.plc_status_label.setText("⚪ PLC: Not Connected")
            self.plc_status_label.setStyleSheet("color: orange; font-weight: bold;")
            self.plc_detail_label.setText("Click 'Connect' to establish connection")
            self.plc_connect_btn.setEnabled(True)
            self.plc_disconnect_btn.setEnabled(False)
            
    def on_plc_connection_changed(self, connected, message):
        """Callback ketika status koneksi PLC berubah"""
        if connected:
            self.plc_status_label.setText(f"🟢 PLC: {message}")
            self.plc_status_label.setStyleSheet("color: green; font-weight: bold;")
            self.plc_detail_label.setText(f"Connected - Unit ID: {self.plc.unit_id}")
        else:
            self.plc_status_label.setText(f"🔴 PLC: {message}")
            self.plc_status_label.setStyleSheet("color: red; font-weight: bold;")
            self.plc_detail_label.setText(message)
            
    def on_plc_safety_changed(self, active):
        """Callback ketika safety status berubah"""
        if active:
            self.plc_safety_label.setText("🔴 Safety: ACTIVE")
            self.plc_safety_label.setStyleSheet("color: red; font-weight: bold;")
            self.plc_detail_label.setText("SAFETY MODE - Servo outputs disabled")
        else:
            self.plc_safety_label.setText("🟢 Safety: Normal")
            self.plc_safety_label.setStyleSheet("color: green; font-weight: bold;")
            
    def on_plc_error(self, error_msg):
        """Callback ketika error PLC terjadi"""
        self.plc_detail_label.setText(f"Error: {error_msg}")
        self.plc_detail_label.setStyleSheet("color: red; font-size: 10px;")
        
    # ========== Video Display Functions ==========
    
    def update_video_display(self, cv_frame):
        """Update tampilan video"""
        if not cv_frame is None:
            height, width, channel = cv_frame.shape
            bytes_per_line = 3 * width
            q_image = QImage(cv_frame.data, width, height, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_image)
            
            scaled = pixmap.scaled(
                self.video_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.video_label.setPixmap(scaled)
            
    def on_position_changed(self, current_frame):
        """Callback ketika posisi frame berubah"""
        if self.total_frames > 0:
            current_time = current_frame / self.fps if self.fps > 0 else 0
            
            # Update slider
            position = (current_frame / self.total_frames) * 100
            self.slider.blockSignals(True)
            self.slider.setValue(int(position))
            self.slider.blockSignals(False)
            
            # Update time label
            current_qtime = QTime(0, 0, 0).addSecs(int(current_time))
            total_time = QTime(0, 0, 0).addSecs(int(self.total_frames / self.fps))
            self.time_label.setText(
                f"{current_qtime.toString('mm:ss')} / {total_time.toString('mm:ss')}"
            )
            self.frame_label.setText(f"Frame: {current_frame} / {self.total_frames}")
            self.time_display.setText(f"Time: {current_time:.3f}s")
            
            # if self.is_playing and self.servo_enabled_status:
            #     # Gunakan nilai joystick terakhir
            #     lx = self.last_joystick_lx
            #     ly = self.last_joystick_ly
            #     ry = self.last_joystick_ry
                
            #     # Compute servo positions
            #     s1, s2, s3 = self.compute_servo_from_joystick(lx, ly, ry)
                
            #     # Kirim ke PLC
            #     if self.plc and self.plc.is_connected:
            #         self.servo.write_writepos([s1, s2, s3])
            #         self.servo.run()
            
            # Record jika sedang recording
            if self.is_recording:
                self.record_current_position(current_frame, current_time)
                
    # ========== Joystick Functions ==========
    
    def refresh_joystick_list(self):
        """Refresh daftar joystick yang tersedia"""
        self.joystick_combo.clear()
        self.joystick_combo.addItem("No Joystick", -1)
        
        joysticks = self.joystick.get_available_joysticks()
        
        for joy in joysticks:
            self.joystick_combo.addItem(
                f"{joy['name']} (ID:{joy['id']}, Axes:{joy['axes']}, Buttons:{joy['buttons']})", 
                joy['id']
            )
            
    def on_deadzone_changed(self, value):
        """Callback ketika deadzone berubah"""
        self.joystick.set_deadzone(value)
        
    def connect_joystick(self):
        """Connect ke joystick yang dipilih"""
        joy_id = self.joystick_combo.currentData()
        
        if joy_id >= 0:
            if self.joystick.connect_joystick(joy_id):
                self.connect_joystick_btn.setEnabled(False)
                self.disconnect_joystick_btn.setEnabled(True)
                self.joystick_enabled = True
                
                info = self.joystick.get_joystick_info()
                if info:
                    self.joystick_info_label.setText(f"Joystick: {info['name']}")
                    QMessageBox.information(self, "Success", 
                        f"Joystick connected!\n\n"
                        f"Name: {info['name']}\n"
                        f"Axes: {info['axes']}\n"
                        f"Buttons: {info['buttons']}\n\n"
                        f"Move the joystick to see values change.")
            else:
                QMessageBox.warning(self, "Error", "Failed to connect joystick!")
        else:
            QMessageBox.warning(self, "Warning", "Please select a joystick first!")
            
    def disconnect_joystick(self):
        """Disconnect joystick"""
        self.joystick.disconnect_joystick()
        self.connect_joystick_btn.setEnabled(True)
        self.disconnect_joystick_btn.setEnabled(False)
        self.joystick_enabled = False
        self.joystick_info_label.setText("Joystick: Not connected")
        
        # Reset displays
        self.lx_value.setText("0.000")
        self.ly_value.setText("0.000")
        self.ry_value.setText("0.000")
        
        # Reset colors
        for label in [self.lx_value, self.ly_value, self.ry_value]:
            label.setStyleSheet("color: #888888; font-family: monospace; font-weight: bold; font-size: 14px;")
            
    def on_joystick_connection(self, connected):
        """Callback ketika joystick terhubung/terputus"""
        if connected:
            info = self.joystick.get_joystick_info()
            if info:
                self.joystick_status.setText(f"🟢 Connected: {info['name']}")
                self.joystick_status.setStyleSheet("color: green; font-weight: bold;")
                self.joystick_info_label.setText(f"Joystick: {info['name']}")
            else:
                self.joystick_status.setText("🟢 Connected")
                self.joystick_status.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.joystick_status.setText("⚪ Not Connected")
            self.joystick_status.setStyleSheet("color: gray; font-weight: bold;")
            self.joystick_info_label.setText("Joystick: Not connected")
            
    def on_joystick_moved(self, lx, ly, ry):
        """Callback ketika joystick digerakkan"""
        # Simpan nilai terakhir
        self.last_joystick_lx = lx
        self.last_joystick_ly = ly
        self.last_joystick_ry = ry
        
        # Update display
        self.lx_value.setText(f"{lx:+.3f}")
        self.ly_value.setText(f"{ly:+.3f}")
        self.ry_value.setText(f"{ry:+.3f}")
        
        # Update warna berdasarkan nilai
        self.update_joystick_color(self.lx_value, lx)
        self.update_joystick_color(self.ly_value, ly)
        self.update_joystick_color(self.ry_value, ry)
        
    def on_joystick_button(self, button_id):
        """Callback ketika tombol joystick ditekan"""
        self.status_label.setText(f"🎮 Button {button_id} pressed")
        QTimer.singleShot(1000, lambda: self.status_label.setText(self.status_text))
        
    def update_joystick_color(self, label, value):
        """Update warna label joystick berdasarkan nilai"""
        abs_val = abs(value)
        if abs_val > 0.8:
            label.setStyleSheet("color: #ff6666; font-family: monospace; font-weight: bold; font-size: 14px;")
        elif abs_val > 0.5:
            label.setStyleSheet("color: #ffaa66; font-family: monospace; font-weight: bold; font-size: 14px;")
        elif abs_val > 0.2:
            label.setStyleSheet("color: #ffff66; font-family: monospace; font-weight: bold; font-size: 14px;")
        elif abs_val > 0.05:
            label.setStyleSheet("color: #aaff66; font-family: monospace; font-weight: bold; font-size: 14px;")
        else:
            label.setStyleSheet("color: #888888; font-family: monospace; font-weight: bold; font-size: 14px;")
            
    def compute_servo_from_joystick(self, lx, ly, ry):
        """
        Hitung posisi servo dari input joystick
        Formula: roll = lx, pitch = -ly, heave = -ry
        """
        roll = lx
        pitch = -ly
        heave = -ry
        
        s1 = heave - pitch + roll
        s2 = heave - pitch - roll
        s3 = heave + pitch
        
        # Clamp ke range -1 sampai 1
        s1 = max(-1, min(1, s1))
        s2 = max(-1, min(1, s2))
        s3 = max(-1, min(1, s3))
        
        # Convert ke servo range 0-1000
        s1 = int((s1 + 1) * 500)
        s2 = int((s2 + 1) * 500)
        s3 = int((s3 + 1) * 500)
        
        return s1, s2, s3
        
    # ========== Video Functions ==========
    
    def load_video(self):
        """Load video file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Video for Recording", "",
            "Video Files (*.mp4 *.avi *.mov *.mkv *.flv *.wmv)"
        )
        
        if file_path:
            self.is_loading = True
            self.load_btn.setEnabled(False)
            self.loading_bar.setVisible(True)
            self.info_label.setText("Loading video...")
            self.video_info_label.setText(f"Video: Loading...")
            
            self.record_thread.load_video(file_path)
            
            if not self.record_thread.isRunning():
                self.record_thread.start()
                
    def on_video_loaded(self, video_info):
        """Callback ketika video selesai di-load"""
        self.is_loading = False
        self.load_btn.setEnabled(True)
        self.loading_bar.setVisible(False)
        
        self.total_frames = video_info['total_frames']
        self.fps = video_info['fps']
        self.video_loaded = True
        
        file_name = os.path.basename(video_info['path'])
        self.info_label.setText(
            f"Loaded: {file_name} | Duration: {video_info['duration']:.2f}s | FPS: {self.fps:.1f}"
        )
        self.video_info_label.setText(f"Video: {file_name} ({video_info['duration']:.1f}s, {self.fps:.0f}fps)")
        
        # Enable controls
        self.play_btn.setEnabled(True)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.slider.setEnabled(True)
        self.record_btn.setEnabled(True)
        
        self.update_sampling_info()
        
    def on_loading_error(self, error_msg):
        """Callback error loading"""
        self.is_loading = False
        self.load_btn.setEnabled(True)
        self.loading_bar.setVisible(False)
        self.info_label.setText("Error loading video")
        self.video_info_label.setText("Video: Error loading")
        QMessageBox.critical(self, "Error", f"Failed to load video:\n{error_msg}")
        
    def on_video_ended(self):
        """Callback video selesai"""
        self.is_playing = False
        self.info_label.setText("Video ended")
        
        if self.is_recording:
            self.stop_recording()
            QMessageBox.information(self, "Recording", "Video ended. Recording stopped.")
        
    def play_video(self):
        """Play video"""
        if self.video_loaded:
            self.is_playing = True
            self.record_thread.play()
            
    def pause_video(self):
        """Pause video"""
        if self.video_loaded:
            self.is_playing = False
            self.record_thread.pause()
            
    def stop_video(self):
        """Stop video"""
        if self.video_loaded:
            self.is_playing = False
            self.record_thread.stop()
            
    def slider_pressed(self):
        """Slider ditekan"""
        if self.is_playing:
            self.is_playing = False
            self.record_thread.pause()
        
    def slider_released(self):
        """Slider dilepas"""
        if self.video_loaded:
            value = self.slider.value()
            self.record_thread.seek(value)
            self.last_recorded_timestamp = -1
            
    def slider_value_changed(self, value):
        """Value slider berubah"""
        if self.video_loaded and self.total_frames > 0:
            frame_pos = int((value / 100.0) * self.total_frames)
            current_time = frame_pos / self.fps if self.fps > 0 else 0
            self.time_display.setText(f"Time: {current_time:.3f}s")
            
    # ========== Recording Functions ==========
    
    def update_sampling_info(self):
        """Update sampling info display"""
        mode = self.record_mode.currentText()
        if mode == "Every Frame":
            self.sampling_info.setText(f"Sampling: Every Frame (~{self.fps:.0f}Hz)")
        else:
            interval = self.record_modes[mode]
            freq = 1.0 / interval
            self.sampling_info.setText(f"Sampling: {freq:.0f}Hz ({interval}s)")
            
    def record_current_position(self, current_frame, current_time):
        """Record posisi saat ini dengan mengambil nilai joystick terakhir"""
        mode = self.record_mode.currentText()
        
        # Tentukan interval
        if mode == "Every Frame":
            should_record = True
        else:
            interval = self.record_modes[mode]
            if self.last_recorded_timestamp < 0:
                should_record = True
            else:
                time_since_last = current_time - self.last_recorded_timestamp
                should_record = time_since_last >= interval
                
        if should_record:
            # Gunakan nilai joystick terakhir yang tersimpan
            lx = self.last_joystick_lx
            ly = self.last_joystick_ly
            ry = self.last_joystick_ry
            
            # Compute servo positions
            s1, s2, s3 = self.compute_servo_from_joystick(lx, ly, ry)
            
            position_ratio = current_frame / self.total_frames if self.total_frames > 0 else 0
            
            record = {
                'frame': current_frame,
                'video_timestamp': current_time,
                'position_ratio': position_ratio,
                'system_timestamp': datetime.now().strftime("%H:%M:%S.%f")[:-3],
                'joystick': {
                    'lx': lx,
                    'ly': ly,
                    'ry': ry
                },
                'servo_computed': {
                    'servo1': s1,
                    'servo2': s2,
                    'servo3': s3
                }
            }
            
            self.recorded_data.append(record)
            self.last_recorded_timestamp = current_time
            
            # Update UI
            self.record_counter.setText(f"Recorded: {len(self.recorded_data)}")
            self.add_record_to_table(record)
            self.position_recorded.emit(record)
            
    def add_record_to_table(self, record):
        """Tambahkan record ke tabel"""
        row = self.data_table.rowCount()
        self.data_table.insertRow(row)
        
        # Frame dan time
        frame_item = QTableWidgetItem(str(record['frame']))
        time_item = QTableWidgetItem(f"{record['video_timestamp']:.3f}")
        ratio_item = QTableWidgetItem(f"{record['position_ratio']:.6f}")
        
        # Joystick values
        lx_item = QTableWidgetItem(f"{record['joystick']['lx']:+.3f}")
        ly_item = QTableWidgetItem(f"{record['joystick']['ly']:+.3f}")
        ry_item = QTableWidgetItem(f"{record['joystick']['ry']:+.3f}")
        
        # Servo values
        s1_item = QTableWidgetItem(str(record['servo_computed']['servo1']))
        s2_item = QTableWidgetItem(str(record['servo_computed']['servo2']))
        s3_item = QTableWidgetItem(str(record['servo_computed']['servo3']))
        
        # Set alignment
        for item in [frame_item, time_item, ratio_item, lx_item, ly_item, ry_item, 
                     s1_item, s2_item, s3_item]:
            item.setTextAlignment(Qt.AlignCenter)
            
        self.data_table.setItem(row, 0, frame_item)
        self.data_table.setItem(row, 1, time_item)
        self.data_table.setItem(row, 2, ratio_item)
        self.data_table.setItem(row, 3, lx_item)
        self.data_table.setItem(row, 4, ly_item)
        self.data_table.setItem(row, 5, ry_item)
        self.data_table.setItem(row, 6, s1_item)
        self.data_table.setItem(row, 7, s2_item)
        self.data_table.setItem(row, 8, s3_item)
        
        self.data_table.scrollToBottom()
        
    def start_recording(self):
        """Mulai recording"""
        if not self.video_loaded:
            QMessageBox.warning(self, "Warning", "Please load a video first!")
            return
            
        if not self.joystick_enabled:
            reply = QMessageBox.question(
                self, "No Joystick",
                "Joystick is not connected. Continue recording without joystick?\n"
                "This will record zero values for joystick positions.",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
                
        self.clear_recording()
        self.is_recording = True
        self.last_recorded_timestamp = -1
        
        self.record_btn.setEnabled(False)
        self.stop_record_btn.setEnabled(True)
        self.save_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.record_mode.setEnabled(False)
        
        mode = self.record_mode.currentText()
        self.status_text = "🔴 RECORDING..."
        self.status_label.setText(self.status_text)
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        self.recording_info_label.setText(f"Recording: Active ({mode})")
        
        QMessageBox.information(
            self, "Recording Started",
            f"Recording started!\n\n"
            f"Mode: {mode}\n"
            f"Joystick: {'Connected' if self.joystick_enabled else 'Not connected'}\n\n"
            "1. Click PLAY to start the video\n"
            "2. Move the joystick to record positions\n"
            "3. Click STOP RECORDING when finished"
        )
        
    def stop_recording(self):
        """Stop recording"""
        self.is_recording = False
        
        self.record_btn.setEnabled(True)
        self.stop_record_btn.setEnabled(False)
        self.save_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.record_mode.setEnabled(True)
        
        total = len(self.recorded_data)
        if total > 0:
            duration = self.recorded_data[-1]['video_timestamp'] - self.recorded_data[0]['video_timestamp']
            self.status_text = f"✅ Recording stopped - {total} positions recorded ({duration:.2f}s)"
            self.recording_info_label.setText(f"Recording: Stopped ({total} records, {duration:.1f}s)")
        else:
            self.status_text = "✅ Recording stopped - No data recorded"
            self.recording_info_label.setText("Recording: Stopped (no data)")
        self.status_label.setText(self.status_text)
        self.status_label.setStyleSheet("color: green; font-weight: bold;")
        
    def clear_recording(self):
        """Clear semua data recording"""
        self.recorded_data = []
        self.last_recorded_timestamp = -1
        self.data_table.setRowCount(0)
        self.record_counter.setText("Recorded: 0")
        self.save_btn.setEnabled(False)
        self.recording_info_label.setText("Recording: Not started")
        
    def save_recording(self):
        """Save recording ke file JSON"""
        if not self.recorded_data:
            QMessageBox.warning(self, "Warning", "No recorded data to save!")
            return
        
        # mendapatkan nama file video
        if self.record_thread.video_path:
            video_name = os.path.basename(self.record_thread.video_path)
            # Ekstensi video yang umum
            video_extensions = ('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.mpeg', '.mpg')
            
            if video_name.endswith(video_extensions):
                # Hapus ekstensi
                video_name = video_name[:-4]
        else:
            video_name = "Video_Animasi"
            
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Recording",
            f"{video_name}_motion_recording",
            "JSON Files (*.json)"
        )
        
        if file_path:
            try:
                video_info = {
                    'file_name': os.path.basename(self.record_thread.video_path) if self.record_thread.video_path else None,
                    'total_frames': self.total_frames,
                    'fps': self.fps,
                    'duration': self.total_frames / self.fps if self.fps > 0 else 0
                }
                
                # Hitung statistik
                total_duration = 0
                if self.recorded_data:
                    total_duration = self.recorded_data[-1]['video_timestamp'] - self.recorded_data[0]['video_timestamp']
                
                data = {
                    'version': '1.0',
                    'type': 'joystick_motion_recording',
                    'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'video_info': video_info,
                    'joystick_info': {
                        'connected': self.joystick_enabled,
                        'info': self.joystick.get_joystick_info() if self.joystick_enabled else None
                    },
                    'recording_config': {
                        'mode': self.record_mode.currentText(),
                        'total_records': len(self.recorded_data),
                        'duration': total_duration,
                        'fps': self.fps
                    },
                    'kinematics_formula': {
                        'roll': 'lx',
                        'pitch': '-ly',
                        'heave': '-ry',
                        's1': 'heave - pitch + roll',
                        's2': 'heave - pitch - roll',
                        's3': 'heave + pitch',
                        'output_range': '0-1000 (0=min, 500=neutral, 1000=max)'
                    },
                    'motion_data': self.recorded_data
                }
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    
                QMessageBox.information(self, "Success", 
                    f"Recording saved to:\n{file_path}\n\n"
                    f"Total records: {len(self.recorded_data)}\n"
                    f"Duration: {total_duration:.2f}s")
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    # ================= Servo Control =================
    def servo_enabled(self):
        """Enable servo"""
        print("=" * 50)
        print("ENABLE SERVO BUTTON PRESSED")
        print(f"PLC Connected: {self.plc.is_connected if self.plc else False}")
        print(f"Safety Active: {self.plc.safety_active if self.plc else False}")
        print("=" * 50)
        
        if not self.plc or not self.plc.is_connected:
            QMessageBox.warning(self, "Error", "PLC not connected!")
            return
            
        result = self.servo.en_servo()
        
        if result:
            self.servo_dis_btn.setEnabled(True)
            self.servo_home_btn.setEnabled(True)
            self.servo_reset_btn.setEnabled(True)
            self.servo_en_btn.setEnabled(False)
            self.servo_enabled_status = True  # Set flag enabled
            
            self.status_servo_label.setText("🟢 Servo Enabled")
            self.status_servo_label.setStyleSheet("color: green; font-weight: bold;")
            print("✓ Servo enabled successfully")
            
            # Mulai timer untuk update posisi (opsional)
            self.start_position_update_timer()
        else:
            self.status_servo_label.setText("❌ Enable Failed")
            self.status_servo_label.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.warning(self, "Error", "Failed to enable servo!\nCheck PLC connection.")
            print("✗ Servo enable failed")

    def servo_disabled(self):
        """Disable servo"""
        print("=" * 50)
        print("DISABLE SERVO BUTTON PRESSED")
        print("=" * 50)
        
        if not self.plc or not self.plc.is_connected:
            QMessageBox.warning(self, "Error", "PLC not connected!")
            return
            
        result = self.servo.disable_servo()
        
        if result:
            self.servo_dis_btn.setEnabled(False)
            self.servo_home_btn.setEnabled(False)
            self.servo_reset_btn.setEnabled(False)
            self.servo_en_btn.setEnabled(True)
            self.servo_enabled_status = False  # Clear flag
            
            self.status_servo_label.setText("🔴 Servo Disabled")
            self.status_servo_label.setStyleSheet("color: red; font-weight: bold;")
            
            # Stop timer update posisi
            self.stop_position_update_timer()
            print("✓ Servo disabled successfully")
        else:
            self.status_servo_label.setText("❌ Disable Failed")
            self.status_servo_label.setStyleSheet("color: red; font-weight: bold;")
            print("✗ Servo disable failed")

    def start_position_update_timer(self):
        """Start timer untuk update posisi ke PLC"""
        if hasattr(self, 'position_timer') and self.position_timer.isActive():
            self.position_timer.stop()
            
        self.position_timer = QTimer()
        self.position_timer.timeout.connect(self.update_position_to_plc)
        self.position_timer.start(50)  # 20Hz update rate (50ms)
        print("✓ Position update timer started (20Hz)")

    def stop_position_update_timer(self):
        """Stop timer update posisi"""
        if hasattr(self, 'position_timer'):
            self.position_timer.stop()
            print("✓ Position update timer stopped")

    def update_position_to_plc(self):
        """Update posisi ke PLC (dipanggil timer)"""
        if not self.plc or not self.plc.is_connected:
            return
            
        if not self.servo_enabled_status:
            return
            
        # Gunakan nilai joystick terakhir
        lx = self.last_joystick_lx
        ly = self.last_joystick_ly
        ry = self.last_joystick_ry
        
        # Compute servo positions
        s1, s2, s3 = self.compute_servo_from_joystick(lx, ly, ry)
        
        # Kirim ke PLC (konversi ke float)
        try:
            self.servo.write_writepos([float(s1), float(s2), float(s3)])
        except Exception as e:
            print(f"Error sending position to PLC: {e}")

    def servo_home(self):
        """Home servo"""
        print("=" * 50)
        print("HOME SERVO BUTTON PRESSED")
        print("=" * 50)
        
        # Disable tombol home sementara
        self.servo_home_btn.setEnabled(False)
        self.status_servo_label.setText("🏠 Homing in progress...")
        self.status_servo_label.setStyleSheet("color: orange; font-weight: bold;")
        
        # Kirim perintah homing
        result = self.servo.homing()
        
        if result:
            print("✓ Homing command sent")
            self.status_servo_label.setText("🏠 Homing command sent")
            
            # Timer untuk cek status homing
            self.homing_check_timer = QTimer()
            self.homing_check_timer.timeout.connect(self.check_homing_status)
            self.homing_check_timer.start(500)  # Cek setiap 500ms
            
            QMessageBox.information(self, "Homing", "Homing command sent!\nWaiting for completion...")
        else:
            self.servo_home_btn.setEnabled(True)
            self.status_servo_label.setText("❌ Homing Failed")
            self.status_servo_label.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.warning(self, "Error", "Failed to send homing command!")
            
    def check_homing_status(self):
        """Cek status homing dari PLC"""
        # Baca status homed dari PLC
        homed = self.servo.read_home_status()
        
        if homed is not None and homed:
            # Homing selesai
            self.homing_check_timer.stop()
            self.servo_home_btn.setEnabled(True)
            self.status_servo_label.setText("✅ Homing Completed!")
            self.status_servo_label.setStyleSheet("color: green; font-weight: bold;")
            QMessageBox.information(self, "Homing", "Homing completed successfully!")
        elif homed is False:
            # Masih dalam proses
            pass
        else:
            # Error membaca status
            self.homing_check_timer.stop()
            self.servo_home_btn.setEnabled(True)
            self.status_servo_label.setText("⚠️ Cannot read homing status")
            self.status_servo_label.setStyleSheet("color: orange; font-weight: bold;")
            
    def servo_reset(self):
        """Reset servo"""
        print("=" * 50)
        print("RESET SERVO BUTTON PRESSED")
        print("=" * 50)
        
        # Konfirmasi reset
        reply = QMessageBox.question(
            self,
            "Reset Servo",
            "Are you sure you want to reset the servo?\n\n"
            "This will clear any errors and reset the system.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Disable tombol reset sementara
            self.servo_reset_btn.setEnabled(False)
            self.status_servo_label.setText("🔄 Resetting...")
            self.status_servo_label.setStyleSheet("color: orange; font-weight: bold;")
            
            # Kirim perintah reset
            result = self.servo.reset()
            
            if result:
                print("✓ Reset command sent")
                self.status_servo_label.setText("✅ Reset command sent")
                
                # Timer untuk enable kembali tombol
                QTimer.singleShot(2000, self.reset_complete)
                
                QMessageBox.information(self, "Reset", "Reset command sent!\nSystem will reset in 2 seconds.")
            else:
                self.servo_reset_btn.setEnabled(True)
                self.status_servo_label.setText("❌ Reset Failed")
                self.status_servo_label.setStyleSheet("color: red; font-weight: bold;")
                QMessageBox.warning(self, "Error", "Failed to send reset command!")
                
    def reset_complete(self):
        """Reset complete - re-enable buttons"""
        self.servo_reset_btn.setEnabled(True)
        self.status_servo_label.setText("🟢 Servo Enabled")
        self.status_servo_label.setStyleSheet("color: green; font-weight: bold;")
        
    def update_servo_status(self):
        """Update status servo secara periodik"""
        if hasattr(self, 'status_update_timer'):
            self.status_update_timer.stop()
            
        self.status_update_timer = QTimer()
        self.status_update_timer.timeout.connect(self._update_servo_status)
        self.status_update_timer.start(1000)  # Update setiap 1 detik
        
    def _update_servo_status(self):
        """Internal: update status servo"""
        if not self.plc or not self.plc.is_connected:
            return
            
        # Baca status enable
        enabled = self.servo.read_enable_status()
        if enabled is not None:
            if enabled:
                self.servo_en_btn.setEnabled(False)
                self.servo_dis_btn.setEnabled(True)
                self.servo_home_btn.setEnabled(True)
                self.servo_reset_btn.setEnabled(True)
                self.status_servo_label.setText("🟢 Servo Enabled")
                self.status_servo_label.setStyleSheet("color: green; font-weight: bold;")
            else:
                self.servo_en_btn.setEnabled(True)
                self.servo_dis_btn.setEnabled(False)
                self.servo_home_btn.setEnabled(False)
                self.servo_reset_btn.setEnabled(False)
                self.status_servo_label.setText("🔴 Servo Disabled")
                self.status_servo_label.setStyleSheet("color: red; font-weight: bold;")