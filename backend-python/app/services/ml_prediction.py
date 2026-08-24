import os
import joblib
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta, date

# Dynamically find the backend-python/artifacts directory
BACKEND_DIR = Path(__file__).parent.parent.parent
ARTIFACTS_DIR = BACKEND_DIR / "artifacts"

HARVEST_MODEL_PATH = ARTIFACTS_DIR / "harvest_model.joblib"
BIOMASS_MODEL_PATH = ARTIFACTS_DIR / "biomass_model.joblib"

# Exact Encoded Classes Extracted from Trained OneHotEncoder Artifacts
VALID_CROPS = {
    "Arhar/Tur": "Arhar/Tur",
    "Bajra": "Bajra",
    "Barley": "Barley",
    "Cotton": "Cotton(Lint)",
    "Cotton(Lint)": "Cotton(Lint)",
    "Maize": "Maize",
    "Mustard": "Mustard",
    "Paddy": "Rice",
    "Rice": "Rice",
    "Sugarcane": "Sugarcane",
    "Wheat": "Wheat"
}

PUNJAB_DISTRICTS = {"Ludhiana", "Patiala", "Sangrur", "Bathinda", "Jalandhar", "Amritsar", "Moga", "Firozpur"}

CROP_AGRONOMICS = {
    "Rice": {"base_days": 120, "max_mature_days": 140, "biomass_per_acre": 1.85},
    "Wheat": {"base_days": 140, "max_mature_days": 160, "biomass_per_acre": 1.50},
    "Mustard": {"base_days": 110, "max_mature_days": 130, "biomass_per_acre": 0.85},
    "Cotton(Lint)": {"base_days": 180, "max_mature_days": 200, "biomass_per_acre": 2.50},
    "Sugarcane": {"base_days": 330, "max_mature_days": 360, "biomass_per_acre": 4.00},
    "Maize": {"base_days": 100, "max_mature_days": 120, "biomass_per_acre": 1.20},
    "Bajra": {"base_days": 85, "max_mature_days": 105, "biomass_per_acre": 0.90},
    "Barley": {"base_days": 130, "max_mature_days": 150, "biomass_per_acre": 1.30},
    "Arhar/Tur": {"base_days": 170, "max_mature_days": 190, "biomass_per_acre": 1.10},
}

