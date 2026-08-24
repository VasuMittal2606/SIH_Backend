from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, validator
from typing import Optional
import httpx
from app.services.ml_prediction import ml_service, VALID_CROPS

router = APIRouter(prefix="/api/farmer", tags=["Farmer Dashboard"])

class PredictionRequest(BaseModel):
    crop: str
    location: str
    farm_area: float
    sowing_date: str
    n_value: Optional[float] = None
    p_value: Optional[float] = None
    k_value: Optional[float] = None
    ph_value: Optional[float] = None

    @validator("crop")
    def validate_crop_name(cls, v):
        if v not in VALID_CROPS:
            supported_list = sorted(list(set(VALID_CROPS.keys())))
            raise ValueError(f"Crop '{v}' is not supported by the trained ML model. Supported crops: {supported_list}")
        return v

# 1. Complete District Coordinates for Punjab & Haryana Stubble Belt
CITY_COORDS = {
    # Punjab Districts
    "Ludhiana": {"lat": 30.9010, "lon": 75.8573},
    "Patiala": {"lat": 30.3398, "lon": 76.3869},
    "Sangrur": {"lat": 30.2458, "lon": 75.8422},
    "Bathinda": {"lat": 30.2110, "lon": 74.9455},
    "Jalandhar": {"lat": 31.3260, "lon": 75.5762},
    "Amritsar": {"lat": 31.6340, "lon": 74.8723},
    "Moga": {"lat": 30.8280, "lon": 75.1717},
    "Firozpur": {"lat": 30.9237, "lon": 74.6063},
    
    # Haryana Districts
    "Karnal": {"lat": 29.6857, "lon": 76.9905},
    "Ambala": {"lat": 30.3782, "lon": 76.7767},
    "Kurukshetra": {"lat": 29.9695, "lon": 76.8783},
    "Kaithal": {"lat": 29.8015, "lon": 76.3989},
    "Sonipat": {"lat": 28.9931, "lon": 77.0151},
    "Panipat": {"lat": 29.3909, "lon": 76.9635},
    "Hisar": {"lat": 29.1492, "lon": 75.7217},
    "Sirsa": {"lat": 29.5352, "lon": 75.0232}
}

# 2. Regional Soil Profiles (Soil Health Card Auto-fill Data for all 16 districts)
DISTRICT_SOIL_PROFILES = {
    # Punjab Profiles
    "Ludhiana": {"n_value": 150.0, "p_value": 24.0, "k_value": 120.0, "ph_value": 7.6},
    "Patiala": {"n_value": 140.0, "p_value": 21.0, "k_value": 118.0, "ph_value": 7.5},
    "Sangrur": {"n_value": 145.0, "p_value": 23.0, "k_value": 115.0, "ph_value": 7.7},
    "Bathinda": {"n_value": 130.0, "p_value": 19.0, "k_value": 105.0, "ph_value": 7.8},
    "Jalandhar": {"n_value": 147.0, "p_value": 22.0, "k_value": 119.0, "ph_value": 7.4},
    "Amritsar": {"n_value": 142.0, "p_value": 21.5, "k_value": 116.0, "ph_value": 7.3},
    "Moga": {"n_value": 138.0, "p_value": 20.0, "k_value": 111.0, "ph_value": 7.5},
    "Firozpur": {"n_value": 133.0, "p_value": 18.5, "k_value": 108.0, "ph_value": 7.9},
    
    # Haryana Profiles
    "Karnal": {"n_value": 145.0, "p_value": 22.5, "k_value": 115.0, "ph_value": 7.4},
    "Ambala": {"n_value": 135.0, "p_value": 20.0, "k_value": 110.0, "ph_value": 7.2},
    "Kurukshetra": {"n_value": 148.0, "p_value": 23.5, "k_value": 119.0, "ph_value": 7.5},
    "Kaithal": {"n_value": 138.0, "p_value": 20.5, "k_value": 112.0, "ph_value": 7.3},
    "Sonipat": {"n_value": 141.0, "p_value": 21.0, "k_value": 114.0, "ph_value": 7.4},
    "Panipat": {"n_value": 143.0, "p_value": 21.8, "k_value": 116.0, "ph_value": 7.6},
    "Hisar": {"n_value": 128.0, "p_value": 17.5, "k_value": 102.0, "ph_value": 8.0},
    "Sirsa": {"n_value": 125.0, "p_value": 16.5, "k_value": 100.0, "ph_value": 8.1}
}

async def fetch_live_weather(location: str) -> dict:
    """Fetches live weather data from Open-Meteo based on district coordinates."""
    coords = CITY_COORDS.get(location, CITY_COORDS["Karnal"]) # Fallback to Karnal
    url = f"https://api.open-meteo.com/v1/forecast?latitude={coords['lat']}&longitude={coords['lon']}&current=temperature_2m,relative_humidity_2m,precipitation"
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            return {
                "temperature": data["current"]["temperature_2m"],
                "humidity": data["current"]["relative_humidity_2m"],
                "rainfall": data["current"]["precipitation"],
                "ndvi": 0.71,
                "evi": 0.52
            }
    except Exception as e:
        print(f"Weather API failed: {e}. Using fallback defaults.")
        return {"temperature": 29.5, "humidity": 67.0, "rainfall": 5.0, "ndvi": 0.71, "evi": 0.52}

@router.post("/dashboard-prediction")
async def get_dashboard_prediction(request: PredictionRequest):
    try:
        farm_data = request.dict(exclude_none=True)
        location = farm_data.get("location", "Karnal")
        
        # Track whether soil data was imputed
        is_soil_imputed = ("n_value" not in farm_data or "p_value" not in farm_data)
        
        # Auto-fill soil data from regional profile if the user didn't provide it
        default_soil = DISTRICT_SOIL_PROFILES.get(location, DISTRICT_SOIL_PROFILES["Karnal"])
        if "n_value" not in farm_data:
            farm_data["n_value"] = default_soil["n_value"]
        if "p_value" not in farm_data:
            farm_data["p_value"] = default_soil["p_value"]
        if "k_value" not in farm_data:
            farm_data["k_value"] = default_soil["k_value"]
        if "ph_value" not in farm_data:
            farm_data["ph_value"] = default_soil["ph_value"]
            
        farm_data["is_soil_imputed"] = is_soil_imputed

        # Fetch live weather and run prediction
        live_weather_data = await fetch_live_weather(location)
        prediction = await ml_service.predict_farm(farm_data, live_weather_data)
        
        return {
            "status": "success",
            "data": {
                "farm_size": f"{farm_data['farm_area']} Acres",
                "crop": farm_data['crop'],
                "location_used": location,
                "soil_source": "District Regional Profile (Soil Health Card Auto-fill)",
                "live_temperature": f"{live_weather_data['temperature']} °C",
                "predicted_harvest": prediction["predicted_harvest_date"],
                "available_stubble": f"{prediction['available_stubble_tons']} Tons",
                "confidence": prediction["confidence"],
                "harvest_expected_in": f"{prediction['harvest_expected_in_days']} DAYS"
            }
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")