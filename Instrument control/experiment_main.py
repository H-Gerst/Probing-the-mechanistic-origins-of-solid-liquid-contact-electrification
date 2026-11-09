import asyncio
import time
import keyboard
from datetime import datetime

from state_manager import ExperimentState
from arduino_pump_manager import ArduinoPumpController
from camera_manager import CameraController
from network_manager import LabVIEWServer
from storage_manager import ExperimentLogger


async def pump_loop(
        state: ExperimentState,
        pump: ArduinoPumpController,
        logger: ExperimentLogger,
        # Configuration dicts for initial vs cycle operations
        syringe_config: dict = None,
        initial_config: dict = None,
        pulse_config: dict = None,
        interval: float = 0.1
):
    # Default hardware and syringe spects
    syringe_cfg = syringe_config or {"diameter_mm": 14.5, "microsteps": 16}
    initial_cfg = initial_config or {
        "direction": "WITHDRAW",
        "rate": 600.0,
        "unit": "UL_MIN",
        "volume_ml": 0.5,
        "duration_sec": 10.0
    }

    pulse_cfg = pulse_config or {
        "n_pulses": 1,
        "pulse_rate": 600.0,
        "pulse_unit": "UL_MIN",
        "pulse_vol_ml": 0.005,
        "on_sec": 5.0,
        "standby_sec": 5.0,
        "total_cycles": 2
    }

    total_cycles = 1
    current_cycle = 1
    current_pulse = 1

    # ------------------------------------------------------------------
    # set syringe parameters
    # ------------------------------------------------------------------
    print("\n[Pump Setup] Configuring Hardware Syringe Parameters...")
    await pump.set_diameter(syringe_cfg["diameter_mm"])
    await pump.set_microsteps(syringe_cfg["microsteps"])


    # ------------------------------------------------------------------
    # Set first phase
    # ------------------------------------------------------------------
    print(f"\n[Pump Setup] Loading initial infuse ({initial_cfg['rate']} {initial_cfg['unit']})...")
    await pump.set_direction(initial_cfg["direction"])
    await pump.set_rate(initial_cfg["rate"], initial_cfg["unit"])
    await pump.set_volume(initial_cfg["volume_ml"])

    await pump.start_pump()


    current_phase = 'initial'
    subphase = 'standby'
    is_armed = False

    phase_start = 0.0# time.time()
    phase_end = 0.0 # phase_start + initial_cfg["initial_duration_sec"]


    print("\n[Pump Loop] Syringe pump is armed and waiting for LabVIEW START command...")

    while not state.is_shutdown:
        loop_start = time.time()

        if keyboard.is_pressed("q"):
            state.signal_shutdown()
            break

        if state.is_running and not state.is_paused:
            if not is_armed:
                print("\n[LabVIEW Trigger] Signal received! Starting Initial Infuse...")
                is_armed = True
                subphase = 'on'
                phase_start = time.time()
                phase_end = phase_start + initial_cfg["duration_sec"]
                await pump.start_pump()

                # --- PHASE 1: INITIAL PHASE ---
            elif current_phase == 'initial':
                if loop_start >= phase_end:
                    print(
                        f"\n[Phase Transition] Initial phase complete. Switching to Infuse Pulses (Cycle {current_cycle})...")
                    await pump.stop_pump()

                    current_phase = 'infuse'
                    current_pulse = 1
                    subphase = 'on'

                    # Configure Infuse Motor Settings
                    await pump.set_direction("INFUSE")
                    await pump.set_rate(pulse_cfg["pulse_rate"], pulse_cfg["pulse_unit"])
                    await pump.set_volume(pulse_cfg["pulse_vol_ml"])
                    await pump.start_pump()
                    phase_start = time.time()
                    phase_end = phase_start + pulse_cfg["on_sec"]

                # --- PHASE 2: INFUSE PULSES ---
            elif current_phase == 'infuse':
                if loop_start >= phase_end:
                    if subphase == 'on':
                        await pump.stop_pump()
                        subphase = 'standby'
                        phase_start = time.time()
                        phase_end = phase_start + pulse_cfg["standby_sec"]

                    elif subphase == 'standby':
                        if current_pulse < pulse_cfg["n_pulses"]:
                            current_pulse += 1
                            subphase = 'on'
                            print(f"[Infuse Pulse] Pulse {current_pulse}/{pulse_cfg['n_pulses']} (Cycle {current_cycle})")

                            await pump.set_rate(pulse_cfg["pulse_rate"], pulse_cfg["pulse_unit"])
                            await pump.set_volume(pulse_cfg["pulse_vol_ml"])
                            await pump.start_pump()

                            phase_start = time.time()
                            phase_end = phase_start + pulse_cfg["on_sec"]
                        else:
                            # Transition to Withdraw Phase
                            print(
                                f"\n[Phase Transition] Infuse Pulses Done. Switching to Withdraw Pulses (Cycle {current_cycle})...")
                            current_phase = 'withdraw'
                            current_pulse = 1
                            subphase = 'on'

                            # Hardware Re-direction to WITHDRAW
                            await pump.set_direction("WITHDRAW")
                            await pump.set_rate(pulse_cfg["pulse_rate"], pulse_cfg["pulse_unit"])
                            await pump.set_volume(pulse_cfg["pulse_vol_ml"])
                            await pump.start_pump()

                            phase_start = time.time()
                            phase_end = phase_start + pulse_cfg["on_sec"]

                # --- PHASE 3: WITHDRAW PULSES ---
            elif current_phase == 'withdraw':
                if loop_start >= phase_end:
                    if subphase == 'on':
                        await pump.stop_pump()
                        subphase = 'standby'
                        phase_start = time.time()
                        phase_end = phase_start + pulse_cfg["standby_sec"]

                    elif subphase == 'standby':
                        if current_pulse < pulse_cfg["n_pulses"]:
                            current_pulse += 1
                            subphase = 'on'
                            print(
                                f"[Withdraw Pulse] Pulse {current_pulse}/{pulse_cfg['n_pulses']} (Cycle {current_cycle})")

                            await pump.set_rate(pulse_cfg["pulse_rate"], pulse_cfg["pulse_unit"])
                            await pump.set_volume(pulse_cfg["pulse_vol_ml"])
                            await pump.start_pump()

                            phase_start = time.time()
                            phase_end = phase_start + pulse_cfg["on_sec"]
                        else:
                            # Loop back for next cycle or finish
                            if current_cycle < total_cycles:
                                current_cycle += 1
                                print(
                                    f"\n[Phase Transition] Cycle {current_cycle - 1} Complete. Starting Cycle {current_cycle} (Infuse)...")
                                current_phase = 'infuse'
                                current_pulse = 1
                                subphase = 'on'

                                await pump.set_direction("INFUSE")
                                await pump.set_rate(pulse_cfg["pulse_rate"], pulse_cfg["pulse_unit"])
                                await pump.set_volume(pulse_cfg["pulse_vol_ml"])
                                await pump.start_pump()

                                phase_start = time.time()
                                phase_end = phase_start + pulse_cfg["on_sec"]
                            else:
                                print("\n[Phase Transition] All Infuse/Withdraw cycles completed successfully!")
                                await pump.stop_pump()
                                current_phase = 'complete'
                                subphase = ''

                # Construct status string (e.g., initial_on, infuse_standby, withdraw_on, complete)
            status_str = f"{current_phase}_{subphase}".strip('_')

            telemetry = await pump.get_status()
            telemetry['status'] = status_str

            state.update_volume(telemetry['resp_vol'])
            logger.log_vol(telemetry)

            # Handle Pause / LabVIEW Standby States
        else:
            if state.is_paused:
                status_str = "paused"
            else:
                status_str = "initial_standby"

            logger.log_vol({
                "resp_vol": "0.000",
                "resp_time": f'r{datetime.now().strftime("%H:%M:%S.%f")}',
                "status": status_str
            })

        elapsed = time.time() - loop_start
        await asyncio.sleep(max(0.0, interval - elapsed))


