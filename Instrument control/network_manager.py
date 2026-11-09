import asyncio
from datetime import datetime
from state_manager import ExperimentState


class LabVIEWServer:
    """Asynchronous server handling network communications with LabVIEW."""

    def __init__(self, host='localhost', port=8089):
        self.host = host
        self.port = port
        self.server = None
        self.lv_start_time = None

    async def start(self, state: ExperimentState, pump, camera, data_logger, exp_name, day):
        self.server = await asyncio.start_server(
            lambda r, w: self._handle_client(r, w, state, pump, camera, data_logger, exp_name, day),
            self.host, self.port
        )
        print(f"[Network] LabVIEW Server running on {self.host}:{self.port}")

    async def _handle_client(self, reader, writer, state: ExperimentState, pump, camera, data_logger, exp_name, day):
        print(f"[Network] LabVIEW Client connected.")

        try:
            while not state.is_shutdown:
                data = await reader.read(1024)
                if not data:
                    break

                print(f"[Network] Incoming: {data}")

                if b'START' in data:
                    writer.write(b'GO')
                    self.lv_start_time = f'r{datetime.now().strftime("%H:%M:%S.%f")}'
                    await writer.drain()

                    if not state.is_running:
                        await pump.start_pump()
                        start_time = f'r{datetime.now().strftime("%H:%M:%S.%f")}'
                        pump.pump_start_time = start_time

                        data_logger.log_vol({"resp_vol": 0, "resp_time": start_time, "status": "Start"})
                        state.start_experiment()
                        await camera.start_recording(exp_name, day)

                elif b'STOP' in data:
                    writer.write(b'OK')
                    await writer.drain()
                    state.signal_shutdown()
                    break

                elif b'2026' in data:
                    self.lv_start_time = data.decode('utf-8')


        except Exception as e:
            print(f"[Network Error] Connection failure: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
            print("[Network] Connection closed.")

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()