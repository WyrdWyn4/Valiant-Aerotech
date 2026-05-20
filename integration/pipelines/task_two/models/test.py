#!/usr/bin/env python3
"""
Live sliding-window inference script for Windows using a trained YOLO model (ONNX).
This replaces the Raspberry Pi specific camera implementation.
It captures from your webcam (or screen) and convolutes the model over the full frame.
"""

import cv2
import numpy as np
import signal
import sys
import time
from ultralytics import YOLO

# ----------------------------------------------------------------------
# Constants (based on your camera geometry and training)
# ----------------------------------------------------------------------
HFOV_DEG = 66.26          # Horizontal field of view (degrees)
VFOV_DEG = 52.02          # Vertical field of view (degrees)
# We assume the webcam / target feed is roughly this resolution for calcs:
CAPTURE_WIDTH = 1280      
CAPTURE_HEIGHT = 720      
R_s = 224                 # Model input size (must match training)
DISTANCE_CM = 100.0       # Distance from camera to scene (cm)

# ----------------------------------------------------------------------
# Sliding window parameters
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# Geometry factors (pre-calculated based on Pi camera FOVs)
# ----------------------------------------------------------------------
half_hfov_rad = np.radians(HFOV_DEG) / 2
half_vfov_rad = np.radians(VFOV_DEG) / 2
real_width_at_distance = 2 * DISTANCE_CM * np.tan(half_hfov_rad)
real_height_at_distance = 2 * DISTANCE_CM * np.tan(half_vfov_rad)

CONF_THRESH = 0.35   # Minimum confidence to accept a detection
NMS_THRESH = 0.40    # Intersection-over-Union threshold for NMS

running = True
def signal_handler(sig, frame):
    global running
    print("\nStopping...")
    running = False

signal.signal(signal.SIGINT, signal_handler)

# ----------------------------------------------------------------------
# Sliding Window Inference Function
# ----------------------------------------------------------------------
def sliding_window_inference(model, frame, window_size, step_size):
    """
    Slides a window over the frame, resizes each window to R_x*R_s,
    runs YOLO inference, and aggregates bounding boxes with NMS.
    """
    fh, fw = frame.shape[:2]
    win_w, win_h = window_size
    step_x, step_y = step_size
    
    boxes_data = []      # [x, y, w, h] format for cv2.dnn.NMSBoxes
    confidences = []
    class_ids = []
    
    # 1. Slide window across the frame
    for y in range(0, max(1, fh - win_h + step_y), step_y):
        for x in range(0, max(1, fw - win_w + step_x), step_x):
            # Clamp boundaries so we don't go out of frame
            y_start = min(y, fh - win_h) if fh > win_h else 0
            x_start = min(x, fw - win_w) if fw > win_w else 0
            y_end = min(y_start + win_h, fh)
            x_end = min(x_start + win_w, fw)
            
            if (x_end - x_start) <= 0 or (y_end - y_start) <= 0:
                continue

            # Extract window and optionally resize back to R_s x R_s
            window = frame[y_start:y_end, x_start:x_end]
            resized = cv2.resize(window, (R_s, R_s), interpolation=cv2.INTER_AREA)
            
            # Predict
            results = model(resized, verbose=False)
            
            # 2. Map bounding boxes back to the full frame
            for result in results:
                for box in result.boxes:
                    conf = float(box.conf[0].cpu().numpy())
                    if conf < CONF_THRESH:
                        continue
                        
                    cls = int(box.cls[0].cpu().numpy())
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    
                    # Scale coordinates from 224x224 back to the cropped window size
                    scale_x = (x_end - x_start) / R_s
                    scale_y = (y_end - y_start) / R_s
                    
                    full_x1 = x_start + (x1 * scale_x)
                    full_y1 = y_start + (y1 * scale_y)
                    full_w = (x2 - x1) * scale_x
                    full_h = (y2 - y1) * scale_y
                    
                    boxes_data.append([int(full_x1), int(full_y1), int(full_w), int(full_h)])
                    confidences.append(conf)
                    class_ids.append(cls)
                    
    # 3. Non-Maximum Suppression to remove duplicates along window seams
    final_boxes = []
    if len(boxes_data) > 0:
        indices = cv2.dnn.NMSBoxes(boxes_data, confidences, score_threshold=CONF_THRESH, nms_threshold=NMS_THRESH)
        if len(indices) > 0:
            for i in indices.flatten():
                bx, by, bw, bh = boxes_data[i]
                final_boxes.append({
                    "bbox": [bx, by, bx + bw, by + bh],
                    "conf": confidences[i],
                    "cls": class_ids[i]
                })
                
    return final_boxes

