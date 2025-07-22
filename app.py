from flask import Flask, request, jsonify
from supabase import create_client, Client
import random
import string
import requests
import re
# Initialize Flask App
app = Flask(__name__)

# === Supabase Configuration ===
SUPABASE_URL = "https://elsrdfggcsfotcntlawf.supabase.co".strip()
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVsc3JkZmdnY3Nmb3RjbnRsYXdmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTIxNTM0MzgsImV4cCI6MjA2NzcyOTQzOH0.OzahTapdw7oxj2nJAp3MDmcT97hcdibDvsfKIqZMmYM".strip()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# === ESP32 IP Address ===
ESP32_IP = "http://192.168.0.111"  # Must match actual ESP32 IP

# === Helper: Generate Booking ID ===
def generate_booking_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

# === Helper: Check Available Slot from ESP32 ===
def get_available_slot():
    try:
        response = requests.get(f"{ESP32_IP}/slots", timeout=5)
        if response.status_code == 200:
            data = response.json()
            slots = data.get("slots", [])
            for slot in slots:
                if slot["status"] == "Available":
                    return slot["slot_id"]
    except Exception as e:
        print("❌ ESP32 Error:", str(e))
    return None

# === ROUTE: Book Slot (Frontend) ===
@app.route("/api/book_slot", methods=["POST"])
def book_slot():
    try:
        data = request.get_json()
        print("📥 Received booking data:", data)

        required = ["full_name", "vehicle_number", "in_time", "out_time", "booking_date"]
        missing = [field for field in required if not data.get(field)]
        if missing:
            return jsonify({"success": False, "message": f"Missing fields: {missing}"}), 400

        slot_id = get_available_slot()
        if not slot_id:
            return jsonify({"success": False, "message": "No slots available"}), 400

        booking_id = generate_booking_id()

        # Insert into Supabase
        result = supabase.table("bookings").insert({
            "booking_id": booking_id,
            "slot_id": slot_id,
            "name": data["full_name"],
            "vehicle_number": data["vehicle_number"],
            "in_time": data["in_time"],
            "out_time": data["out_time"],
            "booking_date": data["booking_date"],
            "status": "Confirmed"
        }).execute()

        print("✅ Booking created:", result)

        return jsonify({
            "success": True,
            "slot": slot_id,
            "booking_id": booking_id,
            "message": "Slot booked successfully"
        })

    except Exception as e:
        print("🔥 Error in /api/book_slot:", str(e))
        return jsonify({"success": False, "message": "Server error"}), 500

# === ROUTE: AI Plate Verification (/entry) ===
@app.route("/entry", methods=["POST"])
def verify_plate():
    data = request.get_json()
    raw_plate = data.get("vehicle_number")

    if not raw_plate:
        return jsonify({"success": False, "message": "Vehicle number missing"}), 400

    # Clean the plate
    def clean_plate(txt):
        txt = txt.upper()
        txt = txt.replace('O', '0').replace('I', '1').replace('S', '5').replace('Z', '2')
        return re.sub(r'[^A-Z0-9]', '', txt)

    cleaned_plate = clean_plate(raw_plate)
    print(f"🔧 Plate received: '{raw_plate}' → cleaned: '{cleaned_plate}'")

    try:
        # Try exact match first
        response = supabase.table("bookings").select("*").eq("vehicle_number", cleaned_plate).limit(1).execute()

        # Optional: Also try with original if cleaned fails
        if len(response.data) == 0:
            response = supabase.table("bookings").select("*").ilike("vehicle_number", f"%{cleaned_plate}%").limit(1).execute()

        if len(response.data) > 0:
            booking = response.data[0]
            slot_id = booking.get("slot_id")
            
            # Open gate
            try:
                requests.post(f"{ESP32_IP}/gate", json={"action": "open"}, timeout=3)
                print(f"✅ Verified: {cleaned_plate} - Opening gate for Slot {slot_id}")
            except Exception as e:
                print("⚠️ Gate open failed:", str(e))

            return jsonify({"success": True, "message": "Access granted", "slot": slot_id})

        else:
            print(f"❌ No booking found for plate: {cleaned_plate}")
            return jsonify({"success": False, "message": "Vehicle not found"}), 404

    except Exception as e:
        print("Error:", str(e))
        return jsonify({"success": False, "message": "Verification failed"}), 500

    except Exception as e:
        print("Error in /entry:", str(e))
        return jsonify({"success": False, "message": "Verification failed"}), 500

# ✅ === CRITICAL: /update_slot Route === ✅
@app.route("/update_slot", methods=["POST"])
def update_slot_status():
    try:
        data = request.get_json()
        print("🔄 Received /update_slot:", data)  # Log incoming data

        slot_id = data.get("slot_id")
        status = data.get("status")

        if not slot_id or not status:
            return jsonify({"success": False, "message": "Missing slot_id or status"}), 400

        # Update Supabase
        supabase.table("bookings").update({"status": status}).eq("slot_id", slot_id).execute()
        print(f"✅ Updated {slot_id} to {status}")
        return jsonify({"success": True, "message": f"{slot_id} set to {status}"})

    except Exception as e:
        print("🔥 Update failed:", str(e))
        return jsonify({"success": False, "message": "Update failed"}), 500

# === ROUTE: Get Booking Status (for frontend) ===
@app.route("/api/booking_status", methods=["GET"])
def get_booking_status():
    try:
        response = supabase.table("bookings").select("*").execute()
        return jsonify({"success": True, "bookings": response.data})
    except Exception as e:
        print("❌ Failed to fetch bookings:", str(e))
        return jsonify({"success": False, "message": "DB error"}), 500

# === LIST ALL ROUTES FOR DEBUGGING ===
@app.route("/routes")
def list_routes():
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append(f"{rule.rule} → {rule.endpoint} [{', '.join(rule.methods)}]")
    return "<pre>" + "\n".join(sorted(routes)) + "</pre>"

# === Add CORS Headers ===
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# === Run Server ===
if __name__ == "__main__":
    print("\n🚀 Flask Server Starting...")
    print("📌 Supabase Connected")
    print("📡 ESP32 IP:", ESP32_IP)
    print("🌐 Visit http://192.168.0.104:5000/routes to see all endpoints\n")
    app.run(host="0.0.0.0", port=5000, debug=True)