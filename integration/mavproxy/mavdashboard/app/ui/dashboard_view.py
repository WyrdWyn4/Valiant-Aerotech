import time

import pandas as pd
import streamlit as st


def render_dashboard(snapshot: dict) -> None:
    st.title("MAVLink Real-Time Dashboard")

    with st.sidebar:
        st.subheader("Connection")
        st.write(f"Connected: {'Yes' if snapshot['connected'] else 'No'}")
        st.write(f"System ID: {snapshot['system_id'] if snapshot['system_id'] is not None else '-'}")
        st.write(f"Component ID: {snapshot['component_id'] if snapshot['component_id'] is not None else '-'}")
        st.write(f"Mode: {snapshot['flight_mode'] if snapshot['flight_mode'] else '-'}")
        st.write(f"Armed: {snapshot['armed'] if snapshot['armed'] is not None else '-'}")

        if snapshot["last_message_time"] is not None:
            age = time.time() - snapshot["last_message_time"]
            st.write(f"Last packet age: {age:.1f} s")
        else:
            st.write("Last packet age: -")

        if snapshot["last_error"]:
            st.error(snapshot["last_error"])

    row1 = st.columns(4)
    row1[0].metric("Latitude", "-" if snapshot["lat"] is None else f"{snapshot['lat']:.6f}")
    row1[1].metric("Longitude", "-" if snapshot["lon"] is None else f"{snapshot['lon']:.6f}")
    row1[2].metric("Altitude (m)", "-" if snapshot["alt_m"] is None else f"{snapshot['alt_m']:.2f}")
    row1[3].metric(
        "Ground Speed (m/s)",
        "-" if snapshot["groundspeed_mps"] is None else f"{snapshot['groundspeed_mps']:.2f}",
    )

    row2 = st.columns(4)
    row2[0].metric("Roll (deg)", "-" if snapshot["roll_deg"] is None else f"{snapshot['roll_deg']:.1f}")
    row2[1].metric("Pitch (deg)", "-" if snapshot["pitch_deg"] is None else f"{snapshot['pitch_deg']:.1f}")
    row2[2].metric("Yaw (deg)", "-" if snapshot["yaw_deg"] is None else f"{snapshot['yaw_deg']:.1f}")
    row2[3].metric(
        "Battery (%)",
        "-" if snapshot["battery_remaining"] is None else f"{snapshot['battery_remaining']}",
    )

    row3 = st.columns(2)
    row3[0].metric(
        "GPS Fix Type",
        "-" if snapshot["gps_fix_type"] is None else f"{snapshot['gps_fix_type']}",
    )
    row3[1].metric(
        "Satellites Visible",
        "-" if snapshot["satellites_visible"] is None else f"{snapshot['satellites_visible']}",
    )

    left, right = st.columns(2)

    with left:
        st.subheader("Altitude History")
        if snapshot["altitude_history"]:
            df_alt = pd.DataFrame(snapshot["altitude_history"]).set_index("time")
            st.line_chart(df_alt[["alt_m"]])
        else:
            st.info("No altitude data yet.")

    with right:
        st.subheader("Ground Speed History")
        if snapshot["speed_history"]:
            df_speed = pd.DataFrame(snapshot["speed_history"]).set_index("time")
            st.line_chart(df_speed[["groundspeed_mps"]])
        else:
            st.info("No speed data yet.")

    st.subheader("Top Message Types")
    if snapshot["message_counts"]:
        counts_df = (
            pd.DataFrame(
                [{"message_type": k, "count": v} for k, v in snapshot["message_counts"].items()]
            )
            .sort_values("count", ascending=False)
            .reset_index(drop=True)
        )
        st.dataframe(counts_df, width="stretch", hide_index=True)
    else:
        st.info("No messages received yet.")

    st.subheader("Latest Raw Messages")
    if snapshot["latest_messages"]:
        rows = [
            {"message_type": msg_type, "payload": str(payload)}
            for msg_type, payload in snapshot["latest_messages"].items()
        ]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.info("No raw messages yet.")