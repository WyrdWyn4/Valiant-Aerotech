import cv2

cap = cv2.VideoCapture(0) #0 is the default camera

if not cap.isOpened():
    print("Could not open Camera.")

while True:
    #capture frame by frame
    ret, frame = cap.read()

    if not ret:
        print("Cant receive frame. Exiting...")
        break

    cv2.imshow('Live Webcam Feed', frame)

    #break the loop when the 'ESC' key is pressed
    if cv2.waitKey(1)==27:
        break

cap.release()
cv2.destroyAllWindows()
