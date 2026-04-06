# video_thread.py
import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker
import time

class VideoThread(QThread):
    """Thread untuk memproses video player"""
    
    # Signals untuk komunikasi dengan UI
    frame_ready = Signal(np.ndarray)  # Signal untuk mengirim frame
    position_changed = Signal(int)     # Signal untuk posisi frame berubah
    video_ended = Signal()             # Signal ketika video selesai
    video_loaded = Signal(dict)        # Signal ketika video berhasil di-load
    loading_error = Signal(str)        # Signal ketika error loading
    seek_request = Signal(int)         # Signal untuk request seek (internal)
    
    def __init__(self):
        super().__init__()
        self.cap = None                 # Video capture object
        self.running = True             # Flag untuk loop thread
        self.is_paused = True           # Flag pause video
        self.current_frame = 0          # Posisi frame saat ini
        self.total_frames = 0           # Total frame video
        self.fps = 30                   # FPS video
        self.video_path = None          # Path file video
        self.first_frame = None         # Frame pertama untuk preview
        self.pending_seek = None        # Pending seek position
        self.last_frame = None          # Frame terakhir yang ditampilkan
        self.last_position = 0          # Posisi terakhir
        
        # Mutex untuk thread safety
        self.mutex = QMutex()
        
    def load_video(self, file_path):
        """Load video file"""
        with QMutexLocker(self.mutex):
            # Tutup capture sebelumnya jika ada
            if self.cap is not None:
                self.cap.release()
                
            # Buka video baru
            self.cap = cv2.VideoCapture(file_path)
            self.video_path = file_path
            
            if not self.cap.isOpened():
                self.loading_error.emit(f"Tidak bisa membuka video: {file_path}")
                return
                
            # Dapatkan informasi video
            self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            if self.fps <= 0:
                self.fps = 30
                
            # Ambil frame pertama
            ret, frame = self.cap.read()
            if ret:
                self.first_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self.last_frame = self.first_frame
                
            # Reset posisi ke awal
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self.current_frame = 0
            self.is_paused = True
            self.pending_seek = None
            
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
                
    def seek_to(self, position_percent):
        """Request seek ke posisi tertentu (dipanggil dari UI)"""
        with QMutexLocker(self.mutex):
            self.pending_seek = position_percent
            
    def run(self):
        """Main loop thread"""
        while self.running:
            with QMutexLocker(self.mutex):
                # Proses pending seek jika ada
                if self.pending_seek is not None and self.cap is not None and self.cap.isOpened():
                    position_percent = self.pending_seek
                    frame_pos = int((position_percent / 100.0) * self.total_frames)
                    
                    # Set posisi baru
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
                    self.current_frame = frame_pos
                    
                    # Ambil frame di posisi baru
                    ret, frame = self.cap.read()
                    if ret:
                        self.last_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        self.last_position = self.current_frame
                        
                        # Kirim frame dan posisi
                        self.frame_ready.emit(self.last_frame)
                        self.position_changed.emit(self.current_frame)
                        
                        # Pause setelah seek
                        self.is_paused = True
                        
                    # Clear pending seek
                    self.pending_seek = None
                    
                # Proses playback normal
                if self.cap is not None and self.cap.isOpened():
                    if not self.is_paused:
                        # Baca frame
                        ret, frame = self.cap.read()
                        
                        if ret:
                            self.current_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                            self.last_position = self.current_frame
                            
                            # Convert BGR ke RGB
                            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            self.last_frame = rgb_frame
                            
                            # Kirim frame ke UI
                            self.frame_ready.emit(rgb_frame)
                            self.position_changed.emit(self.current_frame)
                            
                            # Kontrol kecepatan (FPS)
                            delay = int(1000 / self.fps)
                            self.msleep(delay)
                        else:
                            # Video selesai
                            self.video_ended.emit()
                            self.is_paused = True
                            self.msleep(100)
                    else:
                        # Paused, tampilkan frame terakhir
                        if self.last_frame is not None:
                            self.frame_ready.emit(self.last_frame)
                            self.position_changed.emit(self.last_position)
                        elif self.first_frame is not None:
                            self.frame_ready.emit(self.first_frame)
                            self.position_changed.emit(0)
                        self.msleep(50)
                else:
                    # Tidak ada video, tampilkan frame pertama jika ada
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
        """Stop video dan reset ke awal"""
        with QMutexLocker(self.mutex):
            if self.cap is not None:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self.current_frame = 0
                self.last_position = 0
                self.is_paused = True
                
                # Ambil frame pertama
                ret, frame = self.cap.read()
                if ret:
                    self.last_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # Reset kembali
                    self.frame_ready.emit(self.last_frame)
                    self.position_changed.emit(0)
                
    def get_position(self):
        """Dapatkan posisi saat ini (0-100)"""
        with QMutexLocker(self.mutex):
            if self.total_frames > 0:
                return (self.current_frame / self.total_frames) * 100
            return 0
            
    def get_current_frame(self):
        """Dapatkan nomor frame saat ini"""
        with QMutexLocker(self.mutex):
            return self.current_frame
            
    def get_total_frames(self):
        """Dapatkan total frame"""
        with QMutexLocker(self.mutex):
            return self.total_frames
            
    def get_fps(self):
        """Dapatkan FPS video"""
        with QMutexLocker(self.mutex):
            return self.fps
            
    def stop_thread(self):
        """Hentikan thread"""
        self.running = False
        if self.cap is not None:
            self.cap.release()
        self.wait()