async def main(camera_holder: dict, state: ExperimentState): # ADD ME
    print("\n==================================================")
    print("       STARTING EXPERIMENT INITIALIZATION         ")
    print("==================================================")

    print("\n[Sequence 1/5] Initializing Experiment Logger...")
    today = "22_07"
    logger = ExperimentLogger(day=today, sample_name="c", sample_state="etoh", pos="2", rep="1")
    print("  └── Logger Ready. Recording path configured.")

    print("\n[Sequence 2/5] Connecting to Syringe Pump...")
    try:
        pump_name = "COM4"
        pump = ArduinoPumpController(pump_name)
        pump.connect()
        print(f"  └── Syringe Pump Connected Successfully {pump_name}).")
    except Exception as e:
        print(f"  └── [ERROR] Failed to connect to Syringe Pump: {e}")
        raise

    print("\n[Sequence 3/5] Initializing Camera System...")

    # Optional crop box: (X1, Y1, X2, Y2). Set to None if you want the full 4K frame.
    CROP_BOX = (960, 540, 2880, 1620)

    try:
        camera = CameraController(
            cam_no=0,
            fps=30,
            show_preview=True,
            roi=CROP_BOX
        )
        camera.prepare_camera()
        camera_holder["instance"] = camera
        print("  └── Camera Initialized and Ready for Preview.")
    except Exception as e:
        print(f"  └── [ERROR] Failed to initialize Camera: {e}")
        raise

    print("\n[Sequence 4/5] Starting LabVIEW Network Server (Port 8089)...")
    try:
        server = LabVIEWServer(port=8089)
        await server.start(state, pump, camera, logger, logger.exp_name, today)
        print("  └── LabVIEW Server Listening for Connections.")
    except Exception as e:
        print(f"  └── [ERROR] Failed to start LabVIEW Server: {e}")
        raise

    print("\n[Sequence 5/5] Loading Experiment Profiles...")


    # 5. Run the main hardware execution loop wrapped safely in try/finally
    try:
        await pump_loop(
            state,
            pump,
            logger,
        )

    finally:
        # Guaranteed cleanup on 'q' press, LabVIEW stop, or unexpected errors
        print("\n[System] Running clean shutdown sequence...")
        camera.stop_recording()

        try:
            await pump.stop_pump()
        except Exception as e:
            print(f"[Pump Error] Could not stop pump: {e}")

        await server.stop()
        print("  └── LabVIEW Server Stopped.")

        # Extract timestamps
        lv_time = server.lv_start_time if server.lv_start_time else "N/A"
        logger.save_timestamps(lv_time, pump.pump_start_time, camera.camera_start_time)
        print("  └── Timestamps Saved. Cleanup Complete.\n")


import threading

if __name__ == '__main__':
    state = ExperimentState()
    camera_holder = {"instance": None}

    def run_async_main():
        try:
            asyncio.run(main(camera_holder, state))
        except Exception as e:
            print(f"\n[System Error] Initialization/Execution failed: {e}")

    # Start the async system on a background thread
    async_thread = threading.Thread(target=run_async_main, daemon=True)
    async_thread.start()

    print("[Main Thread] Waiting for background hardware initialization...")
    while camera_holder["instance"] is None and async_thread.is_alive():
        time.sleep(0.05)

    camera = camera_holder["instance"]

    # Start main thread GUI preview loop
    if isinstance(camera, CameraController) and camera.show_preview:
        print("[Main Thread] Launching OpenCV Preview Window...")
        try:
            camera.start_preview_loop(state=state)
        except KeyboardInterrupt:
            print("\n[User Interrupt] Shutting down...")
        finally:
            async_thread.join(timeout=2.0)