from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import farmer, auth

app = FastAPI(
    title="ResidueLink API",
    description="Backend for the Stubble-to-Biomass Marketplace",
    version="1.0.0"
)

# Enable CORS for cross-origin requests from Vercel/local frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(farmer.router)
app.include_router(auth.router)

@app.get("/")
async def root():
    return {"message": "Welcome to the ResidueLink API. ML Models and Real SMS OTP Gateway are active."}