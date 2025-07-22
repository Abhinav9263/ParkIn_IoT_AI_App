import cv2
import easyocr
import requests
import numpy as np

# Configuration
IP_CAMERA_URL = "http://192.168.0.102:8080/video"  # Replace with your IP cam URL
FLASK_SERVER_URL = "http://192.168.0.104:5000/entry"  # Flask server IP
PLATE_REGION_COLOR = (0, 255, 0)  # Green box around plate
TEXT_COLOR = (0, 255, 255)  # Yellow text
MIN_CONFIDENCE = 0.5  # OCR confidence threshold

# Initialize EasyOCR reader
reader = easyocr.Reader(['en'], gpu=False)

def detect_plate(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blur, 50, 200)
    contours, _ = cv2.findContours(edged, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    plate_contours = []

    for cnt in contours:
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.018 * peri, True)
        if len(approx) == 4:
            plate_contours.append(approx)
    return plate_contours

def extract_plate_text(roi):
    results = reader.readtext(roi)
    for (bbox, text, prob) in results:
        if prob > MIN_CONFIDENCE:
            return text.upper().strip()
    return None

def ocr_plate_verification():
    cap = cv2.VideoCapture(IP_CAMERA_URL)

    if not cap.isOpened():
        print("❌ Unable to open IP camera stream")
        return

    print("✅ OCR system running. Press 'q' to quit.")
    last_verified_plate = ""

    while True:
        ret, frame = cap.read()
        if not ret:
            print("⚠️ Failed to grab frame")
            break

        # Resize frame for faster processing
        frame = cv2.resize(frame, None, fx=0.7, fy=0.7)

        # Detect plate-like regions
        plate_contours = detect_plate(frame)

        for contour in plate_contours:
            x, y, w, h = cv2.boundingRect(contour)
            roi = frame[y:y+h, x:x+w]

            # Extract text from plate
            plate_text = extract_plate_text(roi)

            if plate_text:
                # Draw box and text
                cv2.drawContours(frame, [contour], -1, PLATE_REGION_COLOR, 2)
                cv2.putText(frame, plate_text, (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, TEXT_COLOR, 2)

                # Send to Flask server if not already sent
                if plate_text != last_verified_plate:
                    print(f"🔍 Detected Plate: {plate_text}")
                    try:
                        response = requests.post(FLASK_SERVER_URL, json={"vehicle_number": plate_text})
                        if response.status_code == 200:
                            print("✅ Verified: Vehicle exists in database")
                            last_verified_plate = plate_text
                        else:
                            print("❌ Not found in database")
                    except Exception as e:
                        print("🌐 Error sending to server:", e)

        # Display video stream
        cv2.imshow("OCR Plate Verification - ParkIn", frame)

        # Exit on 'q' key
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    ocr_plate_verification()