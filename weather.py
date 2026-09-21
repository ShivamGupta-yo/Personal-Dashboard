"""Current weather and today's range from Open-Meteo (free, no API key)."""
import requests

URL = "https://api.open-meteo.com/v1/forecast"

WMO = {
    0: "Clear sky", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Freezing fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Rain showers", 81: "Rain showers", 82: "Heavy showers", 85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with hail",
}


def build(cfg):
    resp = requests.get(
        URL,
        params={
            "latitude": cfg["latitude"],
            "longitude": cfg["longitude"],
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto",
            "forecast_days": 1,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    cur, day = data["current"], data["daily"]
    return {
        "label": cfg.get("label", ""),
        "temp": round(cur["temperature_2m"]),
        "feels": round(cur["apparent_temperature"]),
        "wind": round(cur["wind_speed_10m"]),
        "description": WMO.get(cur["weather_code"], "Unknown"),
        "high": round(day["temperature_2m_max"][0]),
        "low": round(day["temperature_2m_min"][0]),
        "rain_chance": day["precipitation_probability_max"][0],
    }
