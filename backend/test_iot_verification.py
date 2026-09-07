"""
Verification Script for KisaanDost IoT Sensor Pipeline
"""

import sys
from fastapi.testclient import TestClient
from main import app
from services.iot_service import _LATEST_READINGS

client = TestClient(app)

def test_iot_pipeline():
    print("==================================================")
    print("RUNNING KISAANDOST IOT PIPELINE VERIFICATION TESTS")
    print("==================================================")

    # 1. Reset state: Ensure no sensor data initially
    _LATEST_READINGS.clear()

    # 2. Test GET /iot/latest when empty
    resp_empty = client.get("/iot/latest")
    assert resp_empty.status_code == 200
    assert resp_empty.json() == {"has_data": False}
    print("[PASS] GET /iot/latest correctly returns has_data: false when empty")

    # 3. Test /analyze BEFORE any sensor data
    analyze_payload_no_iot = {
        "text": "کپاس کی فصل میں پانی کب دینا چاہیے؟",
        "latitude": 30.1978,
        "longitude": 71.4697
    }
    resp_no_iot = client.post("/analyze", json=analyze_payload_no_iot)
    assert resp_no_iot.status_code == 200
    data_no_iot = resp_no_iot.json()
    assert "farmer_response" in data_no_iot
    assert data_no_iot["farmer_response"] != ""
    print("[PASS] /analyze without sensor data runs cleanly and produces normal farmer_response")

    # 4. Test POST /iot/reading with valid telemetry
    iot_sample = {
        "device_id": "field_1",
        "soil_moisture": 18.5, # Low moisture (dry soil)
        "temperature": 34.2,
        "humidity": 45.0
    }
    resp_iot = client.post("/iot/reading", json=iot_sample)
    assert resp_iot.status_code == 200
    assert resp_iot.json() == {"status": "ok"}
    print("[PASS] POST /iot/reading succeeds with status: ok")

    # 5. Test GET /iot/latest after posting telemetry
    resp_latest = client.get("/iot/latest")
    assert resp_latest.status_code == 200
    latest_data = resp_latest.json()
    assert latest_data.get("has_data") is True
    assert latest_data["reading"]["soil_moisture"] == 18.5
    assert latest_data["reading"]["temperature"] == 34.2
    assert latest_data["reading"]["humidity"] == 45.0
    print("[PASS] GET /iot/latest returns stored telemetry accurately")

    # 6. Test POST /iot/reading with malformed / out of range inputs (must NEVER crash)
    out_of_range_payload = {
        "device_id": "field_1",
        "soil_moisture": 150.0, # out of range, should clamp to 100
        "temperature": 75.0,    # out of range, should clamp to 60
        "humidity": -20.0       # out of range, should clamp to 0
    }
    resp_oor = client.post("/iot/reading", json=out_of_range_payload)
    assert resp_oor.status_code == 200
    assert resp_oor.json() == {"status": "ok"}
    print("[PASS] POST /iot/reading handles out-of-range hardware inputs without crashing")

    # 7. Test /analyze WITH sensor data present (dry soil query)
    # Set dry soil telemetry
    client.post("/iot/reading", json={"device_id": "field_1", "soil_moisture": 12.0, "temperature": 36.0, "humidity": 40.0})
    resp_with_iot = client.post("/analyze", json=analyze_payload_no_iot)
    assert resp_with_iot.status_code == 200
    data_with_iot = resp_with_iot.json()
    assert "farmer_response" in data_with_iot
    print("[PASS] /analyze with dry soil sensor data returned HTTP 200")
    print("\nFarmer Response Output:")
    print("--------------------------------------------------")
    print(data_with_iot["farmer_response"])
    print("--------------------------------------------------")

    print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    test_iot_pipeline()
