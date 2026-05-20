"""
config.py — All tunable parameters for the Task 2 auto-extinguish pipeline.

Edit these values based on flight tests. Gains (KP/KD) and HSV ranges are the
most critical to tune before competition.
"""

# ─── MAVLink ──────────────────────────────────────────────────────────────────
MAVLINK_CONNECTION = "/dev/ttyAMA0"
MAVLINK_BAUD = 921600

# ─── Camera ───────────────────────────────────────────────────────────────────
FRAME_W = 1920
FRAME_H = 1080
CAMERA_HFOV_DEG = 66.0   # RPi AI Camera horizontal FOV — verify from datasheet
CAMERA_VFOV_DEG = 41.0   # RPi AI Camera vertical FOV — verify

# ─── Visual Servo PD Gains ────────────────────────────────────────────────────
# Proportional gain: how aggressively to correct pixel error.
# Start low (0.001) and increase until smooth convergence in ~3-5 seconds.
KP_X = 0.002   # lateral (left/right) error
KP_Y = 0.002   # vertical/forward error
KD_X = 0.0     # derivative gain (start at 0, add if oscillating)
KD_Y = 0.0
MAX_VEL = 0.5  # m/s max velocity command (conservative for first tests)
DEADBAND_PX = 40  # pixels — don't move if error within this radius

# ─── Approach Phase ───────────────────────────────────────────────────────────
APPROACH_SPEED = 0.3      # m/s forward velocity during approach
TARGET_LOCK_AREA_PX = 15000  # bounding box area in pixels when "close enough"
                              # Measure: (width_px * height_px) of target at ~1.5m
APPROACH_TIMEOUT_S = 30   # abort if approach takes longer

# ─── Lock / Aim Phase ────────────────────────────────────────────────────────
LOCK_DURATION_S = 1.5     # hold centered for this long before firing
LOCK_TIMEOUT_S = 10       # abort aim phase if can't achieve lock

# ─── Water Trigger ────────────────────────────────────────────────────────────
SHOOT_METHOD = "MAVLINK_SERVO"     # "GPIO" (RPi5 BCM) or "MAVLINK_SERVO" (GCS/MAVLink)
GPIO_SHOOT_PIN = 18       # BCM pin number on RPi5
MAVLINK_SHOOT_CHANNEL = 10  # servo channel if using MAVLink method
SHOOT_DURATION_S = 2.0    # how long to run pump / open valve

# ─── Photo & Upload ──────────────────────────────────────────────────────────
TEAM_NAME = "ValiantAerotech"  # Team name used for file formatting in competition
GDRIVE_CONFIG_PATH = "integration/configs/gdrive_config.json"
PHOTO_SAVE_DIR = "task2_photos"
UPLOAD_TIMEOUT_S = 15     # max wait for upload before continuing

# ─── Safety ───────────────────────────────────────────────────────────────────
MIN_BATTERY_PCT = 20      # abort auto sequence if battery below this
GEOFENCE_ABORT = True     # abort if MAVLink reports geofence breach

# ─── Target Lost Recovery ─────────────────────────────────────────────────────
MAX_FRAMES_WITHOUT_TARGET = 30  # ~1.5 sec at 20 Hz before returning to SEARCHING
