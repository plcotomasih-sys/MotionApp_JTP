# record_thread.py
import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker
import time

class RecordThread(QThread):
    """Thread khusus untuk record motion dengan kontrol video sendiri"""
    
    # Signals
    frame_ready = Signal(np.ndarray)   # Signal untuk update tampilan video
    position_changed = Signal(int)     # Signal posisi frame
    video_loaded = Signal(dict)        # Signal video selesai di-load
    loading_error = Signal(str)        # Signal error loading
    video_ended = Signal()             # Signal video selesai
    
    def __init__(self):
        super().__init__()
        self.cap = None
        self.running = True
        self.is_paused = True
        self.current_frame = 0
        self.total_frames = 0
        self.fps = 30
        self.video_path = None
        self.first_frame = None
        self.last_frame = None
        self.last_position = 0
        
        # Mutex untuk thread safety
        self.mutex = QMutex()
        
    def load_video(self, file_path):
        """Load video file"""
        with QMutexLocker(self.mutex):
            if self.cap is not None:
                self.cap.release()
                
            self.cap = cv2.VideoCapture(file_path)
            self.video_path = file_path
            
            if not self.cap.isOpened():
                self.loading_error.emit(f"Cannot open video: {file_path}")
                return
                
            self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            if self.fps <= 0:
                self.fps = 30
                
            # Ambil frame pertama
            ret, frame = self.cap.read()
            if ret:
                self.first_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self.last_frame = self.first_frame
                
            # Reset ke awal
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self.current_frame = 0
            self.is_paused = True
            
            # Kirim info video
            video_info = {
                'path': file_path,
                'total_frames': self.total_frames,
                'fps': self.fps,
                'duration': self.total_frames / self.fps
            }
            self.video_loaded.emit(video_info)
            
            # Kirim frame pertama
            if self.first_frame is not None:
                self.frame_ready.emit(self.first_frame)
                self.position_changed.emit(0)
                
    def run(self):
        """Main loop thread"""
        while self.running:
            with QMutexLocker(self.mutex):
                if self.cap is not None and self.cap.isOpened():
                    if not self.is_paused:
                        ret, frame = self.cap.read()
                        if ret:
                            self.current_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                            self.last_position = self.current_frame
                            
                            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            self.last_frame = rgb_frame
                            
                            self.frame_ready.emit(rgb_frame)
                            self.position_changed.emit(self.current_frame)
                            
                            delay = int(1000 / self.fps)
                            self.msleep(delay)
                        else:
                            self.video_ended.emit()
                            self.is_paused = True
                            self.msleep(100)
                    else:
                        # Paused - tampilkan frame terakhir
                        if self.last_frame is not None:
                            self.frame_ready.emit(self.last_frame)
                            self.position_changed.emit(self.last_position)
                        elif self.first_frame is not None:
                            self.frame_ready.emit(self.first_frame)
                            self.position_changed.emit(0)
                        self.msleep(50)
                else:
                    if self.first_frame is not None:
                        self.frame_ready.emit(self.first_frame)
                        self.position_changed.emit(0)
                    self.msleep(50)
                    
    def play(self):
        """Play video"""
        with QMutexLocker(self.mutex):
            self.is_paused = False
            
    def pause(self):
        """Pause video"""
        with QMutexLocker(self.mutex):
            self.is_paused = True
            
    def stop(self):
        """Stop dan reset ke awal"""
        with QMutexLocker(self.mutex):
            if self.cap is not None:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self.current_frame = 0
                self.last_position = 0
                self.is_paused = True
                
                if self.first_frame is not None:
                    self.frame_ready.emit(self.first_frame)
                    self.position_changed.emit(0)
                    
    def seek(self, position_percent):
        """Pindah ke posisi tertentu (0-100)"""
        with QMutexLocker(self.mutex):
            if self.cap is not None and self.total_frames > 0:
                frame_pos = int((position_percent / 100.0) * self.total_frames)
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
                self.current_frame = frame_pos
                self.last_position = frame_pos
                
                ret, frame = self.cap.read()
                if ret:
                    self.last_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
                    self.frame_ready.emit(self.last_frame)
                    self.position_changed.emit(frame_pos)
                    
    def stop_thread(self):
        """Hentikan thread"""
        self.running = False
        if self.cap is not None:
            self.cap.release()
        self.wait()