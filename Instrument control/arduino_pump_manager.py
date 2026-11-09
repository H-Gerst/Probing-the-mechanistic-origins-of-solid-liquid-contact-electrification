import asyncio
import serial
from datetime import datetime
import re

class ArduinoPumpController:
    """Controller matching the Arduino CNC Shield/DRV8825 C++ SerialCommandHandler."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self.pump_start_time = None

    def connect(self):
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout
            )
            print(f"[Pump] Connected to pump on {self.port}")
        except serial.SerialException as e:
            print(f"[Pump Error] Failed to open port {self.port}: {e}")
            raise

    async def send_command(self, cmd_string: str):
        if not self.ser or not self.ser.is_open:
            raise ConnectionError("[Pump Error] Serial connection is missing.")

        if not cmd_string.endswith('\n'):
            cmd_string += '\n'

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.ser.write, cmd_string.encode('ascii'))
        await asyncio.sleep(0.05)

        resp_time = f'r{datetime.now().strftime("%H:%M:%S.%f")}'
        raw_resp = await loop.run_in_executor(None, self.ser.read_all)
        response = raw_resp.decode('ascii').strip()

        return response, resp_time

    # --- Configuration Methods ---
    async def set_diameter(self, dia_mm: float):
        """Syntax: SET DIA <diameter_mm>"""
        return await self.send_command(f"SET DIA {dia_mm:.2f}")

    async def set_volume(self, vol_ml: float):
        """Syntax: SET VOL <volume_mL>"""
        return await self.send_command(f"SET VOL {vol_ml:.3f}")

    async def set_rate(self, rate: float, unit: str = "UL_MIN"):
        """Syntax: SET RATE <value> <unit> (ML_MIN, ML_HR, UL_MIN, UL_HR)"""
        return await self.send_command(f"SET RATE {rate} {unit.upper()}")

    async def set_direction(self, direction: str):
        """Syntax: SET DIR <INFUSE|WITHDRAW>"""
        dir_str = "INFUSE" if direction.upper().startswith("INF") else "WITHDRAW"
        return await self.send_command(f"SET DIR {dir_str}")

    async def set_microsteps(self, steps: int):
        """Syntax: SET MICROSTEPS <1|2|4|8|16|32>"""
        return await self.send_command(f"SET MICROSTEPS {steps}")

    # --- Execution & Control ---
    async def start_pump(self):
        """Syntax: START"""
        self.pump_start_time = datetime.now().strftime("%H:%M:%S.%f")
        return await self.send_command("START")

    async def stop_pump(self):
        """Syntax: STOP"""
        return await self.send_command("STOP")

    async def pause_pump(self):
        """Syntax: PAUSE"""
        return await self.send_command("PAUSE")

    async def resume_pump(self):
        """Syntax: RESUME"""
        return await self.send_command("RESUME")

    async def get_status(self):
        """Syntax: STATUS"""
        resp_str, resp_time = await self.send_command("STATUS")
        return {"resp_vol": resp_str, "resp_time": resp_time}

        match = re.search(r"Dispensed Vol:\s+([\d.]+)", resp_str)
        dispensed_vol = match.group(1) if match else "0.000"

        return {"resp_vol": dispensed_vol, "resp_time": resp_time}


# pump = SyringePumpController("COM3")
# pump.connect()