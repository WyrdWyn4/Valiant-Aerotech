from pymavlink import mavutil

master = mavutil.mavlink_connection('udpin:127.0.0.1:14550')

print("Waiting for heartbeat...")
master.wait_heartbeat()
print("Connected")

while True:
    msg = master.recv_match(type='STATUSTEXT', blocking=True)
    if msg is None:
        continue
    
    print(msg)