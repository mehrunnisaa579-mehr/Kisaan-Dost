"""
FarmAI — IoT Sensor Service
Stores and provides latest field telemetry (soil moisture, temperature, humidity)
received from ESP32 sensors.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Module-level dictionary storing latest telemetry by device_id
_LATEST_READINGS: dict = {}


def store_reading(device_id: str, soil_moisture: float, temperature: float, humidity: float) -> dict:
    """
    Validate, normalize, and store sensor reading with server timestamp.

    Parameters
    ----------
    device_id : str
        Device identifier (e.g. 'field_1').
    soil_moisture : float
        Soil moisture percentage (0 - 100%).
    temperature : float
        Ambient temperature in Celsius (-10 to 60°C).
    humidity : float
        Relative humidity percentage (0 - 100%).

    Returns
    -------
    dict
        Stored reading data structure.
    """
    # ── Input Validation & Safe Clamping (Never Raises) ──────────────────────
    valid_sm = soil_moisture
    valid_temp = temperature
    valid_hum = humidity

    if soil_moisture < 0 or soil_moisture > 100:
        logger.warning(
            "[IoT Service] Out-of-range soil_moisture (%.1f%%) from %s — clamping to 0-100",
            soil_moisture, device_id
        )
        valid_sm = max(0.0, min(100.0, float(soil_moisture)))

    if humidity < 0 or humidity > 100:
        logger.warning(
            "[IoT Service] Out-of-range humidity (%.1f%%) from %s — clamping to 0-100",
            humidity, device_id
        )
        valid_hum = max(0.0, min(100.0, float(humidity)))

    if temperature < -10 or temperature > 60:
        logger.warning(
            "[IoT Service] Out-of-range temperature (%.1f°C) from %s — clamping to -10 to 60°C",
            temperature, device_id
        )
        valid_temp = max(-10.0, min(60.0, float(temperature)))

    reading_data = {
        "device_id": str(device_id or "field_1"),
        "soil_moisture": round(float(valid_sm), 1),
        "temperature": round(float(valid_temp), 1),
        "humidity": round(float(valid_hum), 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    _LATEST_READINGS[reading_data["device_id"]] = reading_data
    logger.info("[IoT Service] Stored telemetry for %s: %s", reading_data["device_id"], reading_data)
    return reading_data


def get_latest_reading(device_id: str = "field_1") -> dict | None:
    """
    Retrieve the latest sensor reading stored for the specified device_id.

    Parameters
    ----------
    device_id : str
        Target device identifier (default 'field_1').

    Returns
    -------
    dict | None
        Latest reading dict or None if no data has been received yet.
    """
    return _LATEST_READINGS.get(device_id)
