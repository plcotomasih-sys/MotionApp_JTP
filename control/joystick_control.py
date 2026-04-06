# joystick_control.py
import pygame
import sys
import time
from PySide6.QtCore import QObject, Signal, QTimer

class JoystickController(QObject):
    """Controller untuk membaca input joystick"""
    
    # Signals
    joystick_moved = Signal(float, float, float)  # lx, ly, ry
    button_pressed = Signal(int)
    joystick_connected = Signal(bool)
    joystick_disconnected = Signal()
    
    def __init__(self):
        super().__init__()
        self.joystick = None
        self.is_connected = False
        self.joystick_id = -1
        self.deadzone = 0.1
        self.joystick_name = ""
        
        # Inisialisasi pygame
        pygame.init()
        pygame.joystick.init()
        
        # Timer untuk polling joystick
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self.poll_joystick)
        self.poll_timer.setInterval(20)  # 50Hz polling rate
        
        # Debug flag
        self.debug = True
        
    def get_available_joysticks(self):
        """Dapatkan daftar joystick yang tersedia"""
        pygame.joystick.init()
        count = pygame.joystick.get_count()
        joysticks = []
        
        print(f"Found {count} joystick(s)")  # Debug
        
        for i in range(count):
            try:
                joy = pygame.joystick.Joystick(i)
                joy.init()
                joysticks.append({
                    'id': i,
                    'name': joy.get_name(),
                    'axes': joy.get_numaxes(),
                    'buttons': joy.get_numbuttons(),
                    'hats': joy.get_numhats()
                })
                joy.quit()
            except Exception as e:
                print(f"Error reading joystick {i}: {e}")
                
        return joysticks
        
    def connect_joystick(self, joystick_id=0):
        """Connect ke joystick dengan ID tertentu"""
        try:
            # Cek apakah joystick tersedia
            if pygame.joystick.get_count() <= joystick_id:
                print(f"Joystick ID {joystick_id} not found")
                return False
                
            # Inisialisasi joystick
            self.joystick = pygame.joystick.Joystick(joystick_id)
            self.joystick.init()
            
            # Simpan info
            self.joystick_id = joystick_id
            self.joystick_name = self.joystick.get_name()
            self.is_connected = True
            
            # Start polling
            self.poll_timer.start()
            
            # Emit signal
            self.joystick_connected.emit(True)
            
            print(f"Connected to: {self.joystick_name}")
            print(f"  Axes: {self.joystick.get_numaxes()}")
            print(f"  Buttons: {self.joystick.get_numbuttons()}")
            print(f"  Hats: {self.joystick.get_numhats()}")
            
            return True
            
        except Exception as e:
            print(f"Error connecting to joystick: {e}")
            return False
            
    def disconnect_joystick(self):
        """Disconnect joystick"""
        self.poll_timer.stop()
        
        if self.joystick:
            self.joystick.quit()
            self.joystick = None
            
        self.is_connected = False
        self.joystick_id = -1
        self.joystick_name = ""
        
        self.joystick_connected.emit(False)
        self.joystick_disconnected.emit()
        
        print("Joystick disconnected")
        
    def poll_joystick(self):
        """Polling joystick untuk membaca nilai"""
        if not self.is_connected or not self.joystick:
            return
            
        # Process pygame events
        pygame.event.pump()
        
        try:
            # Baca axis values
            num_axes = self.joystick.get_numaxes()
            
            # Default values
            lx = 0.0
            ly = 0.0
            ry = 0.0
            
            # Baca axis berdasarkan konfigurasi umum
            # Axis 0: Left X (roll)
            if num_axes > 0:
                lx = self.joystick.get_axis(0)
                lx = self.apply_deadzone(lx)
                
            # Axis 1: Left Y (pitch)
            if num_axes > 1:
                ly = self.joystick.get_axis(1)
                ly = self.apply_deadzone(ly)
                
            # Axis 2: Right Y atau Throttle (heave)
            if num_axes > 2:
                ry = self.joystick.get_axis(4)
                ry = self.apply_deadzone(ry)
            # elif num_axes > 3:
            #     # Alternative: axis 3 untuk throttle
            #     ry = self.joystick.get_axis(3)
            #     ry = self.apply_deadzone(ry)
                
            # Emit signal dengan nilai yang sudah diproses
            self.joystick_moved.emit(lx, ly, ry)
            
            # Debug output (optional)
            # if self.debug and (abs(lx) > 0.05 or abs(ly) > 0.05 or abs(ry) > 0.05):
            #     print(f"Joystick: LX={lx:+.3f}, LY={ly:+.3f}, RY={ry:+.3f}")
                
            # Baca buttons (optional)
            num_buttons = self.joystick.get_numbuttons()
            for i in range(num_buttons):
                if self.joystick.get_button(i):
                    self.button_pressed.emit(i)
                    if self.debug:
                        print(f"Button {i} pressed")
                        
        except Exception as e:
            print(f"Error polling joystick: {e}")
            
    def apply_deadzone(self, value):
        """Apply deadzone ke nilai axis"""
        if abs(value) < self.deadzone:
            return 0.0
        return value
        
    def set_deadzone(self, deadzone):
        """Set deadzone value (0-0.3)"""
        self.deadzone = max(0.0, min(0.3, deadzone))
        
    def get_joystick_info(self):
        """Dapatkan informasi joystick"""
        if not self.is_connected or not self.joystick:
            return None
            
        return {
            'name': self.joystick_name,
            'id': self.joystick_id,
            'axes': self.joystick.get_numaxes(),
            'buttons': self.joystick.get_numbuttons(),
            'hats': self.joystick.get_numhats()
        }
        
    def calibrate_center(self):
        """Kalibrasi posisi center joystick"""
        if not self.is_connected:
            return None
            
        print("Calibrating joystick center...")
        samples = []
        for _ in range(100):
            pygame.event.pump()
            lx = self.joystick.get_axis(0) if self.joystick.get_numaxes() > 0 else 0
            ly = self.joystick.get_axis(1) if self.joystick.get_numaxes() > 1 else 0
            ry = self.joystick.get_axis(2) if self.joystick.get_numaxes() > 2 else 0
            samples.append((lx, ly, ry))
            time.sleep(0.01)
            
        # Hitung rata-rata
        avg_lx = sum(s[0] for s in samples) / len(samples)
        avg_ly = sum(s[1] for s in samples) / len(samples)
        avg_ry = sum(s[2] for s in samples) / len(samples)
        
        print(f"Center calibration: LX={avg_lx:.3f}, LY={avg_ly:.3f}, RY={avg_ry:.3f}")
        
        return {'lx': avg_lx, 'ly': avg_ly, 'ry': avg_ry}