import sys
import cv2 
import numpy as np

cap = cv2.VideoCapture(0) #0 is the default camera

if not cap.isOpened():
    print("Could not open Camera.")

while True:
    #capture frame by frame
    ret, frame = cap.read()

    if not ret:
        print("Cant receive frame. Exiting...")
        break

    #break the loop when the 'ESC' key is pressed
    if cv2.waitKey(1)==27:
        break

    #Got it from here https://docs.opencv.org/3.4/d4/d70/tutorial_hough_circle.html
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) #grey the image
    gray = cv2.medianBlur(gray,5) #blur the image to reduce noise

    rows = gray.shape[0]

    circles =  cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, 1, rows / 8,
                               param1=100, param2=30,
                               minRadius=1, maxRadius=30)  #Hough circle transform
    

     
    if circles is not None:
        circles = np.uint16(np.around(circles))
        for i in circles[0, :]:
            center = (i[0], i[1])
            # circle center
            cv2.circle(frame, center, 1, (0, 100, 100), 3)
            # circle outline
            radius = i[2]
            cv2.circle(frame, center, radius, (255, 0, 255), 3)
    
    
    cv2.imshow("detected circles", frame)
    if cv2.waitKey(1) == 27:  # ESC
        break

cap.release()
cv2.destroyAllWindows()
