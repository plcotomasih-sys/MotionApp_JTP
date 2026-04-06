# plc_data_sender.py
from PySide6.QtCore import QObject, Signal, QTimer
import time

class PLCDataSender(QObject):
    """Class untuk mengirim data real-time ke PLC via Modbus TCP"""
    
    # Signals untuk komunikasi dengan UI
    data_sent = Signal(dict)
    data_failed = Signal(str)
    connection_error = Signal(str)
    
    def __init__(self, plc_connection):
        super().__init__()
        self.plc = plc_connection
        self.is_sending_enabled = False
        self.send_timer = QTimer()
        self.send_timer.timeout.connect(self.send_buffered_data)
        
        # Buffer untuk data yang akan dikirim
        self.data_buffer = {
            'machine_state': 0,
            'servo1': 500,  # Default neutral
            'servo2': 500,
            'servo3': 500,
            'timestamp': 0,
            'source': 'initial'
        }
        
        # Track data terakhir yang dikirim
        self.last_sent_data = None
        
        # Pengaturan pengiriman
        self.send_interval = 50  # ms (20 Hz update rate)
        self.last_send_time = 0
        self.min_send_interval = 0.05  # Minimum 50ms
        
        # Counter untuk debug
        self.send_counter = 0
        
        # Statistik
        self.stats = {
            'total_sent': 0,
            'total_failed': 0,
            'last_success_time': 0,
            'last_error': None
        }
        
    def set_send_interval(self, interval_ms):
        """Set interval pengiriman data ke PLC"""
        if interval_ms >= 20:
            self.send_interval = interval_ms
            if self.is_sending_enabled:
                self.send_timer.start(interval_ms)
            return True
        return False
    
    def start_sending(self):
        """Mulai mengirim data ke PLC"""
        if not self.plc.is_connected:
            self.connection_error.emit("Cannot start sending: PLC not connected")
            return False
        
        self.is_sending_enabled = True
        self.send_counter = 0
        self.last_sent_data = None
        self.send_timer.start(self.send_interval)
        print(f"✓ Data sending started (interval: {self.send_interval}ms)")
        return True
    
    def stop_sending(self):
        """Stop mengirim data ke PLC"""
        self.is_sending_enabled = False
        self.send_timer.stop()
        print("Data sending stopped")
    
    def update_data(self, machine_state, servo1, servo2, servo3, source="video"):
        """
        Update data yang akan dikirim ke PLC
        
        Args:
            machine_state: 0=idle, 1=running, 2=paused, 3=error
            servo1, servo2, servo3: nilai servo (0-1000)
            source: sumber data ('video', 'neutral', 'pause', etc)
        """
        # Validasi input
        servo1 = max(0, min(1000, servo1))
        servo2 = max(0, min(1000, servo2))
        servo3 = max(0, min(1000, servo3))
        machine_state = max(0, min(3, machine_state))
        
        # Cek apakah data berubah secara signifikan
        prev_s1 = self.data_buffer['servo1']
        prev_s2 = self.data_buffer['servo2']
        prev_s3 = self.data_buffer['servo3']
        
        # Deteksi perubahan besar (lebih dari 50)
        if (abs(prev_s1 - servo1) > 50 or
            abs(prev_s2 - servo2) > 50 or
            abs(prev_s3 - servo3) > 50):
            print(f"[PLC Sender] Large change detected from {source}:")
            print(f"  Previous: S1={prev_s1}, S2={prev_s2}, S3={prev_s3}")
            print(f"  New:      S1={servo1}, S2={servo2}, S3={servo3}")
        
        # Update buffer
        self.data_buffer.update({
            'machine_state': machine_state,
            'servo1': servo1,
            'servo2': servo2,
            'servo3': servo3,
            'timestamp': time.time(),
            'source': source
        })
        
        # Jika tidak dalam mode timer, kirim langsung
        if not self.is_sending_enabled:
            self.send_data_now()
    
    def send_data_now(self):
        """Kirim data segera"""
        if not self.plc.is_connected or not self.plc.client:
            return False
        
        # Cek interval pengiriman
        current_time = time.time()
        if current_time - self.last_send_time < self.min_send_interval:
            return False
        
        try:
            # Ambil data dari buffer
            machine_state = self.data_buffer['machine_state']
            servo1 = self.data_buffer['servo1']
            servo2 = self.data_buffer['servo2']
            servo3 = self.data_buffer['servo3']
            source = self.data_buffer.get('source', 'unknown')
            
            # Cek apakah data sama dengan yang terakhir dikirim
            if (self.last_sent_data and 
                self.last_sent_data['servo1'] == servo1 and
                self.last_sent_data['servo2'] == servo2 and
                self.last_sent_data['servo3'] == servo3 and
                self.last_sent_data['machine_state'] == machine_state):
                # Data sama, skip kirim
                return True
            
            # Gunakan fungsi dari PLC connection
            success = self.plc.write_all_data(machine_state, servo1, servo2, servo3)
            
            if success:
                self.last_send_time = current_time
                self.stats['total_sent'] += 1
                self.send_counter += 1
                
                # Simpan data yang terkirim
                self.last_sent_data = {
                    'machine_state': machine_state,
                    'servo1': servo1,
                    'servo2': servo2,
                    'servo3': servo3,
                    'source': source
                }
                
                # Debug setiap 50 kali
                if self.send_counter % 50 == 0:
                    print(f"[PLC Sender] Sent #{self.send_counter}: "
                          f"S1={servo1}, S2={servo2}, S3={servo3} (from {source})")
                
                self.data_sent.emit({
                    'machine_state': machine_state,
                    'servo1': servo1,
                    'servo2': servo2,
                    'servo3': servo3,
                    'source': source,
                    'timestamp': current_time
                })
                return True
            else:
                error_msg = "Failed to write to PLC"
                self.stats['total_failed'] += 1
                self.stats['last_error'] = error_msg
                self.data_failed.emit(error_msg)
                return False
                    
        except Exception as e:
            error_msg = f"Exception sending data: {e}"
            self.stats['total_failed'] += 1
            self.stats['last_error'] = error_msg
            self.data_failed.emit(error_msg)
            return False
    
    def send_buffered_data(self):
        """Kirim data yang ada di buffer (dipanggil oleh timer)"""
        if self.is_sending_enabled:
            self.send_data_now()
    
    def send_neutral_position(self):
        """Kirim posisi netral (500) ke semua servo"""
        print("[PLC Sender] Sending neutral position")
        self.update_data(0, 500, 500, 500, source="neutral")
    
    def send_emergency_stop(self):
        """Kirim perintah emergency stop (semua servo ke 0)"""
        print("[PLC Sender] EMERGENCY STOP")
        self.update_data(3, 0, 0, 0, source="emergency")
        return True
    
    def get_statistics(self):
        """Dapatkan statistik pengiriman data"""
        total = self.stats['total_sent'] + self.stats['total_failed']
        success_rate = (self.stats['total_sent'] / total * 100) if total > 0 else 0
        
        return {
            **self.stats,
            'is_sending': self.is_sending_enabled,
            'send_interval': self.send_interval,
            'send_counter': self.send_counter,
            'buffer': self.data_buffer.copy(),
            'success_rate': success_rate
        }