"""
water_trigger.py — Abstraction layer for firing water at the target.

Supports two methods, selected by config.SHOOT_METHOD:
  "GPIO"          – RPi5 BCM pin toggles a relay/MOSFET for a pump/valve.
  "MAVLINK_SERVO" – MAV_CMD_DO_SET_SERVO on a spare channel (PWM open/close).
"""

from __future__ import annotations

import time

from .config import (
    SHOOT_METHOD,
    GPIO_SHOOT_PIN,
    SHOOT_DURATION_S,
    MAVLINK_SHOOT_CHANNEL,
)


class WaterTrigger:
    """Fire water using whichever method is configured."""

    def __init__(self, mav_connection=None):
        self.mav = mav_connection
        self._gpio = None
        self._gpio_setup()

    # ── GPIO init ─────────────────────────────────────────────────────────

    def _gpio_setup(self):
        if SHOOT_METHOD != "GPIO":
            return
        try:
            import RPi.GPIO as GPIO          # type: ignore
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(GPIO_SHOOT_PIN, GPIO.OUT)
            GPIO.output(GPIO_SHOOT_PIN, GPIO.LOW)
            self._gpio = GPIO
            print(f"[WATER] GPIO mode — pin {GPIO_SHOOT_PIN} ready")
        except (ImportError, RuntimeError) as exc:
            print(f"[WATER] WARNING: RPi.GPIO unavailable ({exc}) — GPIO shooting disabled")

    # ── Public API ────────────────────────────────────────────────────────

    def fire(self, duration: float = SHOOT_DURATION_S):
        """Open valve / pump for *duration* seconds, then close."""
        print(f"[WATER] Firing for {duration:.1f}s via {SHOOT_METHOD}")
        if SHOOT_METHOD == "GPIO":
            self._fire_gpio(duration)
        elif SHOOT_METHOD == "MAVLINK_SERVO":
            self._fire_mavlink(duration)
        else:
            print(f"[WATER] Unknown SHOOT_METHOD '{SHOOT_METHOD}' — no action")

    # ── GPIO method ───────────────────────────────────────────────────────

    def _fire_gpio(self, duration: float):
        if self._gpio is None:
            print("[WATER] SIMULATED GPIO FIRE (no hardware)")
            time.sleep(duration)
            return
        self._gpio.output(GPIO_SHOOT_PIN, self._gpio.HIGH)
        time.sleep(duration)
        self._gpio.output(GPIO_SHOOT_PIN, self._gpio.LOW)

    # ── MAVLink servo method ──────────────────────────────────────────────

    def _fire_mavlink(self, duration: float):
        if self.mav is None:
            print("[WATER] SIMULATED MAVLINK FIRE (no connection)")
            time.sleep(duration)
            return
        from pymavlink import mavutil

        # PWM 1900 = open, 1100 = closed
        self.mav.mav.command_long_send(
            self.mav.target_system,
            self.mav.target_component,
            mavutil.mavlink.MAV_CMD_DO_SET_SERVO,
            0,                       # confirmation
            MAVLINK_SHOOT_CHANNEL,   # servo channel
            1900,                    # PWM — open
            0, 0, 0, 0, 0,
        )
        time.sleep(duration)
        self.mav.mav.command_long_send(
            self.mav.target_system,
            self.mav.target_component,
            mavutil.mavlink.MAV_CMD_DO_SET_SERVO,
            0,
            MAVLINK_SHOOT_CHANNEL,
            1100,                    # PWM — closed
            0, 0, 0, 0, 0,
        )

    # ── Cleanup ───────────────────────────────────────────────────────────

    def cleanup(self):
        """Release GPIO resources if applicable."""
        if SHOOT_METHOD == "GPIO" and self._gpio is not None:
            try:
                self._gpio.cleanup()
            except Exception:
                pass
