import threading
import time


class ExperimentState:
    """Thread-safe state manager replacing global flags."""

    def __init__(self):
        self._running = threading.Event()
        self._shutdown = threading.Event()
        self._paused = threading.Event()

        self.lock = threading.Lock()
        self.last_volume = 0.0

    @property
    def is_running(self) -> bool:
        return self._running.is_set()

    @property
    def is_shutdown(self) -> bool:
        return self._shutdown.is_set()

    @property
    def is_paused(self) -> bool:
        return self._paused.is_set()

    def start_experiment(self):
        self._running.set()

    def stop_experiment(self):
        self._running.clear()

    def signal_shutdown(self):
        self._running.clear()
        self._shutdown.set()

    def set_paused(self, paused: bool):
        if paused:
            self._paused.set()
        else:
            self._paused.clear()

    def update_volume(self, vol):
        with self.lock:
            self.last_volume = vol

    def get_volume(self):
        with self.lock:
            return self.last_volume