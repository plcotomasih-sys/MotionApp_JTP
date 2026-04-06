# video_player_tab.py
import os
import json
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QSlider, QLabel, QFileDialog, QMessageBox, QProgressBar)
from PySide6.QtCore import Qt, QTime, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from plc_data_sender import PLCDataSender

class VideoPlayerTab(QWidget):
    # Tambahkan signal untuk mengirim data servo ke komponen lain
    servo_data_ready = Signal(dict)  # Signal untuk mengirim data servo ke PLC
    
    def __init__(self, video_thread, plc_connection):
        super().__init__()
        self.video_thread = video_thread
        self.plc_connection = plc_connection
        self.is_playing = False
        self.total_frames = 0
        self.fps = 30
        self.video_loaded = False
        self.is_seeking = False
        self.seek_timer = QTimer()
        self.seek_timer.setSingleShot(True)
        self.seek_timer.timeout.connect(self.perform_seek)
        self.pending_seek_value = 0

        # Inisialisasi PLC data sender
        self.plc_sender = PLCDataSender(plc_connection)

        # Connect signals dari PLC sender
        self.plc_sender.data_sent.connect(self.on_plc_data_sent)
        self.plc_sender.data_failed.connect(self.on_plc_data_failed)
        self.plc_sender.connection_error.connect(self.on_plc_connection_error)
        
        # Data motion recording
        self.motion_data = []
        self.motion_data_dict_by_frame = {}
        self.motion_data_dict_by_timestamp = {}
        self.current_motion_data = None
        self.motion_data_loaded = False
        
        # Informasi tambahan dari JSON
        self.video_info = {}
        self.joystick_info = {}
        self.recording_config = {}
        self.kinematics_formula = {}
        
        # ready State
        self.is_servo_ready = False
        
        # Connect signals dari video thread
        self.video_thread.frame_ready.connect(self.update_video_display)
        self.video_thread.position_changed.connect(self.update_position)
        self.video_thread.video_ended.connect(self.on_video_end)
        self.video_thread.video_loaded.connect(self.on_video_loaded)
        self.video_thread.loading_error.connect(self.on_loading_error)
        
        # Setup UI
        self.setup_ui()
        
    def setup_ui(self):
        """Setup user interface untuk video player"""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Video display area
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("""
            background-color: black;
            border: 2px solid #444;
            border-radius: 5px;
        """)
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setText("No Video Loaded\n\nClick 'Load Video' to Load Video and Motion Data")
        layout.addWidget(self.video_label)
        
        # Loading indicator
        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setVisible(False)
        self.loading_bar.setMaximumHeight(3)
        layout.addWidget(self.loading_bar)
        
        # Control buttons
        controls_layout = QHBoxLayout()
        
        self.servo_home_btn = QPushButton("⚙️ Homing Servo")
        self.servo_home_btn.clicked.connect(self.home_servo)
        self.servo_home_btn.setEnabled(False)
        controls_layout.addWidget(self.servo_home_btn)
        
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.clicked.connect(self.play_video)
        self.play_btn.setEnabled(False)
        controls_layout.addWidget(self.play_btn)
        
        self.pause_btn = QPushButton("⏸ Pause")
        self.pause_btn.clicked.connect(self.pause_video)
        self.pause_btn.setEnabled(False)
        controls_layout.addWidget(self.pause_btn)
        
        self.stop_btn = QPushButton("■ Stop")
        self.stop_btn.clicked.connect(self.stop_video)
        self.stop_btn.setEnabled(False)
        controls_layout.addWidget(self.stop_btn)
        
        self.load_btn = QPushButton("📂 Load Video")
        self.load_btn.clicked.connect(self.load_video)
        controls_layout.addWidget(self.load_btn)
        
        layout.addLayout(controls_layout)
        
        # Progress slider
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
        
        layout.addLayout(slider_layout)
        
        # Info panel
        info_layout = QHBoxLayout()
        
        self.info_label = QLabel("No video loaded")
        self.info_label.setStyleSheet("color: #888;")
        info_layout.addWidget(self.info_label)
        
        self.frame_label = QLabel("Frame: 0 / 0")
        self.frame_label.setStyleSheet("color: #888;")
        info_layout.addWidget(self.frame_label)
        
        # Tambahkan label untuk menampilkan data servo
        self.servo_label = QLabel("Servo: - / - / -")
        self.servo_label.setStyleSheet("color: #888;")
        info_layout.addWidget(self.servo_label)
        
        layout.addLayout(info_layout)

    def on_plc_data_sent(self, data):
        """Callback ketika data berhasil dikirim ke PLC"""
        # Optional: Update UI atau log
        pass

    def on_plc_data_failed(self, error_msg):
        """Callback ketika gagal mengirim data ke PLC"""
        print(f"PLC send failed: {error_msg}")
        # Optional: Tampilkan warning di UI
        self.servo_label.setStyleSheet("color: orange;")
        QTimer.singleShot(2000, lambda: self.servo_label.setStyleSheet("color: #888;"))

    def on_plc_connection_error(self, error_msg):
        """Callback ketika error koneksi PLC"""
        print(f"PLC connection error: {error_msg}")
        self.servo_label.setText("PLC Error!")
        self.servo_label.setStyleSheet("color: red;")

    def load_motion_data(self, video_path):
        """Load motion data dari file JSON yang sesuai dengan video"""
        # Buat path untuk file JSON
        base_path = os.path.splitext(video_path)[0]
        json_path = f"{base_path}_motion_recording.json"
        
        # Cek apakah file JSON ada
        if not os.path.exists(json_path):
            error_msg = f"Motion data file not found:\n{json_path}\n\nPlease ensure the JSON file exists."
            self.on_loading_error(error_msg)
            self.play_btn.setEnabled(False)
            return False
        
        try:
            # Load file JSON
            with open(json_path, 'r') as f:
                json_data = json.load(f)
            
            # Cek struktur JSON
            if isinstance(json_data, list):
                # Jika langsung list (format lama)
                self.motion_data = json_data
            elif isinstance(json_data, dict):
                # Jika dictionary dengan key 'motion_data' (format baru)
                if 'motion_data' in json_data:
                    self.motion_data = json_data['motion_data']
                    print(f"JSON Version: {json_data.get('version', 'unknown')}")
                    print(f"Recording type: {json_data.get('type', 'unknown')}")
                    print(f"Created at: {json_data.get('created_at', 'unknown')}")
                    
                    # Simpan informasi tambahan
                    self.video_info = json_data.get('video_info', {})
                    self.joystick_info = json_data.get('joystick_info', {})
                    self.recording_config = json_data.get('recording_config', {})
                    self.kinematics_formula = json_data.get('kinematics_formula', {})
                    
                    # Validasi video info
                    if self.video_info:
                        print(f"Video info: {self.video_info.get('file_name')}")
                        print(f"Expected total frames: {self.video_info.get('total_frames')}")
                        print(f"Expected FPS: {self.video_info.get('fps')}")
                else:
                    error_msg = "Invalid JSON format. Expected 'motion_data' key in JSON object."
                    self.on_loading_error(error_msg)
                    return False
            else:
                error_msg = f"Invalid JSON format. Expected list or dict, got {type(json_data)}"
                self.on_loading_error(error_msg)
                return False
            
            # Pastikan motion_data adalah list
            if not isinstance(self.motion_data, list):
                error_msg = "Invalid motion data format. Expected a list of data points."
                self.on_loading_error(error_msg)
                return False
            
            # Cek apakah motion_data kosong
            if len(self.motion_data) == 0:
                error_msg = "Motion data is empty."
                self.on_loading_error(error_msg)
                return False
            
            # Buat dictionary untuk akses cepat berdasarkan frame dan timestamp
            self.motion_data_dict_by_frame = {}
            self.motion_data_dict_by_timestamp = {}
            
            for data_point in self.motion_data:
                frame = data_point.get('frame')
                timestamp = data_point.get('video_timestamp')
                
                if frame is not None:
                    self.motion_data_dict_by_frame[frame] = data_point
                if timestamp is not None:
                    self.motion_data_dict_by_timestamp[timestamp] = data_point
            
            self.motion_data_loaded = True
            
            # Validasi data
            if self.motion_data_dict_by_frame:
                frames = sorted(self.motion_data_dict_by_frame.keys())
                timestamps = sorted(self.motion_data_dict_by_timestamp.keys())
                
                # Tampilkan informasi jumlah data
                motion_info = (
                    f"Motion data: {len(self.motion_data)} points | "
                    f"Frame range: {frames[0]}-{frames[-1]} | "
                    f"Duration: {timestamps[-1]:.2f}s"
                )
                
                # Update info label
                current_text = self.info_label.text()
                if "No video loaded" in current_text:
                    self.info_label.setText(motion_info)
                else:
                    self.info_label.setText(f"{self.info_label.text()} | {motion_info}")
                
                print(f"✓ Motion data loaded successfully:")
                print(f"  - Total points: {len(self.motion_data)}")
                print(f"  - Frame range: {frames[0]} to {frames[-1]}")
                print(f"  - Timestamp range: {timestamps[0]:.2f}s to {timestamps[-1]:.2f}s")
                
                # Debug: tampilkan beberapa data pertama
                if len(self.motion_data) > 0:
                    print(f"  - First data point: Frame {self.motion_data[0].get('frame')}, "
                        f"Timestamp {self.motion_data[0].get('video_timestamp'):.2f}s")
                if len(self.motion_data) > 1:
                    print(f"  - Last data point: Frame {self.motion_data[-1].get('frame')}, "
                        f"Timestamp {self.motion_data[-1].get('video_timestamp'):.2f}s")
            
            self.play_btn.setEnabled(True)
            
            return True
            
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON format:\n{e}\n\nPlease check the JSON file structure."
            self.on_loading_error(error_msg)
            return False
        except KeyError as e:
            error_msg = f"Missing required key in JSON:\n{e}"
            self.on_loading_error(error_msg)
            return False
        except Exception as e:
            error_msg = f"Failed to load motion data:\n{e}"
            self.on_loading_error(error_msg)
            return False
    
    def get_servo_data_for_frame(self, current_frame):
        """Dapatkan data servo berdasarkan frame saat ini dengan interpolasi"""
        if not self.motion_data_loaded or not self.motion_data_dict_by_frame:
            return None
        
        # Dapatkan semua frame yang tersedia
        available_frames = sorted(self.motion_data_dict_by_frame.keys())
        
        # Cari frame terdekat
        if current_frame <= available_frames[0]:
            # Sebelum data pertama, gunakan data pertama
            return self.motion_data_dict_by_frame[available_frames[0]]
        elif current_frame >= available_frames[-1]:
            # Setelah data terakhir, gunakan data terakhir
            return self.motion_data_dict_by_frame[available_frames[-1]]
        
        # Cari frame sebelum dan sesudah untuk interpolasi
        prev_frame = None
        next_frame = None
        
        for frame in available_frames:
            if frame <= current_frame:
                prev_frame = frame
            if frame >= current_frame and next_frame is None:
                next_frame = frame
        
        # Jika ditemukan data yang tepat
        if prev_frame == current_frame:
            return self.motion_data_dict_by_frame[current_frame]
        
        # Jika tidak ada data tepat, lakukan interpolasi linear
        if prev_frame is not None and next_frame is not None:
            prev_data = self.motion_data_dict_by_frame[prev_frame]
            next_data = self.motion_data_dict_by_frame[next_frame]
            
            # Hitung faktor interpolasi
            factor = (current_frame - prev_frame) / (next_frame - prev_frame)
            
            # Interpolasi servo values
            prev_servo = prev_data.get('servo_computed', {})
            next_servo = next_data.get('servo_computed', {})
            
            interpolated_servo = {
                'servo1': int(prev_servo.get('servo1', 500) + 
                            (next_servo.get('servo1', 500) - prev_servo.get('servo1', 500)) * factor),
                'servo2': int(prev_servo.get('servo2', 500) + 
                            (next_servo.get('servo2', 500) - prev_servo.get('servo2', 500)) * factor),
                'servo3': int(prev_servo.get('servo3', 500) + 
                            (next_servo.get('servo3', 500) - prev_servo.get('servo3', 500)) * factor)
            }
            
            # Buat data interpolasi
            interpolated_data = {
                'frame': current_frame,
                'video_timestamp': current_frame / self.fps if self.fps > 0 else 0,
                'position_ratio': current_frame / self.total_frames if self.total_frames > 0 else 0,
                'servo_computed': interpolated_servo,
                'interpolated': True
            }
            
            return interpolated_data
        
        # Fallback: cari frame terdekat
        closest_frame = min(available_frames, key=lambda x: abs(x - current_frame))
        return self.motion_data_dict_by_frame[closest_frame]
    
    def get_servo_data_for_timestamp(self, current_timestamp):
        """Dapatkan data servo berdasarkan timestamp saat ini dengan interpolasi"""
        if not self.motion_data_loaded or not self.motion_data_dict_by_timestamp:
            return None
        
        # Dapatkan semua timestamp yang tersedia
        available_timestamps = sorted(self.motion_data_dict_by_timestamp.keys())
        
        # Cari timestamp terdekat
        if current_timestamp <= available_timestamps[0]:
            return self.motion_data_dict_by_timestamp[available_timestamps[0]]
        elif current_timestamp >= available_timestamps[-1]:
            return self.motion_data_dict_by_timestamp[available_timestamps[-1]]
        
        # Cari timestamp sebelum dan sesudah untuk interpolasi
        prev_ts = None
        next_ts = None
        
        for ts in available_timestamps:
            if ts <= current_timestamp:
                prev_ts = ts
            if ts >= current_timestamp and next_ts is None:
                next_ts = ts
        
        # Jika ditemukan data yang tepat
        if prev_ts == current_timestamp:
            return self.motion_data_dict_by_timestamp[current_timestamp]
        
        # Jika tidak ada data tepat, lakukan interpolasi linear
        if prev_ts is not None and next_ts is not None:
            prev_data = self.motion_data_dict_by_timestamp[prev_ts]
            next_data = self.motion_data_dict_by_timestamp[next_ts]
            
            # Hitung faktor interpolasi
            factor = (current_timestamp - prev_ts) / (next_ts - prev_ts)
            
            # Interpolasi servo values
            prev_servo = prev_data.get('servo_computed', {})
            next_servo = next_data.get('servo_computed', {})
            
            interpolated_servo = {
                'servo1': int(prev_servo.get('servo1', 500) + 
                            (next_servo.get('servo1', 500) - prev_servo.get('servo1', 500)) * factor),
                'servo2': int(prev_servo.get('servo2', 500) + 
                            (next_servo.get('servo2', 500) - prev_servo.get('servo2', 500)) * factor),
                'servo3': int(prev_servo.get('servo3', 500) + 
                            (next_servo.get('servo3', 500) - prev_servo.get('servo3', 500)) * factor)
            }
            
            # Buat data interpolasi
            interpolated_data = {
                'frame': int(current_timestamp * self.fps) if self.fps > 0 else 0,
                'video_timestamp': current_timestamp,
                'position_ratio': current_timestamp / self.total_frames if self.total_frames > 0 else 0,
                'servo_computed': interpolated_servo,
                'interpolated': True
            }
            
            return interpolated_data
        
        # Fallback: cari timestamp terdekat
        closest_ts = min(available_timestamps, key=lambda x: abs(x - current_timestamp))
        return self.motion_data_dict_by_timestamp[closest_ts]
    
    def update_servo_from_position(self, current_frame, current_timestamp):
        """Update servo data berdasarkan posisi video saat ini"""
        if not self.motion_data_loaded:
            return
        
        # Prioritaskan pencarian berdasarkan frame (lebih akurat)
        motion_point = self.get_servo_data_for_frame(current_frame)
        
        # Jika tidak ditemukan berdasarkan frame, coba berdasarkan timestamp
        if motion_point is None:
            motion_point = self.get_servo_data_for_timestamp(current_timestamp)
        
        if motion_point:
            # Simpan data motion saat ini
            self.current_motion_data = motion_point
            
            # Ambil data servo yang sudah dikomputasi
            servo_computed = motion_point.get('servo_computed', {})
            servo1 = servo_computed.get('servo1', 0)
            servo2 = servo_computed.get('servo2', 0)
            servo3 = servo_computed.get('servo3', 0)
            
            # Cek apakah data hasil interpolasi
            is_interpolated = motion_point.get('interpolated', False)
            interpolated_marker = " (≈)" if is_interpolated else ""
            
            # Update label untuk menampilkan nilai servo
            self.servo_label.setText(f"Servo: {servo1} / {servo2} / {servo3}{interpolated_marker}")
            
            # KIRIM DATA KE PLC VIA MODBUS  
            # Machine state: 1 = running (video playing), 0 = idle/stop
            machine_state = 1 if self.is_playing else 0
            
            # Update data di PLC sender
            self.plc_sender.update_data(machine_state, servo1, servo2, servo3)

            # Kirim data servo ke PLC via signal
            servo_data = {
                'servo1': servo1,
                'servo2': servo2,
                'servo3': servo3,
                'frame': current_frame,
                'timestamp': current_timestamp,
                'position_ratio': motion_point.get('position_ratio', 0),
                'joystick': motion_point.get('joystick', {}),
                'interpolated': is_interpolated,
                'source_frame': motion_point.get('frame', current_frame),
                'source_timestamp': motion_point.get('video_timestamp', current_timestamp)
            }
            self.servo_data_ready.emit(servo_data)
            
            # Debug print setiap 60 frame
            if current_frame % 60 == 0:
                print(f"Frame {current_frame}/{self.total_frames} ({current_timestamp:.2f}s): "
                    f"S1={servo1}, S2={servo2}, S3={servo3}{interpolated_marker}")
                print(f"PLC: State={machine_state}, Servo1={servo1}, Servo2={servo2}, Servo3={servo3}")
        else:
            # Tidak ada data motion untuk posisi ini
            self.servo_label.setText("Servo: No data")
    
    def update_video_display(self, cv_frame):
        """Update tampilan video dengan frame baru"""
        height, width, channel = cv_frame.shape
        bytes_per_line = 3 * width
        q_image = QImage(cv_frame.data, width, height, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)
        
        # Scale agar sesuai dengan label
        scaled_pixmap = pixmap.scaled(
            self.video_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.video_label.setPixmap(scaled_pixmap)
        
    def update_position(self, current_frame):
        """Update posisi slider dan label waktu, serta sinkronkan data servo"""
        if not self.is_seeking and self.total_frames > 0:
            # Update slider
            position = (current_frame / self.total_frames) * 100
            self.slider.blockSignals(True)
            self.slider.setValue(int(position))
            self.slider.blockSignals(False)
            
            # Update time label
            current_time = QTime(0, 0, 0).addSecs(int(current_frame / self.fps))
            total_time = QTime(0, 0, 0).addSecs(int(self.total_frames / self.fps))
            self.time_label.setText(
                f"{current_time.toString('mm:ss')} / {total_time.toString('mm:ss')}"
            )
            
            # Update frame label
            current_timestamp = current_frame / self.fps
            self.frame_label.setText(f"Frame: {current_frame} / {self.total_frames}")
            
            # Update servo data berdasarkan posisi saat ini
            self.update_servo_from_position(current_frame, current_timestamp)
            
    def load_video(self):
        """Load video file dan motion data"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video File",
            "",
            "Video Files (*.mp4 *.avi *.mov *.mkv *.flv *.wmv)"
        )
        
        if file_path:
            # Show loading indicator
            self.loading_bar.setVisible(True)
            self.load_btn.setEnabled(False)
            self.info_label.setText("Loading video and motion data...")
            
            # Load motion data terlebih dahulu
            if not self.load_motion_data(file_path):
                # Jika motion data gagal dimuat, tampilkan error dan batalkan loading video
                self.loading_bar.setVisible(False)
                self.load_btn.setEnabled(True)
                self.info_label.setText("Failed to load motion data")
                return
            
            # Load video di thread
            self.video_thread.load_video(file_path)
            
            # Start thread jika belum running
            if not self.video_thread.isRunning():
                self.video_thread.start()
                
    def on_video_loaded(self, video_info):
        """Callback ketika video selesai di-load"""
        self.loading_bar.setVisible(False)
        self.load_btn.setEnabled(True)
        
        self.total_frames = video_info['total_frames']
        self.fps = video_info['fps']
        self.video_loaded = True
        
        # Update info
        file_name = os.path.basename(video_info['path'])
        motion_status = "✓" if self.motion_data_loaded else "✗"
        self.info_label.setText(
            f"Loaded: {file_name} | "
            f"Duration: {video_info['duration']:.2f}s | "
            f"FPS: {self.fps:.1f} | "
            f"Motion Data: {motion_status}"
        )
        
        # Enable controls jika motion data berhasil dimuat
        if self.motion_data_loaded:
            self.servo_home_btn.setEnabled(True)
            self.play_btn.setEnabled(True)
            self.pause_btn.setEnabled(True)
            self.stop_btn.setEnabled(True)
            self.slider.setEnabled(True)
            
            # Start PLC sender
            if not self.plc_sender.is_sending_enabled:
                self.plc_sender.start_sending()
        else:
            # Jika motion data tidak ada, tetap bisa memutar video tapi tanpa servo
            self.play_btn.setEnabled(True)
            self.pause_btn.setEnabled(True)
            self.stop_btn.setEnabled(True)
            self.slider.setEnabled(True)
            self.info_label.setText(self.info_label.text() + " (No motion data)")
        
    def on_loading_error(self, error_msg):
        """Callback ketika error loading video atau motion data"""
        self.loading_bar.setVisible(False)
        self.load_btn.setEnabled(True)
        self.info_label.setText("Error loading video or motion data")
        self.motion_data_loaded = False
        QMessageBox.critical(self, "Error", error_msg)
        
    def play_video(self):
        """Play video"""
        if self.video_loaded:
            self.is_playing = True
            self.video_thread.play()
            # Start PLC sender jika belum running
            if not self.plc_sender.is_sending_enabled:
                self.plc_sender.start_sending()
            
    def pause_video(self):
        """Pause video"""
        if self.video_loaded:
            self.is_playing = False
            self.video_thread.pause()
            # Update machine state ke idle
            if hasattr(self.plc_sender, 'data_buffer'):
                self.plc_sender.update_data(0,  
                                            self.plc_sender.data_buffer['servo1'],
                                            self.plc_sender.data_buffer['servo2'],
                                            self.plc_sender.data_buffer['servo3'])
            
    def stop_video(self):
        """Stop video"""
        if self.video_loaded:
            self.is_playing = False
            self.video_thread.stop()

            # Send neutral position and stop
            # self.plc_sender.send_neutral_position()

            # Reset servo data
            self.servo_label.setText("Servo: - / - / -")
            self.current_motion_data = None
            
    def slider_pressed(self):
        """Slider ditekan - mulai seeking"""
        self.is_seeking = True
        
    def slider_value_changed(self, value):
        """Value slider berubah - update preview"""
        if self.is_seeking and self.total_frames > 0:
            # Simpan nilai untuk seek nanti
            self.pending_seek_value = value
            
            # Update time label preview
            frame_pos = int((value / 100.0) * self.total_frames)
            current_time = QTime(0, 0, 0).addSecs(int(frame_pos / self.fps))
            total_time = QTime(0, 0, 0).addSecs(int(self.total_frames / self.fps))
            self.time_label.setText(
                f"{current_time.toString('mm:ss')} / {total_time.toString('mm:ss')}"
            )
            
            # Update preview servo data saat seeking
            current_timestamp = frame_pos / self.fps
            self.update_servo_from_position(frame_pos, current_timestamp)
            
            # Gunakan timer untuk debounce
            self.seek_timer.start(50)
            
    def slider_released(self):
        """Slider dilepas - lakukan seeking"""
        if self.video_loaded:
            # Hentikan timer jika masih berjalan
            self.seek_timer.stop()
            self.perform_seek()
            self.is_seeking = False
            
    def perform_seek(self):
        """Lakukan seeking ke posisi yang diinginkan"""
        if self.video_loaded:
            # Kirim request seek ke thread
            self.video_thread.seek_to(self.pending_seek_value)
            # Pause video saat seeking
            if self.is_playing:
                self.is_playing = False
                self.video_thread.pause()
                
    def on_video_end(self):
        """Callback ketika video selesai"""
        self.is_playing = False
        self.info_label.setText("Video ended")

        # Send neutral position
        # self.plc_sender.send_neutral_position()

        # Reset servo data
        self.servo_label.setText("Servo: - / - / -")
        self.current_motion_data = None
        
    def home_servo(self):
        """Fungsi untuk homing servo"""
        # Kirim sinyal homing ke PLC
        homing_data = {
            'command': 'home',
            'servo1': 500,  # Nilai home untuk servo1
            'servo2': 500,  # Nilai home untuk servo2
            'servo3': 500   # Nilai home untuk servo3
        }
        self.servo_data_ready.emit(homing_data)
        QMessageBox.information(self, "Homing", "Homing command sent to servo")