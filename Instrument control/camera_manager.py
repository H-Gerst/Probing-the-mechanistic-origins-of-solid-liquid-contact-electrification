import cv2
import csv
import time
import asyncio
import threading
from pathlib import Path
from datetime import datetime
import queue # ADD ME

class CameraController:
    """
    Asynchronous camera manager for 4K video capture with XVID encoding,
    dynamic cropping, and absolute per-frame timestamp logging.
    """

    def __init__(self, cam_no: int = 0, fps: int = 30, show_preview: bool = True, roi: tuple = None):
        """
        roi: Opteional tuple defining (x_min, y_min, x_max, y_max)
             Example: (960, 540, 2880, 1620)
        """
        self.cam_no = cam_no
        self.fps = fps
        self.show_preview = show_preview
        self.roi = roi  # (x1, y1, x2, y2)

        self.camera = None
        self.writer = None
        self.recording = False
        self.thread = None

        self.preview_queue = queue.Queue(maxsize=1) # ADD ME

        self.camera_start_time = None
        self.frame_count = 0
        self.frame_timestamps = []

    def prepare_camera(self, width: int = 3840, height: int = 2160) -> bool:
        """Pre-warms hardware to eliminate start latency during experiments."""
        print(f"[Camera] Pre-warming hardware on index {self.cam_no}...")
        self.camera = cv2.VideoCapture(self.cam_no, cv2.CAP_DSHOW)

        if not self.camera.isOpened():
            print("[Camera Error] Failed to connect to camera device.")
            return False

        # Request native sensor parameters
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.camera.set(cv2.CAP_PROP_FPS, self.fps)

        print(f"[Camera] Device initialized at {width}x{height} @ {self.fps} FPS.")
        return True

    def _record_loop(self, exp_name: str, day: str):
        """Background thread executing the core capture loop."""
        save_dir = Path(f"New_data/{day}")
        save_dir.mkdir(parents=True, exist_ok=True)
        self.frame_count = 0
        self.frame_timestamps = []

        video_path = save_dir / f"{exp_name}_video.avi"
        timestamp_path = save_dir / f"{exp_name}_frame_timestamps.csv"

        full_width = int(self.camera.get(cv2.CAP_PROP_FRAME_WIDTH))
        full_height = int(self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Handle cropping boundaries & calculate writer output resolution
        if self.roi:
            x1, y1, x2, y2 = self.roi
            x1, x2 = max(0, x1), min(full_width, x2)
            y1, y2 = max(0, y1), min(full_height, y2)

            write_width = x2 - x1
            write_height = y2 - y1
            print(f"[Camera] Cropping enabled: [{x1}:{x2}, {y1}:{y2}] -> Resolution: {write_width}x{write_height}")
        else:
            write_width, write_height = full_width, full_height
            print(f"[Camera] Full frame recording: {write_width}x{write_height}")

        # XVID Codec Writer
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        self.writer = cv2.VideoWriter(str(video_path), fourcc, self.fps, (write_width, write_height))

        # Preview scaling setup
        temp_h, temp_w = int(write_height * 0.3), int(write_width * 0.3)


        # Log camera execution start time
        self.camera_start_time = f'r{datetime.now().strftime("%H:%M:%S.%f")}'
        self.recording = True

        for _ in range(5):
            self.camera.grab()

        print(f"[Camera] Buffer Purged. recording started at {self.camera_start_time}")

        print(f"[Camera] Recording started ({self.fps} FPS / XVID). Target: {video_path}")

        try:
            while self.recording:
                # ret, frame = self.camera.read() # frame = image matrix that has been processed
                perf_counter = time.perf_counter()

                # Capture absolute timestamp
                frame_time = datetime.now().strftime("%H:%M:%S.%f")

                grabbed = self.camera.grab()
                if not grabbed:
                    print("[Camera Warning] Frame dropped or unreadable.")

                ret, frame = self.camera.retrieve()
                if not ret:
                    continue

                # Slicing frame array if ROI is configured
                if self.roi:
                    output_frame = frame[y1:y2, x1:x2]
                else:
                    output_frame = frame

                # Write frame to .avi
                self.writer.write(output_frame)
                self.frame_count += 1

                # Record per-frame timestamp metadata
                self.frame_timestamps.append((self.frame_count, f'r{frame_time}', perf_counter))

                # Optional GUI preview
                if self.show_preview:
                    try:
                        self.preview_queue.put_nowait(output_frame)
                    except queue.Full:
                        pass
                    # resized = cv2.resize(output_frame, (temp_w, temp_h))
                    # cv2.imshow('Camera Preview', resized)
                    # if not self.preview_queue.full(): # ADD ME
                    #     self.preview_queue.put(resized)
                    # if cv2.waitKey(1) & 0xFF == ord('q'):
                    #     self.recording = False
                    #     break

        finally:
            self._cleanup(timestamp_path)

    def start_preview_loop(self, state=None): # ADD ME
        """Must be called from the MAIN THREAD."""
        if not self.show_preview:
            return

        cv2.namedWindow('Live droplet', cv2.WINDOW_NORMAL)

        while self.recording:
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("[GUI] 'q' pressed on Preview Window. Stopping recording...")
                self.recording = False
                if state:
                    state.signal_shutdown()
                break
            try:
                raw_frame = self.preview_queue.get(timeout=0.02)
                h,w = raw_frame.shape[:2]

                h, w = raw_frame.shape[:2]
                resized = cv2.resize(raw_frame, (int(w * 0.3), int(h * 0.3)))

                cv2.imshow('Camera Preview', resized)
            except queue.Empty:
                continue

        cv2.destroyAllWindows()

    def _cleanup(self, timestamp_path: Path):
        """Flushes data, closes streams, and writes timestamp file to disk."""
        if self.writer:
            self.writer.release()
        if self.camera and self.camera.isOpened():
            self.camera.release()
        if self.show_preview:
            cv2.destroyAllWindows()

        # Save absolute frame timestamps CSV
        with open(timestamp_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Frame", "Absolute_Timestamp", "System_Perf_Counter"])
            writer.writerows(self.frame_timestamps)

        print(f"[Camera] Complete. Total Frames: {self.frame_count}. Timestamps saved -> {timestamp_path}")

    async def start_recording(self, exp_name: str, day: str):
        """Dispatches capture loop onto a background thread."""
        if self.recording:
            return

        if self.camera is None or not self.camera.isOpened():
            if not self.prepare_camera():
                raise RuntimeError("Camera failed to initialize.")

        self.thread = threading.Thread(
            target=self._record_loop,
            args=(exp_name, day),
            daemon=True
        )
        self.thread.start()
        await asyncio.sleep(0)

    def stop_recording(self):
        """Gracefully halts capture loop."""
        self.recording = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)