import csv
from pathlib import Path


class ExperimentLogger:
    def __init__(self, day: str, sample_name: str, sample_state: str, pos: str, rep: str, jacket: str = "New_data"):
        self.day = day
        self.dir_path = Path(f"{jacket}/{day}")
        self.exp_name = f"{sample_name}_{sample_state}_{pos}_{rep}"
        self.csv_path = self.dir_path / f"{self.exp_name}.csv"

        self.dir_path.mkdir(exist_ok=True, parents=True)
        self._init_csv()

    def _init_csv(self):
        with open(self.csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["resp_vol", "resp_time", "status"])

    def log_vol(self, row_data: dict):
        with open(self.csv_path, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["resp_vol", "resp_time", "status"])
            writer.writerow(row_data)

    def save_timestamps(self, lv_time, pump_time, video_time):
        time_file = self.dir_path / f"{self.exp_name}_times.csv"
        with open(time_file, mode='w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Device', 'Start_time'])
            writer.writerow(['lv', lv_time])
            writer.writerow(['pump', pump_time])
            writer.writerow(['video', video_time])
        print(f"[Storage] Telemetry timestamps written to {time_file}")