#!/usr/bin/env python3
"""
GCS-side Autonomous Fire Extinguishing Orchestrator
Runs on the Windows Laptop:
1. Captures `scrcpy` window via `mss`
2. Runs YOLO detection
3. Sends MAVLink velocity commands to the drone
"""

import argparse
import sys
import time
import os
import cv2
import numpy as np

try:
    import mss
    import pygetwindow as gw
    HAVE_MSS = True
except ImportError:
    HAVE_MSS = False

from pymavlink import mavutil
from .config import *
from .visual_servo import VisualServo
from .water_trigger import WaterTrigger
from .gdrive_stub import DriveUploader
from .yolo_detector import YOLODetector, draw_detection_overlay

# Optional: if you need camera orientation from the drone, we can still use it over MAVLink
try:
    from integration.pipelines.task_one.common.servo_map import CameraOrientationReader
except ImportError:
    print("WARNING: Could not import CameraOrientationReader. Defaulting to DOWN camera.")
    CameraOrientationReader = None

STATE_SEARCHING   = 'SEARCHING'
STATE_APPROACHING = 'APPROACHING'
STATE_AIMING       = 'AIMING'
STATE_FIRING       = 'FIRING'
STATE_CAPTURING    = 'CAPTURING'
STATE_UPLOADING    = 'UPLOADING'
STATE_COMPLETE     = 'COMPLETE'

class ScrcpyCamera:
    """Captures the scrcpy window live."""
    def __init__(self, phone_ip=None):
        if not HAVE_MSS:
            raise RuntimeError("mss and pygetwindow are required. Run: pip install mss pygetwindow")
        self.sct = mss.MSS()
        self.window = None
        self.scrcpy_proc = None

        import subprocess
        # Clean up any massive amounts of orphaned scrcpy processes from previous crashes
        if os.name == 'nt':
            subprocess.run(["taskkill", "/IM", "scrcpy.exe", "/F"], capture_output=True)
            
        # Also forcefully close the UI windows directly in case taskkill missed them
        for w in gw.getWindowsWithTitle('ExtinguisherCam'):
            try:
                w.close()
            except Exception:
                pass

        # 0x08000000 = CREATE_NO_WINDOW in Windows, prevents spammy black CMD boxes
        c_flags = 0x08000000 if os.name == 'nt' else 0

        if phone_ip:
            print(f"[ScrcpyCamera] Attempting ADB connect to {phone_ip}...")
            subprocess.run(["adb", "connect", phone_ip], capture_output=True, creationflags=c_flags)

        print("[ScrcpyCamera] Automatically launching scrcpy (background)...")
        try:
            self.scrcpy_proc = subprocess.Popen(
                ["scrcpy", "--stay-awake", "--window-title=ExtinguisherCam"], 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL,
                creationflags=c_flags
            )
        except Exception as e:
            print(f"[ScrcpyCamera] WARNING: Could not launch scrcpy automatically. {e}")

    def cleanup(self):
        if self.scrcpy_proc:
            print("[ScrcpyCamera] Terminating scrcpy background process...")
            self.scrcpy_proc.terminate()
            self.scrcpy_proc.wait()

    def get_frame(self):
        if not self.window:
            # Look for explicit scrcpy window title
            windows = [w for w in gw.getWindowsWithTitle('ExtinguisherCam')]
            if not windows:
                return None
            self.window = windows[0]
            print(f"[ScrcpyCamera] Found securely bound scrcpy window: {self.window.title}")
            
        try:
            bbox = {"top": self.window.top, "left": self.window.left, "width": self.window.width, "height": self.window.height}
        except Exception:
            # The window handle died (user probably clicked the X to close the window)
            self.window = None
            return None
        if bbox["width"] <= 0 or bbox["height"] <= 0:
            return None
            
        sct_img = self.sct.grab(bbox)
        frame = np.array(sct_img)
        # Convert BGRA to BGR
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