def get_resolution_from_gui():
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("Camera Setup")
    root.geometry("320x150")

    ttk.Label(root, text="Select Processing Resolution:\n(Frames will be resized to this)").pack(pady=10)

    res_var = tk.StringVar(value="1280x720 (Default)")
    combo = ttk.Combobox(root, textvariable=res_var, values=[
        "1920x1080",
        "1280x720 (Default)",
        "800x800",
        "800x600",
        "640x480",
        "No Downscale (Native)"
    ], state="readonly", width=25)
    combo.pack()

    def on_ok():
        root.quit()

    ttk.Button(root, text="Start Camera", command=on_ok).pack(pady=15)
    root.mainloop()

    selection = res_var.get()
    root.destroy()
    return selection


def main():
    selection = get_resolution_from_gui()
    print(f"User selected: {selection}")

    if selection == "No Downscale (Native)":
        target_w, target_h = None, None
    else:
        target_w, target_h = map(int, selection.split()[0].split('x'))

    print("Loading model...")
    model = YOLO("best.onnx", task="detect")   # force detection task

    # For Windows testing, use the webcam
    print("Opening webcam...")
    cap = cv2.VideoCapture(0)
    
    # Suggest resolution to backend, but usually it gives a native one anyway
    if target_w and target_h:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)

    if not cap.isOpened():
        print("Error: Could not open webcam.")
        sys.exit(1)

    # Read first frame to compute accurate sliding window numbers
    ret, frame = cap.read()
    if not ret:
        print("Error: Could not read frame from webcam.")
        sys.exit(1)

    if target_w and target_h:
        frame = cv2.resize(frame, (target_w, target_h))

    actual_h, actual_w = frame.shape[:2]
    print(f"Model loaded. Processing resolution: {actual_w}x{actual_h}")
    print("Camera started. Press 'q' to stop.")

    try:
        while running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1)
                continue

            # Force resize frame to the requested processing resolution
            if target_w and target_h:
                frame = cv2.resize(frame, (target_w, target_h))

            h, w = frame.shape[:2]
            
            # Crop the strict central 224x224 area
            crop_w, crop_h = R_s, R_s
            start_x = (w - crop_w) // 2
            start_y = (h - crop_h) // 2
            
            # Safety bounds just in case the resolution requested is ridiculously small
            start_x = max(0, start_x)
            start_y = max(0, start_y)
            
            cropped = frame[start_y:max(0, start_y+crop_h), start_x:max(0, start_x+crop_w)]
            
            # Run inference purely on the central 224x224 patch
            results = model(cropped, verbose=False)
            
            # Draw a visual box indicating what the AI is "looking" at (The 224x224 boundary)
            cv2.rectangle(frame, (start_x, start_y), (start_x + crop_w, start_y + crop_h), (255, 0, 0), 2)
            cv2.putText(frame, "AI View Area (224x224)", (start_x, max(start_y - 10, 10)), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)

            # Draw results on the frame
            for result in results:
                for box in result.boxes:
                    conf = float(box.conf[0].cpu().numpy())
                    if conf < CONF_THRESH:
                        continue
                        
                    cls = int(box.cls[0].cpu().numpy())
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    
                    # Offset the bounding box coordinates back to the full frame position
                    full_x1 = int(x1 + start_x)
                    full_y1 = int(y1 + start_y)
                    full_x2 = int(x2 + start_x)
                    full_y2 = int(y2 + start_y)
                    
                    # Draw bounding box
                    cv2.rectangle(frame, (full_x1, full_y1), (full_x2, full_y2), (0, 255, 0), 2)
                    
                    # Draw label
                    label = f"Class {cls} ({conf:.2f})"
                    cv2.putText(frame, label, (full_x1, max(full_y1 - 10, 0)), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # Show the annotated image
            cv2.imshow("Central Region YOLO", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("Camera stopped and window closed.")

if __name__ == "__main__":
    main()