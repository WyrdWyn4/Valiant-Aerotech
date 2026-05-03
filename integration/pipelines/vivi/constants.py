"""Shared constants for the Vivi Task One localization package."""

# Task One target colours. detect() should only return one of these values.
ALLOWED_COLOURS = {"black", "white", "red", "yellow", "blue", "green"}

# Small tolerance used for safe geometry divisions and near-parallel checks.
EPS = 1e-9
