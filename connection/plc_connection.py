# plc_connection.py
import json
import os
import time
from PySide6.QtCore import QObject, Signal, QTimer
from pymodbus.client.sync import ModbusTcpClient
from pymodbus.exceptions import ModbusException
from pymodbus.payload import BinaryPayloadBuilder
from pymodbus.constants import Endian

class PLCConnection(QObject):
    """Industrial PLC Connection dengan 3-level monitoring"""
    
    # Signals
    connection_status_changed = Signal(bool, str)  # connected, message
    safety_status_changed = Signal(bool)           # safety active
    error_occurred = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.client = None
        self.is_connected = False
        self.safety_active = False
        
        # Modbus configuration
        self.ip_address = "192.168.1.100"
        self.port = 502
        self.unit_id = 1
        
        # 3-Level Monitoring Configuration
        # Level 1: Quick Check (200ms)
        self.quick_check_interval = 1000      # ms
        self.quick_check_timeout = 3         # 3x gagal = warning
        
        # Level 2: Heartbeat (1s)
        self.heartbeat_interval = 2000       # ms
        self.heartbeat_timeout = 3           # 3x gagal = safety
        
        # Level 3: Safety Timeout (3s)
        self.safety_timeout = 10000           # ms
        
        # Counters
        self.quick_check_failures = 0
        self.heartbeat_failures = 0
        self.heartbeat_counter = 0

        self.offset_addres = 1
        
        # Register addresses (sesuaikan dengan PLC)
        self.REG_QUICK_CHECK = 2561 - self.offset_addres          # Quick check status
        self.REG_HEARTBEAT_WRITE = 2562 - self.offset_addres      # Heartbeat dari Python
        self.REG_HEARTBEAT_READ = 2563 - self.offset_addres      # Heartbeat feedback dari PLC
        self.REG_CONNECTION_STATUS = 2564 - self.offset_addres    # Status koneksi
        self.REG_SAFETY_STATUS = 2565 - self.offset_addres        # Status safety
        
        # Timers
        self.quick_check_timer = QTimer()
        self.quick_check_timer.timeout.connect(self.quick_check)
        
        self.heartbeat_timer = QTimer()
        self.heartbeat_timer.timeout.connect(self.heartbeat_check)

        # Level 3: Safety Timer (QTimer, bukan integer)
        self.safety_timer = QTimer()
        self.safety_timer.timeout.connect(self.activate_safety)
        self.safety_timer.setSingleShot(True)  # One-shot timer
        
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.read_plc_status)
        
        # Load config
        self.config_file = "plc_config.json"
        self.load_config()
        
    def write_servo_positions(self, servo1, servo2, servo3):
        """
        Write servo positions ke PLC sebagai REAL (32-bit float)
        Sesuai konfigurasi:
        - ServoTargetPos[0]: address 2569-2570
        - ServoTargetPos[1]: address 2571-2572
        - ServoTargetPos[2]: address 2573-2574
        """
        # Validasi nilai
        servo1 = max(0, min(1000, servo1))
        servo2 = max(0, min(1000, servo2))
        servo3 = max(0, min(1000, servo3))
        
        # Konversi ke float (REAL)
        # Asumsi: PLC menerima nilai 0.0 - 1000.0 (atau 0.0 - 1.0)
        # Sesuaikan dengan kebutuhan. Dari konfigurasi, nilai 7e-43 dan 8.96e-38 menunjukkan 
        # nilai float yang sangat kecil, kemungkinan range 0.0 - 1000.0
        
        # Opsi 1: Kirim langsung nilai integer sebagai float
        values = [
            float(servo1),  # 0.0 - 1000.0
            float(servo2),
            float(servo3)
        ]
        
        # Opsi 2: Jika PLC menggunakan range 0.0 - 1.0
        # values = [
        #     servo1 / 1000.0,
        #     servo2 / 1000.0,
        #     servo3 / 1000.0
        # ]
        
        try:
            from pymodbus.payload import BinaryPayloadBuilder
            from pymodbus.constants import Endian
            
            # Buat builder dengan format yang sesuai
            # REAL (32-bit float) = 2 register per nilai
            builder = BinaryPayloadBuilder(
                byteorder=Endian.Big,    # Big Endian untuk byte
                wordorder=Endian.Little  # Little Endian untuk word
            )
            
            # Tambahkan semua nilai float
            for v in values:
                builder.add_32bit_float(v)
            
            # Konversi ke register
            payload = builder.to_registers()
            
            # Alamat awal array (ServoTargetPos[0])
            # Dari konfigurasi: 4X2569, dalam zero-based addressing = 2568
            start_address = 2568  # karena Modbus address 4X2569 = 2568 (0-based)
            
            # print(f"[PLC] Writing servo values: {values}")
            # print(f"[PLC] Payload registers: {payload}")
            # print(f"[PLC] Start address: {start_address}")
            
            # Tulis ke PLC
            result = self.client.write_registers(
                start_address,
                payload,
                unit=self.unit_id
            )
            
            if result.isError():
                print(f"[PLC] Write servo failed: {result}")
                return False
            else:
                # print(f"[PLC] Write successful")
                
                # Verifikasi dengan membaca kembali
                read_result = self.client.read_holding_registers(
                    start_address, 6, unit=self.unit_id
                )
                
                if not read_result.isError():
                    # print(f"[PLC] Read back registers: {read_result.registers}")
                    
                    # Konversi balik ke float untuk verifikasi
                    from pymodbus.payload import BinaryPayloadDecoder
                    
                    decoder = BinaryPayloadDecoder.fromRegisters(
                        read_result.registers,
                        byteorder=Endian.Big,
                        wordorder=Endian.Little
                    )
                    
                    read_servo1 = decoder.decode_32bit_float()
                    read_servo2 = decoder.decode_32bit_float()
                    read_servo3 = decoder.decode_32bit_float()
                    
                    # print(f"[PLC] Read back values: {read_servo1:.2f}, {read_servo2:.2f}, {read_servo3:.2f}")
                    
                    # Cek apakah nilai sesuai
                    # if (abs(read_servo1 - values[0]) < 0.01 and
                    #     abs(read_servo2 - values[1]) < 0.01 and
                    #     abs(read_servo3 - values[2]) < 0.01):
                    #     print("[PLC] ✓ Verification passed")
                    # else:
                    #     print("[PLC] ⚠ Verification failed - values mismatch")
                
                return True
                    
        except Exception as e:
            print(f"[PLC] Exception in write_servo_positions: {e}")
            import traceback
            traceback.print_exc()
            return False

    def write_machine_state(self, state):
        """
        Write machine state ke PLC
        
        Args:
            state: 0=idle, 1=running, 2=paused, 3=error
        
        Returns:
            bool: True jika sukses, False jika gagal
        """
        # Validasi state
        state = max(0, min(3, state))
        
        try:
            # Cari alamat untuk machine state (sesuaikan dengan konfigurasi PLC Anda)
            # Contoh: mungkin di address 2567 atau lainnya
            machine_state_address = 2567  # Sesuaikan dengan konfigurasi PLC
            
            result = self.client.write_register(
                machine_state_address,
                state,
                unit=self.unit_id
            )
            
            if result.isError():
                print(f"[PLC] Write machine state failed: {result}")
                return False
            else:
                # print(f"[PLC] Machine state written: {state}")
                return True
                
        except Exception as e:
            print(f"[PLC] Exception in write_machine_state: {e}")
            return False

    def write_all_data(self, machine_state, servo1, servo2, servo3):
        """
        Write semua data ke PLC dalam satu operasi
        
        Args:
            machine_state: 0=idle, 1=running, 2=paused, 3=error
            servo1, servo2, servo3: nilai servo (0-1000)
        
        Returns:
            bool: True jika sukses, False jika gagal
        """
        # Validasi input
        servo1 = max(0, min(1000, servo1))
        servo2 = max(0, min(1000, servo2))
        servo3 = max(0, min(1000, servo3))
        machine_state = max(0, min(3, machine_state))
        
        try:
            # Method 1: Tulis semua dalam satu batch (jika PLC mendukung)
            # Sesuaikan dengan format data PLC Anda
            
            # Contoh: Semua data sebagai integer
            # payload = [machine_state, servo1, servo2, servo3]
            # result = self.client.write_registers(2570, payload, unit=self.unit_id)
            
            # Method 2: Tulis satu per satu
            success1 = self.write_machine_state(machine_state)
            success2 = self.write_servo_positions(servo1, servo2, servo3)
            
            return success1 and success2
            
        except Exception as e:
            print(f"[PLC] Exception in write_all_data: {e}")
            return False

    def load_config(self):
        """Load konfigurasi dari file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.ip_address = config.get('ip_address', self.ip_address)
                    self.port = config.get('port', self.port)
                    self.unit_id = config.get('unit_id', self.unit_id)
                    self.quick_check_interval = config.get('quick_check_interval', 200)
                    self.heartbeat_interval = config.get('heartbeat_interval', 1000)
                    self.safety_timeout = config.get('safety_timeout', 3000)
                return True
        except Exception as e:
            print(f"Error loading config: {e}")
        return False
        
    def save_config(self):
        """Simpan konfigurasi"""
        try:
            config = {
                'ip_address': self.ip_address,
                'port': self.port,
                'unit_id': self.unit_id,
                'quick_check_interval': self.quick_check_interval,
                'heartbeat_interval': self.heartbeat_interval,
                'safety_timeout': self.safety_timeout
            }
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False

    def get_modbus_address(self):
        """Dapatkan setting Modbus address saat ini"""
        return {
            'ip_address': self.ip_address,
            'port': self.port,
            'unit_id': self.unit_id
        }
        
    def set_modbus_address(self, ip_address, port=502, unit_id=1):
        """Set parameter Modbus address"""
        self.ip_address = ip_address
        self.port = port
        self.unit_id = unit_id
        print(f"Modbus address set to: {self.ip_address}:{self.port}, Unit ID: {self.unit_id}")
            
    def connect(self, ip_address=None, port=None, unit_id=None):
        """Connect ke PLC"""
        if ip_address:
            self.ip_address = ip_address
        if port:
            self.port = port
        if unit_id:
            self.unit_id = unit_id
            
        try:
            if self.client:
                self.client.close()
                
            self.client = ModbusTcpClient(
                host=self.ip_address,
                port=self.port,
                timeout=1
            )
            
            if self.client.connect():
                self.is_connected = True
                self.safety_active = False
                self.quick_check_failures = 0
                self.heartbeat_failures = 0
                
                self.save_config()

                # Start monitoring (timer akan handle semuanya)
                self.start_monitoring()

                self.connection_status_changed.emit(
                    True, f"Connected to {self.ip_address}:{self.port}"
                )

                print(f"✓ Connected to {self.ip_address}:{self.port}")
                print(f"  Quick Check: {self.quick_check_interval}ms")
                print(f"  Heartbeat: {self.heartbeat_interval}ms")
                print(f"  Safety Timeout: {self.safety_timeout}ms")

                return True
            else:
                self.is_connected = False
                self.connection_status_changed.emit(False, "Connection failed")
                return False
                
        except Exception as e:
            self.is_connected = False
            self.connection_status_changed.emit(False, f"Error: {e}")
            return False
            
    def start_monitoring(self):
        self.quick_check_timer.start(self.quick_check_interval)
        self.heartbeat_timer.start(self.heartbeat_interval)
        self.status_timer.start(500)  # baca status tiap 500ms
        self.reset_safety_timer()
        print("✓ 3-Level Monitoring Started")
    
    def stop_monitoring(self):
        self.quick_check_timer.stop()
        self.heartbeat_timer.stop()
        self.safety_timer.stop()
        self.status_timer.stop()

    def test_read_register(self, address=40001):
        """
        Test baca register untuk verifikasi koneksi
        
        Args:
            address: Alamat register yang akan dibaca (default: 40001)
            
        Returns:
            bool: True jika berhasil baca, False jika gagal
        """
        if not self.is_connected or not self.client:
            print("Not connected, cannot test read")
            return False
            
        try:
            print(f"Testing read register {address}...")
            result = self.client.read_holding_registers(address, 1, unit=self.unit_id)
            
            if result.isError():
                print(f"Read error: {result}")
                return False
            else:
                value = result.registers[0]
                print(f"Read successful: Register {address} = {value}")
                return True
                
        except ModbusException as e:
            print(f"Modbus exception: {e}")
            return False
        except Exception as e:
            print(f"Error reading register: {e}")
            return False
        
    # ==========================================
    # LEVEL 1: QUICK CHECK (200ms)
    # ==========================================
    def quick_check(self):
        """Quick check - baca register setiap 200ms"""
        if not self.is_connected or not self.client:
            return
            
        try:
            # Baca quick check register
            result = self.client.read_holding_registers(
                self.REG_QUICK_CHECK, 1, unit=self.unit_id, timeout=0.1
            )
            
            if not result.isError():
                # Success
                self.quick_check_failures = 0
                self.reset_safety_timer()
            else:
                self.quick_check_failures += 1
                print(f"[Quick Check] Failure #{self.quick_check_failures}")
                
                if self.quick_check_failures >= self.quick_check_timeout:
                    print("[Quick Check] Threshold reached, checking heartbeat...")
                    
        except Exception as e:
            self.quick_check_failures += 1
            print(f"[Quick Check] Error: {e}")

            if self.quick_check_failures >= self.quick_check_timeout:
                self.handle_connection_lost()
            
    # ==========================================
    # LEVEL 2: HEARTBEAT (1s)
    # ==========================================
    def heartbeat_check(self):
        """Heartbeat dengan debug"""
        if not self.is_connected or not self.client:
            return
            
        try:
            # Increment counter
            self.heartbeat_counter += 1
            if self.heartbeat_counter > 65535:
                self.heartbeat_counter = 0
                
            # print(f"\n[Heartbeat #{self.heartbeat_counter}]")
            
            # STEP 1: Write ke PLC
            # print(f"  Writing {self.heartbeat_counter} to register {self.REG_HEARTBEAT_WRITE}")
            write_result = self.client.write_register(
                self.REG_HEARTBEAT_WRITE, 
                self.heartbeat_counter, 
                unit=self.unit_id
            )
            
            if write_result.isError():
                # print(f"  ✗ Write failed: {write_result}")
                self.heartbeat_failures += 1
                return
            else:
                self.heartbeat_failures = 0
                
            # print(f"  ✓ Write success")
                
        except Exception as e:
            # print(f"  ✗ Exception: {e}")
            self.heartbeat_failures += 1

            if self.heartbeat_failures >= self.heartbeat_timeout:
                self.handle_connection_lost()
    
    def read_plc_status(self):
        if not self.is_connected or not self.client:
            return

        try:
            result = self.client.read_holding_registers(
                self.REG_CONNECTION_STATUS, 2, unit=self.unit_id
            )

            if not result.isError():
                connection = result.registers[0]
                safety = result.registers[1]

                # Emit ke UI
                self.connection_status_changed.emit(
                    bool(connection),
                    "PLC Connected" if connection else "PLC Disconnected"
                )

                self.safety_status_changed.emit(bool(safety))

                print(f"[PLC] Connection: {connection}, Safety: {safety}")

        except Exception as e:
            print(f"[Status Read Error] {e}")

    def handle_connection_lost(self):
        if self.is_connected:
            print("🔴 CONNECTION LOST")

            self.is_connected = False
            self.activate_safety()

            self.connection_status_changed.emit(False, "Connection Lost")

            # try:
            #     if self.client:
            #         self.client.close()
            # except:
            #     pass
            
    def check_heartbeat_threshold(self):
        """Cek threshold heartbeat untuk safety"""
        if self.heartbeat_failures >= self.heartbeat_timeout:
            print(f"[Heartbeat] Threshold reached! Activating safety...")
            self.activate_safety()
            
    # ==========================================
    # LEVEL 3: SAFETY TIMEOUT (3s)
    # ==========================================
    def reset_safety_timer(self):
        """Reset safety timer (dipanggil saat heartbeat OK)"""
        if self.is_connected and not self.safety_active:
            self.safety_timer.start(self.safety_timeout)
            
    def activate_safety(self):
        """Aktifkan safety - matikan semua output"""
        if not self.safety_active:
            self.safety_active = True
            self.safety_status_changed.emit(True)
            
            # Tulis safety status ke PLC
            if self.client and self.is_connected:
                try:
                    self.client.write_register(self.REG_SAFETY_STATUS, 1, unit=self.unit_id)
                    self.client.write_register(self.REG_CONNECTION_STATUS, 0, unit=self.unit_id)
                except:
                    pass
                    
            self.connection_status_changed.emit(False, "SAFETY ACTIVE - Outputs disabled")
            print("🔴 SAFETY ACTIVATED - All servo outputs disabled")
            
    def deactivate_safety(self):
        """Deactivate safety (recover)"""
        if self.safety_active:
            self.safety_active = False
            self.safety_status_changed.emit(False)
            
            # Reset failures
            self.quick_check_failures = 0
            self.heartbeat_failures = 0
            
            # Tulis status ke PLC
            if self.client and self.is_connected:
                try:
                    self.client.write_register(self.REG_SAFETY_STATUS, 0, unit=self.unit_id)
                    self.client.write_register(self.REG_CONNECTION_STATUS, 1, unit=self.unit_id)
                except:
                    pass
                    
            self.connection_status_changed.emit(True, "Safety deactivated - Normal operation")
            print("🟢 SAFETY DEACTIVATED - Normal operation resumed")
            
    def disconnect(self):
        """Disconnect dari PLC"""
        self.stop_monitoring()
        self.activate_safety()
        
        if self.client:
            self.client.close()
            self.client = None
            
        self.is_connected = False
        self.connection_status_changed.emit(False, "Disconnected")
        print("Disconnected from PLC")
            
    def get_status(self):
        """Dapatkan status lengkap"""
        return {
            'connected': self.is_connected,
            'safety_active': self.safety_active,
            'quick_check_failures': self.quick_check_failures,
            'heartbeat_failures': self.heartbeat_failures,
            'heartbeat_counter': self.heartbeat_counter,
            'ip': self.ip_address,
            'port': self.port
        }