# MAVLink Real-Time Dashboard

A modular Python dashboard for receiving, parsing, logging, and visualizing MAVLink telemetry in real time.

This project is designed to work with **Mission Planner MAVLink forwarding**. It listens to a forwarded MAVLink UDP stream, processes selected telemetry messages, stores live state, optionally logs raw messages to CSV, and displays a real-time dashboard using Streamlit.

---

## Features

- Real-time MAVLink telemetry receiver using `pymavlink`
- Modular backend structure
- Live dashboard with Streamlit
- Message parsing for common telemetry fields
- Optional CSV logging of raw MAVLink packets
- Auto-refreshing web UI
- Separation of:
  - transport
  - parsing
  - state management
  - storage
  - presentation

---

## Current Telemetry Displayed

The dashboard currently parses and displays selected fields from messages such as:

- `HEARTBEAT`
- `GLOBAL_POSITION_INT`
- `ATTITUDE`
- `SYS_STATUS`
- `GPS_RAW_INT`
- `VFR_HUD`

Displayed values include:

- Latitude / Longitude
- Altitude
- Ground speed
- Roll / Pitch / Yaw
- Battery remaining
- Flight mode
- Armed state
- GPS fix type
- Satellites visible
- Message counts
- Latest raw messages
- Altitude history
- Speed history

---

## Important Altitude Note

MAVLink provides more than one altitude reference.

For `GLOBAL_POSITION_INT`:

- `alt` = altitude above mean sea level (MSL), in mm
- `relative_alt` = altitude relative to home/origin, in mm

Mission Planner often shows **relative altitude** in its flight display.  
If the dashboard uses `alt`, it may not match the altitude shown in Mission Planner.

To match Mission Planner more closely, use:

- `relative_alt / 1000.0` for relative altitude in meters

A good long-term approach is to display both:

- **Altitude (Rel/Home)**
- **Altitude (MSL)**

---

## Project Structure

```text
project/
├── dashboard.py
├── requirements.txt
└── app/
    ├── __init__.py
    ├── core/
    │   ├── __init__.py
    │   ├── config.py
    │   └── telemetry_state.py
    ├── mavlink/
    │   ├── __init__.py
    │   ├── client.py
    │   └── processor.py
    ├── services/
    │   ├── __init__.py
    │   └── telemetry_service.py
    ├── storage/
    │   ├── __init__.py
    │   └── csv_logger.py
    └── ui/
        ├── __init__.py
        └── dashboard_view.py