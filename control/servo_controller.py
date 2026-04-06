# servo_controller.py
import struct
from pymodbus.exceptions import ModbusException
from pymodbus.payload import BinaryPayloadBuilder
from pymodbus.constants import Endian

class ServoController:
    def __init__(self, plc_connection):
        """
        plc_connection = instance dari PLCConnection
        """
        self.plc = plc_connection
        
        # Debug: cek apakah plc_connection valid
        print(f"ServoController initialized with PLC: {self.plc}")
        if self.plc:
            print(f"PLC Connected: {self.plc.is_connected}")
            print(f"PLC Client: {self.plc.client}")
        
        # ============================================
        # COIL ADDRESSES (Bit) - Untuk perintah
        # ============================================
        self.COIL_CMD_EN    = 1025 - self.plc.offset_addres   # Enable/Disable Servo (0X1025)
        self.COIL_CMD_HOME  = 1026 - self.plc.offset_addres   # Homing (0X1026)
        self.COIL_CMD_RUN   = 1027 - self.plc.offset_addres   # Run (0X1027)
        self.COIL_CMD_STOP  = 1028 - self.plc.offset_addres   # Stop (0X1028)
        self.COIL_CMD_RESET = 1033 - self.plc.offset_addres   # Reset (0X1033)
        
        # Status coils dari PLC
        self.COIL_PLAYING_COMPLETED = 1035 - self.plc.offset_addres   # Playing completed (0X1035)
        
        # ============================================
        # HOLDING REGISTER ADDRESSES (4X)
        # ============================================
        # Heartbeat registers
        self.REG_QUICK_CHECK = 2561 - self.plc.offset_addres      # 4X2561
        self.REG_HEARTBEAT_WRITE = 2562 - self.plc.offset_addres  # 4X2562
        self.REG_HEARTBEAT_READ = 2563 - self.plc.offset_addres   # 4X2563
        self.REG_CONNECTION_STATUS = 2564 - self.plc.offset_addres # 4X2564
        self.REG_SAFETY_STATUS = 2565  - self.plc.offset_addres   # 4X2565
        
        # Servo target positions (REAL - 32-bit float)
        # Setiap REAL membutuhkan 2 holding register (32-bit)
        self.REG_SERVO_TARGET_0 = 2569 - self.plc.offset_addres   # Servo 1 target (2 registers: 2569-2570) 4X2569
        self.REG_SERVO_TARGET_1 = 2571 - self.plc.offset_addres   # Servo 2 target (2 registers: 2571-2572) 4X2571
        self.REG_SERVO_TARGET_2 = 2573 - self.plc.offset_addres   # Servo 3 target (2 registers: 2573-2574) 4X2573
        
        # Status registers (BOOL arrays - masing-masing 1 register untuk 16 bit)
        # Register 2575: EnStatus[0], EnStatus[1], EnStatus[2] (bit 0,1,2) 4X2575
        self.REG_EN_STATUS = 2575 - self.plc.offset_addres 
        
        # Register 2577: HomeStatus[0], HomeStatus[1], HomeStatus[2] (bit 0,1,2) 4X2577
        self.REG_HOME_STATUS = 2577 - self.plc.offset_addres 
        
        # Register 2579: RunStatus[0], RunStatus[1], RunStatus[2] (bit 0,1,2) 4X2579
        self.REG_RUN_STATUS = 2579 - self.plc.offset_addres 
        
        # Register 2581: StopStatus[0], StopStatus[1], StopStatus[2] (bit 0,1,2) 4X2581
        self.REG_STOP_STATUS = 2581 - self.plc.offset_addres 
        
        # Register 2583: ResetStatus[0], ResetStatus[1], ResetStatus[2] (bit 0,1,2) 4X2583
        self.REG_RESET_STATUS = 2583 - self.plc.offset_addres 
        
        # Register 2585: TotalFrame 4X2585
        self.REG_TOTAL_FRAME = 2585 - self.plc.offset_addres 
        
        # Register 2586: FrameIndex 4X2586
        self.REG_FRAME_INDEX = 2586 - self.plc.offset_addres 

    # FUNGSI WRITEPOS
    def write_writepos(self, values):
        """
        Write ARRAY WritePos [0..2] ke PLC
        
        Args:
            values: list/tuple of 3 float values (s1, s2, s3)
                   Range: 0-1000 (akan dikonversi ke float)
        
        Contoh:
            write_writepos([500.0, 500.0, 500.0])  # Posisi netral
            write_writepos([750.0, 250.0, 500.0])  # Roll kiri
        """
        if not self.plc or not self.plc.is_connected:
            print("❌ PLC not connected, cannot write position")
            return False
            
        if self.plc.safety_active:
            print("❌ Safety active, cannot write position")
            return False
            
        if len(values) != 3:
            raise ValueError("WritePos harus 3 nilai")
            
        try:
            # Konversi nilai ke float
            float_values = [float(v) for v in values]
            
            print(f"📝 Writing positions to PLC: S1={float_values[0]:.1f}, S2={float_values[1]:.1f}, S3={float_values[2]:.1f}")
            
            # Method 1: Menggunakan BinaryPayloadBuilder (Modbus)
            builder = BinaryPayloadBuilder(
                byteorder=Endian.Big,
                wordorder=Endian.Little
            )
            
            for v in float_values:
                builder.add_32bit_float(v)
                
            payload = builder.to_registers()
            
            # Address start (0-based untuk write_registers)
            start_address = self.REG_SERVO_TARGET_0
            
            # Tulis ke PLC
            result = self.plc.client.write_registers(
                start_address, 
                payload, 
                unit=self.plc.unit_id
            )
            
            if result.isError():
                print(f"❌ Failed to write positions: {result}")
                return False
                
            print(f"✓ Positions written successfully")
            return True
            
        except Exception as e:
            print(f"❌ Write position error: {e}")
            return False
            
    def write_writepos_alternative(self, s1, s2, s3):
        """
        Alternative method: Write 3 float values individually
        Menggunakan write_register dengan konversi manual
        """
        if not self.plc or not self.plc.is_connected:
            return False
            
        try:
            print(f"📝 Writing positions: S1={s1:.1f}, S2={s2:.1f}, S3={s3:.1f}")
            
            # Konversi float ke 2 registers (32-bit)
            def float_to_registers(value):
                packed = struct.pack('>f', value)
                int_val = struct.unpack('>I', packed)[0]
                high = (int_val >> 16) & 0xFFFF
                low = int_val & 0xFFFF
                return [high, low]
            
            # Tulis masing-masing posisi
            # WritePos[0] di address 2573-2574
            regs_s1 = float_to_registers(s1)
            self.client.write_registers(2573 - 1, regs_s1, unit=self.slave_id)
            
            # WritePos[1] di address 2575-2576
            regs_s2 = float_to_registers(s2)
            self.client.write_registers(2575 - 1, regs_s2, unit=self.slave_id)
            
            # WritePos[2] di address 2577-2578
            regs_s3 = float_to_registers(s3)
            self.client.write_registers(2577 - 1, regs_s3, unit=self.slave_id)
            
            return True
            
        except Exception as e:
            print(f"❌ Write position error: {e}")
            return False

    # =========================
    # INTERNAL FUNCTIONS
    # =========================
    def _write_coil(self, address, value):
        """Tulis ke coil (bit) - 0X address"""
        if not self.plc:
            print("❌ PLC connection object is None")
            return False
            
        if not self.plc.is_connected:
            print("❌ PLC not connected")
            return False
            
        if self.plc.safety_active:
            print("❌ Safety active - Cannot send command")
            return False
            
        if not self.plc.client:
            print("❌ PLC client is None")
            return False
            
        try:
            print(f"Writing to coil {address}: {value}")
            result = self.plc.client.write_coil(
                address,
                bool(value),
                unit=self.plc.unit_id
            )
            
            if result.isError():
                print(f"❌ Failed write coil: {result}")
                return False
                
            print(f"✓ Write successful")
            return True
            
        except Exception as e:
            print(f"❌ Write error: {e}")
            return False
            
    def _write_register(self, reg, value):
        """Tulis ke holding register (4X)"""
        if not self.plc or not self.plc.is_connected or not self.plc.client:
            print("❌ PLC not connected")
            return False
            
        if self.plc.safety_active:
            print("❌ Safety active")
            return False
            
        try:
            print(f"Writing to register {reg}: {value}")
            result = self.plc.client.write_register(
                reg,
                int(value),
                unit=self.plc.unit_id
            )
            
            if result.isError():
                print(f"❌ Failed write register: {result}")
                return False
                
            print(f"✓ Write successful")
            return True
            
        except Exception as e:
            print(f"❌ Write error: {e}")
            return False
            
    def _write_float_register(self, reg, value):
        """Tulis float ke holding register (2 registers untuk 32-bit float)"""
        if not self.plc or not self.plc.is_connected or not self.plc.client:
            print("❌ PLC not connected")
            return False
            
        if self.plc.safety_active:
            print("❌ Safety active")
            return False
            
        try:
            # Convert float to 32-bit integer
            packed = struct.pack('>f', value)
            int_val = struct.unpack('>I', packed)[0]
            
            # Split into two 16-bit registers
            high = (int_val >> 16) & 0xFFFF
            low = int_val & 0xFFFF
            
            print(f"Writing float {value} to register {reg}: high={high}, low={low}")
            
            # Write both registers
            result = self.plc.client.write_register(reg, high, unit=self.plc.unit_id)
            if result.isError():
                print(f"❌ Failed write high register: {result}")
                return False
                
            result = self.plc.client.write_register(reg + 1, low, unit=self.plc.unit_id)
            if result.isError():
                print(f"❌ Failed write low register: {result}")
                return False
                
            print(f"✓ Write successful")
            return True
            
        except Exception as e:
            print(f"❌ Write error: {e}")
            return False
            
    def _pulse_coil(self, address, duration=0.1):
        """Pulse coil (set True lalu False)"""
        import time
        
        print(f"Pulsing coil {address}")
        if self._write_coil(address, True):
            time.sleep(duration)
            self._write_coil(address, False)
            return True
        return False
        
    def _read_coil(self, address):
        """Baca coil (0X)"""
        if not self.plc or not self.plc.is_connected or not self.plc.client:
            return None
            
        try:
            result = self.plc.client.read_coils(
                address, 1, unit=self.plc.unit_id
            )
            
            if result.isError():
                return None
                
            return result.bits[0]
            
        except Exception as e:
            print(f"❌ Read coil error: {e}")
            return None
            
    def _read_register(self, reg):
        """Baca holding register (4X)"""
        if not self.plc or not self.plc.is_connected or not self.plc.client:
            return None
            
        try:
            result = self.plc.client.read_holding_registers(
                reg, 1, unit=self.plc.unit_id
            )
            
            if result.isError():
                return None
                
            return result.registers[0]
            
        except Exception as e:
            print(f"❌ Read register error: {e}")
            return None
            
    def _read_float_register(self, reg):
        """Baca float dari holding register (2 registers)"""
        if not self.plc or not self.plc.is_connected or not self.plc.client:
            return None
            
        try:
            result = self.plc.client.read_holding_registers(
                reg, 2, unit=self.plc.unit_id
            )
            
            if result.isError():
                return None
                
            # Combine two 16-bit registers into 32-bit integer
            combined = (result.registers[0] << 16) | result.registers[1]
            
            # Convert to float
            packed = struct.pack('>I', combined)
            value = struct.unpack('>f', packed)[0]
            
            return value
            
        except Exception as e:
            print(f"❌ Read float error: {e}")
            return None
            
    def _read_status_bits(self, reg):
        """Baca status bits dari register (untuk array BOOL)"""
        value = self._read_register(reg)
        if value is None:
            return [False, False, False]
            
        # Bit 0 = index 0, Bit 1 = index 1, Bit 2 = index 2
        return [
            bool(value & (1 << 0)),
            bool(value & (1 << 1)),
            bool(value & (1 << 2))
        ]

    # =========================
    # PUBLIC CONTROL FUNCTIONS
    # =========================
    def en_servo(self):
        """Enable servo"""
        print("🔌 Enable servo command")
        return self._write_coil(self.COIL_CMD_EN, True)
        
    def disable_servo(self):
        """Disable servo"""
        print("🔌 Disable servo command")
        return self._write_coil(self.COIL_CMD_EN, False)
        
    def homing(self):
        """Homing command (pulse)"""
        print("⚙️ Homing command")
        return self._pulse_coil(self.COIL_CMD_HOME)
        
    def run(self):
        """Run command (pulse)"""
        print("▶️ Run command")
        return self._pulse_coil(self.COIL_CMD_RUN)
        
    def stop(self):
        """Stop command (pulse)"""
        print("⏹ Stop command")
        return self._pulse_coil(self.COIL_CMD_STOP)
        
    def reset(self):
        """Reset command (pulse)"""
        print("🔄 Reset command")
        return self._pulse_coil(self.COIL_CMD_RESET)
        
    # =========================
    # STATUS READ FUNCTIONS
    # =========================
    def read_enable_status(self):
        """Baca status enable servo (dari register 4X2575)"""
        status = self._read_status_bits(self.REG_EN_STATUS)
        return status  # [EnStatus[0], EnStatus[1], EnStatus[2]]
        
    def read_enable_status_all(self):
        """Baca apakah semua servo enabled"""
        status = self._read_status_bits(self.REG_EN_STATUS)
        return status[0] and status[1] and status[2]
        
    def read_home_status(self):
        """Baca status homing (dari register 4X2577)"""
        return self._read_status_bits(self.REG_HOME_STATUS)
        
    def read_home_status_all(self):
        """Baca apakah semua homing selesai"""
        status = self._read_status_bits(self.REG_HOME_STATUS)
        return status[0] and status[1] and status[2]
        
    def read_run_status(self):
        """Baca status run (dari register 4X2579)"""
        return self._read_status_bits(self.REG_RUN_STATUS)
        
    def read_run_status_all(self):
        """Baca apakah semua run selesai"""
        status = self._read_status_bits(self.REG_RUN_STATUS)
        return status[0] and status[1] and status[2]
        
    def read_stop_status(self):
        """Baca status stop (dari register 4X2581)"""
        return self._read_status_bits(self.REG_STOP_STATUS)
        
    def read_reset_status(self):
        """Baca status reset (dari register 4X2583)"""
        return self._read_status_bits(self.REG_RESET_STATUS)
        
    def read_playing_completed(self):
        """Baca status playing completed (dari coil 0X1035)"""
        return self._read_coil(self.COIL_PLAYING_COMPLETED)
        
    def get_servo_target(self, servo_id=0):
        """Baca target posisi servo (REAL dari 4X2569, 4X2571, 4X2573)"""
        if servo_id == 0:
            return self._read_float_register(self.REG_SERVO_TARGET_0)
        elif servo_id == 1:
            return self._read_float_register(self.REG_SERVO_TARGET_1)
        elif servo_id == 2:
            return self._read_float_register(self.REG_SERVO_TARGET_2)
        return None
        
    def get_all_servo_targets(self):
        """Baca semua target posisi servo"""
        s1 = self._read_float_register(self.REG_SERVO_TARGET_0)
        s2 = self._read_float_register(self.REG_SERVO_TARGET_1)
        s3 = self._read_float_register(self.REG_SERVO_TARGET_2)
        return [s1, s2, s3]
        
    def set_servo_target(self, servo_id, value):
        """Set target posisi servo (REAL ke 4X2569, 4X2571, 4X2573)"""
        if servo_id == 0:
            return self._write_float_register(self.REG_SERVO_TARGET_0, value)
        elif servo_id == 1:
            return self._write_float_register(self.REG_SERVO_TARGET_1, value)
        elif servo_id == 2:
            return self._write_float_register(self.REG_SERVO_TARGET_2, value)
        return False
        
    def set_all_servo_targets(self, s1, s2, s3):
        """Set semua target posisi servo"""
        success = True
        if not self._write_float_register(self.REG_SERVO_TARGET_0, s1):
            success = False
        if not self._write_float_register(self.REG_SERVO_TARGET_1, s2):
            success = False
        if not self._write_float_register(self.REG_SERVO_TARGET_2, s3):
            success = False
        return success
        
    def get_total_frame(self):
        """Baca TotalFrame (4X2585)"""
        return self._read_register(self.REG_TOTAL_FRAME)
        
    def get_frame_index(self):
        """Baca FrameIndex (4X2586)"""
        return self._read_register(self.REG_FRAME_INDEX)
        
    def test_connection(self):
        """Test koneksi ke PLC dengan baca register"""
        if not self.plc or not self.plc.is_connected:
            print("❌ PLC not connected")
            return False
            
        try:
            result = self.plc.client.read_holding_registers(
                self.REG_QUICK_CHECK, 1, unit=self.plc.unit_id
            )
            if not result.isError():
                print(f"✓ Test read successful: {result.registers[0]}")
                return True
            else:
                print(f"✗ Test read failed: {result}")
                return False
        except Exception as e:
            print(f"✗ Test error: {e}")
            return False