class GCSAutoExtinguisher:
    def __init__(self, connection_string, baudrate, sim_mode=False, headless=False, phone_ip=None):
        self.sim = sim_mode
        self.headless = headless
        print(f"[INIT] Connecting to MAVLink on {connection_string} (sim={sim_mode})...")
        
        # We spoof source_system=1 and source_component=191 (Companion computer) 
        # so Mission Planner actually displays our STATUSTEXT logs in the HUD!
        self.master = mavutil.mavlink_connection(
            connection_string, 
            baud=baudrate, 
            source_system=1, 
            source_component=191
        )
        if not self.sim:
            self.master.wait_heartbeat()
            print("[INIT] Heartbeat received!")

        # Request SERVO_OUTPUT_RAW at 10Hz to track camera orientation
        self.master.mav.request_data_stream_send(
            self.master.target_system, self.master.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_EXTRA1, 10, 1
        )
            
        self.servo = VisualServo(self.master)
        self.trigger = WaterTrigger(self.master)
        self.uploader = DriveUploader()
        self.detector = YOLODetector()
        
        if CameraOrientationReader:
            self.cam_reader = CameraOrientationReader(self.master, request_stream=False)
        else:
            self.cam_reader = None

        self.camera = ScrcpyCamera(phone_ip=phone_ip)

        # State tracking
        self.state = STATE_SEARCHING
        self.last_seen_time = 0
        self.frames_without_target = 0
        self.lock_start_time = None
        self.state_start_time = time.time()
        
        self.last_hud_alert_time = 0
        self.target_counter = 0

    def send_hud_message(self, message: str, severity=mavutil.mavlink.MAV_SEVERITY_INFO):
        """Broadcasts a STATUSTEXT message over MAVLink so it appears on Mission Planner UI/Goggles."""
        if self.master:
            text = f"T2: {message}"[:49].encode()  # STATUSTEXT max len is 50
            self.master.mav.statustext_send(severity, text)

    def set_state(self, new_state):
        if self.state != new_state:
            msg = f"STATE: {self.state} -> {new_state}"
            print(f">>> {msg}")
            self.send_hud_message(msg)
            self.state = new_state
            self.state_start_time = time.time()

    def is_camera_looking_down(self):
        if self.cam_reader:
            orientation = self.cam_reader.get_camera_orientation_nonblocking()
            return orientation == 'DOWN' or orientation == 'UNKNOWN'
        return True # Default assume ground target if reader missing

    def loop(self):
        print("\n=== STARTING GCS AUTO-EXTINGUISH LOOP ===")
        print("Waiting for scrcpy window to appear... (Press Ctrl+C to abort)")
        
        try:
            while True:
                # 1. Grab frame from Scrcpy
                frame = self.camera.get_frame()
                if frame is None:
                    time.sleep(0.5)
                    continue

                FRAME_H, FRAME_W = frame.shape[:2]

                # 2. Run YOLO Detection
                det = self.detector.detect_target(frame)
                
                if det:
                    cx, cy, area, bbox = det
                    self.last_seen_time = time.time()
                    self.frames_without_target = 0
                    
                    # Send HUD alert about target periodically (don't spam 20Hz)
                    if time.time() - self.last_hud_alert_time > 1.5:
                        self.send_hud_message(f"AI LOCK: Area {area}px")
                        self.last_hud_alert_time = time.time()
                        
                else:
                    self.frames_without_target += 1

                # 3. Handle state transitions for lost targets
                if self.state in [STATE_APPROACHING, STATE_AIMING]:
                    # Target lost for more than threshold? Revert to searching
                    if self.frames_without_target > MAX_FRAMES_WITHOUT_TARGET:
                        print(f"Target lost for {MAX_FRAMES_WITHOUT_TARGET} frames. Reverting to SEARCHING.")
                        if not self.sim:
                            # Stop moving
                            self.servo.send_velocity_body(0.0, 0.0, 0.0)
                        self.set_state(STATE_SEARCHING)

                # Optional UI overlay
                if not self.headless:
                    overlay = draw_detection_overlay(frame, det)
                    cv2.putText(overlay, f"STATE: {self.state}", (10, 30), 
                                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
                    cv2.imshow("GCS Extinguisher View", overlay)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

                # 4. State Machine Execution
                if self.state == STATE_SEARCHING:
                    # In a full competition run, we'd integrate with pathfinding.
                    # Here we wait until target is detected.
                    if det:
                        self.set_state(STATE_APPROACHING)

                elif self.state == STATE_APPROACHING:
                    if time.time() - self.state_start_time > APPROACH_TIMEOUT_S:
                        print("Approach timed out. Reverting to SEARCHING.")
                        self.set_state(STATE_SEARCHING)
                        continue

                    if det:
                        is_down = self.is_camera_looking_down()
                        
                        # Use PD controller to compute pixel errors
                        vel_right, vel_vertical = self.servo.compute_velocity(cx, cy)

                        # If area is large enough, switch to aiming
                        if area >= TARGET_LOCK_AREA_PX:
                            print(f"[APPROACH] Target large enough (area {area} >= {TARGET_LOCK_AREA_PX}). Switching to AIMING.")
                            self.set_state(STATE_AIMING)
                            continue

                        # Move towards target
                        if not self.sim:
                            if is_down:
                                # Target on ground, top of image = forward. Error is up = negative err_y = forward
                                self.servo.send_velocity_body(-vel_vertical, vel_right, APPROACH_SPEED)
                            else:
                                # Target on wall, moving forward at APPROACH_SPEED, correcting altitude
                                self.servo.send_velocity_body(APPROACH_SPEED, vel_right, vel_vertical)

                elif self.state == STATE_AIMING:
                    if time.time() - self.state_start_time > LOCK_TIMEOUT_S:
                        print("Aiming timed out. Reverting to SEARCHING.")
                        self.set_state(STATE_SEARCHING)
                        continue

                    if det:
                        is_down = self.is_camera_looking_down()
                        vel_right, vel_vertical = self.servo.compute_velocity(cx, cy)

                        # We don't advance closer during AIMING, just centre it
                        if not self.sim:
                            if is_down:
                                self.servo.send_velocity_body(-vel_vertical, vel_right, 0.0)
                            else:
                                self.servo.send_velocity_body(0.0, vel_right, vel_vertical)

                        # Check if target is perfectly centered
                        err_x_abs = abs(cx - FRAME_W // 2)
                        err_y_abs = abs(cy - FRAME_H // 2)
                        
                        if err_x_abs < DEADBAND_PX and err_y_abs < DEADBAND_PX:
                            if self.lock_start_time is None:
                                self.lock_start_time = time.time()
                            elif time.time() - self.lock_start_time >= LOCK_DURATION_S:
                                print("[AIMING] Lock maintained! Firing.")
                                if not self.sim:
                                    self.servo.send_velocity_body(0.0, 0.0, 0.0)
                                self.set_state(STATE_FIRING)
                        else:
                            self.lock_start_time = None

                elif self.state == STATE_FIRING:
                    print(f"Firing water for {SHOOT_DURATION_S}s!")
                    self.trigger.fire(SHOOT_DURATION_S)
                    
                    self.last_shot_frame = frame
                    self.set_state(STATE_CAPTURING)

                elif self.state == STATE_CAPTURING:
                    print("Saving confirmation photo (from GCS capture)...")
                    if self.last_shot_frame is not None:
                        os.makedirs(PHOTO_SAVE_DIR, exist_ok=True)
                        self.target_counter += 1
                        photo_name = f"Task_2_{TEAM_NAME}_target_{self.target_counter}.jpg"
                        photo_path = os.path.join(PHOTO_SAVE_DIR, photo_name)
                        cv2.imwrite(photo_path, self.last_shot_frame)
                        print(f"Saved: {photo_path}")
                        self.upload_file_path = photo_path
                        self.set_state(STATE_UPLOADING)
                    else:
                        print("ERROR: No frame to save!")
                        self.set_state(STATE_SEARCHING)

                elif self.state == STATE_UPLOADING:
                    print("Uploading to Drive...")
                    if hasattr(self, 'upload_file_path'):
                        self.uploader.upload_task2_photo(self.upload_file_path, self.target_counter)
                    
                    # Reset target tracking state and search for next target
                    self.lock_start_time = None
                    self.last_seen_time = 0
                    self.frames_without_target = 0
                    self.last_shot_frame = None
                    self.set_state(STATE_SEARCHING)

        except KeyboardInterrupt:
            print("\nAborted by user.")
        finally:
            if not self.sim:
                self.servo.send_velocity_body(0.0, 0.0, 0.0)
            self.camera.cleanup()
            cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--connect', default='udpin:127.0.0.1:14550', help='MAVLink standard sitl connection')
    parser.add_argument('--baud', type=int, default=57600, help='Baudrate')
    parser.add_argument('--sim', action='store_true', help='Simulation mode (no commands sent)')
    parser.add_argument('--headless', action='store_true', help='Disable OpenCV viewing windows')
    parser.add_argument('--scrcpy-ip', type=str, default=None, help='IP Address of phone for scrcpy tcpip connection')
    args = parser.parse_args()

    extinguisher = GCSAutoExtinguisher(args.connect, args.baud, args.sim, args.headless, args.scrcpy_ip)
    extinguisher.loop()
