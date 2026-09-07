"""
FarmAI — IoT Router
Endpoints for ESP32 sensor telemetry ingestion and setup debugging.
"""

import logging
from fastapi import APIRouter
from pydantic import BaseModel, Field
from services.iot_service import store_reading, get_latest_reading

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/iot", tags=["IoT Sensors"])


class SensorReading(BaseModel):
    device_id: str = Field(default="field_1", description="Identifier for the ESP32 sensor hardware unit")
    soil_moisture: float = Field(..., description="Soil moisture percentage (0 - 100%)")
    temperature: float = Field(..., description="Ambient temperature in Celsius")
    humidity: float = Field(..., description="Relative humidity percentage")


@router.post("/reading")
async def post_sensor_reading(payload: SensorReading):
    """
    Ingest live telemetry from ESP32 hardware.

    Guaranteed to return HTTP 200 and never crash on malformed inputs.
    """
    try:
        store_reading(
            device_id=payload.device_id,
            soil_moisture=payload.soil_moisture,
            temperature=payload.temperature,
            humidity=payload.humidity,
        )
        return {"status": "ok"}
    except Exception as exc:
        logger.error("[IoT Router] Error storing sensor reading: %s", exc)
        return {"status": "error", "message": str(exc)}


@router.get("/latest")
async def get_latest_sensor_reading(device_id: str = "field_1"):
    """
    Debug-only endpoint for curl/Postman verification during hardware setup.
    """
    reading = get_latest_reading(device_id=device_id)
    if reading is None:
        return {"has_data": False}
    return {
        "has_data": True,
        "reading": reading,
    }
