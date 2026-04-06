# video_player_tab.py
import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QSlider, QLabel, QFileDialog, QMessageBox, QProgressBar)
from PySide6.QtCore import Qt, QTime, QTimer
from PySide6.QtGui import QImage, QPixmap

class VideoPlayerTab(QWidget):
    def __init__(self, video_thread):
        super().__init__()
        self.video_thread = video_thread
        self.is_playing = False
        self.total_frames = 0
        self.fps = 30
        self.video_loaded = False
        self.is_seeking = False  # Flag untuk menandai sedang seeking
        self.seek_timer = QTimer()  # Timer untuk debounce seek
        self.seek_timer.setSingleShot(True)
        self.seek_timer.timeout.connect(self.perform_seek)
        self.pending_seek_value = 0

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
        # self.servo_home_btn.clicked.connect(self.play_video)
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
        
        layout.addLayout(info_layout)
        
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
        """Update posisi slider dan label waktu"""
        if not self.is_seeking and self.total_frames > 0:
            # Update slider (hanya jika tidak sedang seeking)
            position = (current_frame / self.total_frames) * 100
            self.slider.blockSignals(True)  # Block signals untuk menghindari loop
            self.slider.setValue(int(position))
            self.slider.blockSignals(False)
            
            # Update time label
            current_time = QTime(0, 0, 0).addSecs(int(current_frame / self.fps))
            total_time = QTime(0, 0, 0).addSecs(int(self.total_frames / self.fps))
            self.time_label.setText(
                f"{current_time.toString('mm:ss')} / {total_time.toString('mm:ss')}"
            )
            
            # Update frame label
            self.frame_label.setText(f"Frame: {current_frame} / {self.total_frames}")
            
    def load_video(self):
        """Load video file"""
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
            self.info_label.setText("Loading video...")
            
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
        self.info_label.setText(
            f"Loaded: {file_name} | "
            f"Duration: {video_info['duration']:.2f}s | "
            f"FPS: {self.fps:.1f}"
        )
        
        # Enable controls
        self.servo_home_btn.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.slider.setEnabled(True)
        
    def on_loading_error(self, error_msg):
        """Callback ketika error loading video"""
        self.loading_bar.setVisible(False)
        self.load_btn.setEnabled(True)
        self.info_label.setText("Error loading video")
        QMessageBox.critical(self, "Error", f"Failed to load video:\n{error_msg}")
        
    def play_video(self):
        """Play video"""
        if self.video_loaded:
            self.is_playing = True
            self.video_thread.play()
            
    def pause_video(self):
        """Pause video"""
        if self.video_loaded:
            self.is_playing = False
            self.video_thread.pause()
            
    def stop_video(self):
        """Stop video"""
        if self.video_loaded:
            self.is_playing = False
            self.video_thread.stop()
            
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
            
            # Gunakan timer untuk debounce
            self.seek_timer.start(50)  # Delay 50ms
            
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