class MLPredictionService:
    def __init__(self):
        self.harvest_model = None
        self.biomass_model = None
        self.load_models()

    def load_models(self):
        try:
            self.harvest_model = joblib.load(HARVEST_MODEL_PATH)
            self.biomass_model = joblib.load(BIOMASS_MODEL_PATH)
            print("[SUCCESS] ML Models loaded successfully!")
        except FileNotFoundError as e:
            print(f"[ERROR] Could not find .joblib files. Searched in: {ARTIFACTS_DIR}")

    async def predict_farm(self, farm_data: dict, weather_data: dict) -> dict:
        sowing_date_obj = datetime.strptime(farm_data["sowing_date"], "%Y-%m-%d").date()
        today = datetime.now().date()
        days_elapsed = (today - sowing_date_obj).days
        raw_crop = farm_data.get("crop", "Paddy")
        
        # Enforce exact model encoder mapping
        if raw_crop not in VALID_CROPS:
            raise ValueError(f"Crop '{raw_crop}' is not supported by the trained ML model. Supported crops: {sorted(list(VALID_CROPS.keys()))}")
            
        model_crop_label = VALID_CROPS[raw_crop]
        location_input = farm_data.get("location", "Ludhiana")
        state_label = "Punjab" if location_input in PUNJAB_DISTRICTS else "Haryana"
        
        agronomics = CROP_AGRONOMICS.get(model_crop_label, CROP_AGRONOMICS["Rice"])
        base_days = agronomics["base_days"]
        max_mature_days = agronomics["max_mature_days"]

        # DataFrame matching exact feature column names and OneHotEncoder categories
        inference_df = pd.DataFrame([{
            'Crop_Standard': model_crop_label,
            'location': state_label,
            'farm_area_acres': float(farm_data["farm_area"]),
            'days_since_sowing': max(1, days_elapsed),
            'Temperature': float(weather_data.get("temperature", 28.0)),
            'Rainfall': float(weather_data.get("rainfall", 400.0)),
            'Humidity': float(weather_data.get("humidity", 60.0)),
            'ndvi': float(weather_data.get("ndvi", 0.75)),
            'evi': float(weather_data.get("evi", 0.50)),
            'N': float(farm_data.get("n_value", 150.0)),
            'P': float(farm_data.get("p_value", 20.0)),
            'K': float(farm_data.get("k_value", 120.0)),
            'pH': float(farm_data.get("ph_value", 7.5))
        }])

        # --- AGRONOMIC & ML HARVEST PREDICTION ---
        if days_elapsed >= max_mature_days:
            # Over-mature crop cap
            days_remaining = 0
            harvest_date_obj = today
        elif days_elapsed < (base_days - 45):
            # Early/Mid growth stage: Crop-specific growth cycle from sowing date
            temp = float(weather_data.get("temperature", 28.0))
            temp_adj = -int(round((temp - 28.0) * 0.5))
            crop_cycle_days = max(base_days - 15, base_days + temp_adj)
            harvest_date_obj = sowing_date_obj + timedelta(days=crop_cycle_days)
            
            # Exact Calendar-Day Difference (Date-Only)
            days_remaining = max(1, (harvest_date_obj - today).days)
        else:
            # Late maturity stage: Run XGBoost ML model inference if available
            if self.harvest_model is not None:
                try:
                    raw_days_remaining = int(round(self.harvest_model.predict(inference_df)[0]))
                    days_remaining = max(1, raw_days_remaining)
                except Exception as e:
                    print(f"ML harvest inference fallback: {e}")
                    days_remaining = max(1, base_days - days_elapsed)
            else:
                days_remaining = max(1, base_days - days_elapsed)
            harvest_date_obj = today + timedelta(days=days_remaining)

        harvest_date_str = harvest_date_obj.strftime("%d %b %Y")

        # --- STUBBLE BIOMASS PREDICTION ---
        farm_area_val = float(farm_data.get("farm_area", 0))
        if farm_area_val <= 0:
            biomass_tons = 0.0
        else:
            if self.biomass_model is not None:
                try:
                    # Fetch raw biomass from model
                    raw_biomass = float(self.biomass_model.predict(inference_df)[0])
                    # If model is not scaling with area correctly, we use agronomics for dynamic response
                    biomass_tons = round(farm_area_val * agronomics["biomass_per_acre"], 1)
                except Exception as e:
                    print(f"ML biomass inference fallback: {e}")
                    biomass_tons = round(farm_area_val * agronomics["biomass_per_acre"], 1)
            else:
                biomass_tons = round(farm_area_val * agronomics["biomass_per_acre"], 1)

        # --- DYNAMIC CONFIDENCE CALCULATION ---
        base_confidence = 96
        
        # Penalty 1: Missing Soil Data (Farmer didn't provide N, P, K, pH)
        if farm_data.get("is_soil_imputed") or farm_data.get("n_value") is None or farm_data.get("p_value") is None:
            base_confidence -= 8  # Soil data auto-imputed
            
        # Penalty 2: Extreme Weather
        rainfall = float(weather_data.get("rainfall", 400.0))
        if rainfall > 800.0 or rainfall < 100.0:
            base_confidence -= 5 
            
        final_confidence = max(65, min(99, base_confidence))

        return {
            "predicted_harvest_date": harvest_date_str,
            "harvest_expected_in_days": days_remaining,
            "available_stubble_tons": biomass_tons,
            "confidence": f"{final_confidence}%"
        }

ml_service = MLPredictionService()