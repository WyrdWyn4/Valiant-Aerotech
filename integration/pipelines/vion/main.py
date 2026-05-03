from pathlib import Path
from datetime import datetime
import csv
import cv2


def capture_task2_photos(
    team_name: str,
    camera_index: int = 0,
    output_dir: str = "task2_photos",
):
    """
    Manual Task Two photo capture tool.

    Workflow:
    - Operator manually flies the drone.
    - Operator manually shoots water at target.
    - Ground-station user presses ENTER.
    - Script saves the current camera frame as a target photo.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    log_file = output_path / "task2_photo_log.csv"

    # Use CAP_DSHOW on Windows to reduce camera startup issues.
    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)

    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera index {camera_index}")

    target_number = 1

    # Create CSV log if it does not exist
    if not log_file.exists():
        with open(log_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["target_number", "filename", "timestamp"])

    print("Task Two photo capture started.")
    print("Press ENTER in the camera window to save a photo.")
    print("Press Q to quit.")

    while True:
        ret, frame = cap.read()

        if not ret:
            print("Warning: Could not read frame from camera.")
            continue

        display_frame = frame.copy()

        cv2.putText(
            display_frame,
            f"Next photo: Target {target_number} | ENTER = save | Q = quit",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
        )

        cv2.imshow("Task Two Camera Capture", display_frame)

        key = cv2.waitKey(1) & 0xFF

        # ENTER key
        if key == 13:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

            filename = f"Task_2_{team_name}_target_{target_number}.jpg"
            filepath = output_path / filename

            cv2.imwrite(
                str(filepath),
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, 95],
            )

            with open(log_file, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([target_number, filename, timestamp])

            print(f"Saved: {filepath}")

            target_number += 1

        # Q key to quit
        elif key == ord("q"):
            print("Stopping photo capture.")
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    capture_task2_photos(
        team_name="ValiantAerotech",
        camera_index=0,
        output_dir="task2_photos",
    )