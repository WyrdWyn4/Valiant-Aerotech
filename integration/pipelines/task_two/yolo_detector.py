import cv2
import numpy as np
import os
import time
from ultralytics import YOLO

# ----------------------------------------------------------------------
# Constants from previous test geometry
# ----------------------------------------------------------------------
HFOV_DEG = 66.26          
VFOV_DEG = 52.02          
CAPTURE_WIDTH = 1280      
CAPTURE_HEIGHT = 720      
R_s = 224                 
DISTANCE_CM = 100.0       

half_hfov_rad = np.radians(HFOV_DEG) / 2
half_vfov_rad = np.radians(VFOV_DEG) / 2
real_width_at_distance = 2 * DISTANCE_CM * np.tan(half_hfov_rad)
real_height_at_distance = 2 * DISTANCE_CM * np.tan(half_vfov_rad)

CROP_W = int(CAPTURE_WIDTH * (30.0 / real_width_at_distance))
CROP_H = int(CAPTURE_HEIGHT * (30.0 / real_height_at_distance))

STEP_X = int(CROP_W * 0.5)
STEP_Y = int(CROP_H * 0.5)

CONF_THRESH = 0.35
NMS_THRESH = 0.40

class YOLODetector:
    def __init__(self, model_path="models/best.onnx"):
        # Resolve absolute path relative to this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        abs_model_path = os.path.join(current_dir, model_path)
        
        print(f"[YOLODetector] Loading ONNX model from: {abs_model_path}")
        self.model = YOLO(abs_model_path, task="detect")
        self.R_s = R_s

    def central_crop_inference(self, frame):
        h, w = frame.shape[:2]
        
        # Calculate dynamic crop size assuming the model was geometrically trained 
        # on a 224x224 center patch of a 1280x720 camera frame.
        scale_x = w / 1280.0
        scale_y = h / 720.0
        
        crop_w = max(1, int(self.R_s * scale_x))
        crop_h = max(1, int(self.R_s * scale_y))
        
        start_x = max(0, (w - crop_w) // 2)
        start_y = max(0, (h - crop_h) // 2)
        
        cropped = frame[start_y:start_y+crop_h, start_x:start_x+crop_w]
        
        # Geometrically resize the dynamic crop patch uniformly down to 224x224 for YOLO tensor ingestion
        if cropped.shape[0] > 0 and cropped.shape[1] > 0:
            resized_crop = cv2.resize(cropped, (self.R_s, self.R_s), interpolation=cv2.INTER_AREA)
        else:
            return []

        results = self.model(resized_crop, verbose=False)
        
        final_boxes = []
        for result in results:
            for box in result.boxes:
                conf = float(box.conf[0].cpu().numpy())
                if conf < CONF_THRESH:
                    continue
                    
                cls = int(box.cls[0].cpu().numpy())
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                
                # Offset bounding box to match the original frame
                # YOLO returns coordinates in the 0-224 coordinate system.
                full_x1 = int((x1 / self.R_s) * crop_w + start_x)
                full_y1 = int((y1 / self.R_s) * crop_h + start_y)
                full_x2 = int((x2 / self.R_s) * crop_w + start_x)
                full_y2 = int((y2 / self.R_s) * crop_h + start_y)
                
                final_boxes.append({
                    "bbox": (full_x1, full_y1, full_x2, full_y2),
                    "conf": conf,
                    "cls": cls
                })
                
        return final_boxes

    def detect_target(self, frame):
        """
        Runs YOLO and returning the highest-confidence target.
        Returns: (cx, cy, area, (x1, y1, x2, y2)) or None
        """
        if frame is None:
            return None

        detections = self.central_crop_inference(frame)
        if not detections:
            return None
            
        # Pick the highest confidence detection
        best_det = max(detections, key=lambda d: d["conf"])
        
        x1, y1, x2, y2 = best_det["bbox"]
        w = x2 - x1
        h = y2 - y1
        cx = int(x1 + w / 2)
        cy = int(y1 + h / 2)
        area = int(w * h)
        
        return (cx, cy, area, (x1, y1, x2, y2))

def draw_detection_overlay(frame, detection_result):
    """
    Draws a green bounding box, crosshair, and the central AI View boundary.
    """
    overlay = frame.copy()
    
    # Draw frame-centre crosshair
    h, w = overlay.shape[:2]
    
    # Draw the dynamically scaled central AI view area boundary
    scale_x = w / 1280.0
    scale_y = h / 720.0
    crop_w = max(1, int(R_s * scale_x))
    crop_h = max(1, int(R_s * scale_y))
    
    start_x = max(0, (w - crop_w) // 2)
    start_y = max(0, (h - crop_h) // 2)
    cv2.rectangle(overlay, (start_x, start_y), (start_x + crop_w, start_y + crop_h), (255, 0, 0), 2)
    cv2.putText(overlay, "AI View Tracking Box", (start_x, max(start_y - 10, 10)), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)

    if detection_result is None:
        return overlay
        
    cx, cy, area, bbox = detection_result
    x1, y1, x2, y2 = bbox
    
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.circle(overlay, (cx, cy), 5, (0, 0, 255), -1)
    cv2.putText(overlay, f"YOLO area={area}", (x1, max(y1 - 10, 20)), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    
    cv2.line(overlay, (cx - 15, cy), (cx + 15, cy), (0, 255, 0), 1)
    cv2.line(overlay, (cx, cy - 15), (cx, cy + 15), (0, 255, 0), 1)
    
    return overlay
