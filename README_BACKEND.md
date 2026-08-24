# ResidueLink — Backend, Database & Authentication

**Smart Stubble-to-Biomass Matching Marketplace**
Team ResidueLink | Smart India Hackathon (SIH) 2026

## Overview

This document covers the server-side architecture of ResidueLink: the FastAPI backend/API layer, the database schema (with MySQL and Supabase/PostgreSQL as alternative options — final choice pending), and the .NET-based authentication layer. It complements the frontend README, which covers the React.js client.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend / API | Python — FastAPI |
| Authentication | .NET (ASP.NET Core) — separate auth service issuing tokens consumed by FastAPI |
| Database | MySQL **or** Supabase (PostgreSQL) — undecided, both covered below |
| ML / Prediction | Scikit-learn, Pandas, NumPy (regression models for harvest-date prediction) |
| External APIs | Open-Meteo / OpenWeatherMap (agro-climatic weather data), Distance Matrix API (geolocation/routing) |
| Deployment | Docker, Git/GitHub, Render / Vercel |

## High-Level Architecture

```
┌─────────────┐        ┌────────────────────┐        ┌──────────────────────┐
│   React.js   │ ─────▶ │  .NET Auth Service   │ ─────▶ │  Database             │
│   Frontend   │ ◀───── │  (login/signup, JWT) │        │  (MySQL / Supabase)   │
└─────────────┘        └────────────────────┘        └──────────────────────┘
       │                                                        ▲
       │  JWT-authenticated requests                            │
       ▼                                                        │
┌─────────────────────────────────────────────────────────────┴───┐
│                     FastAPI Backend (core API)                    │
│  ─ Farmer / Buyer / CHC dashboard endpoints                       │
│  ─ ML harvest-prediction service                                  │
│  ─ Proximity matching engine (Distance Matrix API)                │
│  ─ Profitability calculators                                      │
│  ─ Weather API integration (Open-Meteo / OpenWeatherMap)          │
└────────────────────────────────────────────────────────────────┘
```

The .NET service owns identity (signup/login/token issuance); FastAPI owns all business logic and validates the JWTs issued by .NET on every request. Both services share the same database (or the .NET service owns only the `users`/auth-related tables while FastAPI owns the rest — see [Authentication Layer](#authentication-layer-net) for details).

## Backend (FastAPI)

### Suggested Project Structure

```
backend/
├── main.py                  # FastAPI app entrypoint
├── core/
│   ├── config.py             # env vars, settings
│   ├── security.py           # JWT validation, dependency injection for auth
│   └── database.py           # DB session/connection setup
├── models/                   # ORM models (SQLAlchemy)
├── schemas/                  # Pydantic request/response schemas
├── routers/
│   ├── farmer.py
│   ├── buyer.py
│   ├── chc_official.py
│   ├── listings.py
│   ├── matching.py
│   ├── negotiations.py
│   └── calculators.py
├── services/
│   ├── ml_prediction.py      # harvest-date regression model
│   ├── weather_service.py    # Open-Meteo / OpenWeatherMap client
│   ├── distance_service.py   # Distance Matrix API client
│   └── matching_engine.py    # proximity-first matching logic
└── tests/
```

### Core API Modules & Endpoints

**Farmer Dashboard**
- `POST /farms` — create farm profile (size, crop, variety, sowing date, location)
- `GET /farms/{farm_id}/predicted-harvest` — trigger/fetch ML-predicted harvest date
- `PATCH /farms/{farm_id}/harvest-date` — manual override of predicted date
- `POST /listings` — create sell request (auto-generated 10 days pre-harvest, or manual/instant)
- `GET /listings/{listing_id}/matches` — buyers matched, ranked by distance
- `GET /balers/availability` — real-time CHC baler availability
- `POST /calculators/farmer-profitability` — compute net earnings per acre/ton

**Biomass Buyer Dashboard**
- `POST /buy-requests` — post tonnage requirement + proposed rate
- `GET /buy-requests/{id}/alerts` — proximity-based new-listing alerts
- `GET /listings/nearby` — farms/listings within procurement radius
- `POST /matches/{id}/counter-offer` — submit counter-offer
- `POST /calculators/buyer-landed-cost` — compute total procurement cost per ton
- `GET /deliveries` — procurement & delivery tracker

**Government / CHC Official Dashboard**
- `PATCH /balers/{baler_id}/status` — update baler operational status
- `GET /analytics/heatmap` — regional supply/demand heatmap data
- `GET /analytics/machinery-allocation` — baler allocation overview
- `GET /analytics/environmental-impact` — aggregated tons diverted / fires prevented

**Shared / Cross-Cutting**
- `GET /weather/{location}` — agro-climatic weather data (cached)
- `POST /matching/run` — proximity-first matching algorithm trigger
- `GET|POST /negotiations/{match_id}/messages` — chat/negotiation thread
- All endpoints expect a valid JWT (issued by the .NET auth service) in the `Authorization: Bearer <token>` header, validated via a FastAPI dependency.

### External Integrations

| Integration | Purpose | Used by |
|---|---|---|
| Open-Meteo / OpenWeatherMap API | Real-time agro-climatic parameters feeding the ML harvest-prediction model | `services/weather_service.py` |
| Distance Matrix API | Computes travel distance for proximity-first matching and logistics tracking | `services/distance_service.py` |
| ML Regression Model (Scikit-learn) | Predicts field maturity/harvest date from tabular crop + weather data | `services/ml_prediction.py` |

## Database Structure

Schema is written generically (works for both MySQL and PostgreSQL/Supabase) — differences are noted at the end of this section.

### Entity Overview

`users` → `farmer_profiles` / `buyer_profiles` / `chc_officials` → `farms` → `harvest_predictions` → `listings` ⇄ `buy_requests` → `matches` → `negotiations` / `transactions`, with `chcs` → `balers` → `baler_bookings` on the machinery side.

### Table: `users`

| Column | Type | Notes |
|---|---|---|
| id | UUID / BIGINT PK | primary key |
| full_name | VARCHAR(150) | |
| phone_number | VARCHAR(15) | unique, primary login identifier (OTP-friendly) |
| email | VARCHAR(150) | unique, nullable |
| password_hash | VARCHAR(255) | nullable if using OTP-only auth; managed by .NET auth service |
| role | ENUM('farmer','buyer','chc_official','admin') | drives dashboard routing |
| preferred_language | ENUM('en','hi','pa') | for bilingual UI |
| is_verified | BOOLEAN | phone/OTP or email verified |
| auth_provider_id | VARCHAR(255) | external ID from .NET Identity provider, if applicable |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### Table: `farmer_profiles`

| Column | Type | Notes |
|---|---|---|
| id | UUID/BIGINT PK | |
| user_id | FK → users.id | 1:1 with users |
| default_location_lat | DECIMAL(9,6) | |
| default_location_lng | DECIMAL(9,6) | |
| address | VARCHAR(255) | |
| district | VARCHAR(100) | |
| state | VARCHAR(100) | Punjab / Haryana etc. |

### Table: `buyer_profiles`

| Column | Type | Notes |
|---|---|---|
| id | UUID/BIGINT PK | |
| user_id | FK → users.id | 1:1 with users |
| company_name | VARCHAR(150) | |
| procurement_radius_km | INT | used for proximity alerts |
| base_location_lat | DECIMAL(9,6) | |
| base_location_lng | DECIMAL(9,6) | |

### Table: `chc_officials`

| Column | Type | Notes |
|---|---|---|
| id | UUID/BIGINT PK | |
| user_id | FK → users.id | 1:1 with users |
| chc_id | FK → chcs.id | which Custom Hiring Centre they manage |
| designation | VARCHAR(100) | |

### Table: `farms`

| Column | Type | Notes |
|---|---|---|
| id | UUID/BIGINT PK | |
| farmer_id | FK → farmer_profiles.id | |
| crop_type | VARCHAR(100) | e.g. Paddy |
| crop_variety | VARCHAR(100) | |
| sowing_date | DATE | |
| farm_size_acres | DECIMAL(6,2) | |
| location_lat | DECIMAL(9,6) | |
| location_lng | DECIMAL(9,6) | |
| created_at | TIMESTAMP | |

### Table: `harvest_predictions`

| Column | Type | Notes |
|---|---|---|
| id | UUID/BIGINT PK | |
| farm_id | FK → farms.id | |
| predicted_harvest_date | DATE | ML output |
| manual_override_date | DATE | nullable — farmer override |
| model_version | VARCHAR(50) | for traceability |
| weather_snapshot | JSON | agro-climatic inputs used |
| created_at | TIMESTAMP | |

### Table: `listings` (Sell Requests)

| Column | Type | Notes |
|---|---|---|
| id | UUID/BIGINT PK | |
| farm_id | FK → farms.id | |
| farmer_id | FK → farmer_profiles.id | denormalized for query convenience |
| tonnage_available | DECIMAL(8,2) | |
| listing_type | ENUM('auto_prelisting','manual','instant') | |
| status | ENUM('pending','active','matched','closed','cancelled') | |
| target_harvest_date | DATE | |
| price_expectation_per_ton | DECIMAL(10,2) | nullable |
| created_at | TIMESTAMP | |

### Table: `buy_requests`

| Column | Type | Notes |
|---|---|---|
| id | UUID/BIGINT PK | |
| buyer_id | FK → buyer_profiles.id | |
| tonnage_required | DECIMAL(10,2) | |
| proposed_rate_per_ton | DECIMAL(10,2) | |
| status | ENUM('open','partially_matched','fulfilled','closed') | |
| created_at | TIMESTAMP | |

### Table: `matches`

| Column | Type | Notes |
|---|---|---|
| id | UUID/BIGINT PK | |
| listing_id | FK → listings.id | |
| buy_request_id | FK → buy_requests.id | |
| distance_km | DECIMAL(6,2) | from Distance Matrix API |
| match_status | ENUM('suggested','negotiating','accepted','rejected') | |
| agreed_rate_per_ton | DECIMAL(10,2) | nullable until accepted |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### Table: `negotiations` (Messages)

| Column | Type | Notes |
|---|---|---|
| id | UUID/BIGINT PK | |
| match_id | FK → matches.id | |
| sender_id | FK → users.id | |
| message_text | TEXT | |
| sent_at | TIMESTAMP | |

### Table: `chcs` (Custom Hiring Centres)

| Column | Type | Notes |
|---|---|---|
| id | UUID/BIGINT PK | |
| name | VARCHAR(150) | |
| region | VARCHAR(100) | |
| location_lat | DECIMAL(9,6) | |
| location_lng | DECIMAL(9,6) | |

### Table: `balers`

| Column | Type | Notes |
|---|---|---|
| id | UUID/BIGINT PK | |
| chc_id | FK → chcs.id | |
| machine_code | VARCHAR(50) | |
| status | ENUM('available','in_use','maintenance') | |
| last_updated | TIMESTAMP | |

### Table: `baler_bookings`

| Column | Type | Notes |
|---|---|---|
| id | UUID/BIGINT PK | |
| baler_id | FK → balers.id | |
| farmer_id | FK → farmer_profiles.id | |
| booking_date | DATE | |
| status | ENUM('requested','confirmed','completed','cancelled') | |

### Table: `transactions` (Procurement & Delivery)

| Column | Type | Notes |
|---|---|---|
| id | UUID/BIGINT PK | |
| match_id | FK → matches.id | |
| tonnage_delivered | DECIMAL(10,2) | |
| pickup_date | DATE | |
| delivery_status | ENUM('scheduled','in_transit','delivered','cancelled') | |
| payment_status | ENUM('pending','partial','paid') | |
| final_rate_per_ton | DECIMAL(10,2) | |

### Table: `notifications`

| Column | Type | Notes |
|---|---|---|
| id | UUID/BIGINT PK | |
| user_id | FK → users.id | |
| type | VARCHAR(50) | e.g. 'new_match', 'pre_harvest_alert' |
| message | TEXT | |
| is_read | BOOLEAN | |
| created_at | TIMESTAMP | |

### Relationships Summary

- `users` 1─1 `farmer_profiles` / `buyer_profiles` / `chc_officials` (role-specific extension tables)
- `farmer_profiles` 1─N `farms` → 1─N `harvest_predictions`, 1─N `listings`
- `buyer_profiles` 1─N `buy_requests`
- `listings` N─N `buy_requests` resolved via `matches`
- `matches` 1─N `negotiations`, 1─1 (or 1─N) `transactions`
- `chcs` 1─N `balers` → `balers` 1─N `baler_bookings`
- `users` 1─N `notifications`

### MySQL vs. Supabase (PostgreSQL) Notes

| Aspect | MySQL | Supabase (PostgreSQL) |
|---|---|---|
| Primary keys | `BIGINT AUTO_INCREMENT` or `CHAR(36)` for UUID | native `UUID` type with `gen_random_uuid()` |
| JSON columns | `JSON` type (e.g. `weather_snapshot`) | native `JSONB`, indexable |
| Geospatial | `POINT`/`DECIMAL` lat-lng pairs, or MySQL spatial extensions | can use `PostGIS` extension for true geospatial queries |
| Auth integration | Managed separately (this project's .NET service) or via phpMyAdmin-hosted instance | Supabase has built-in Auth — if chosen, may reduce/replace some .NET auth responsibilities, but current plan keeps .NET as the auth layer regardless |
| Realtime features | None built-in — needs polling or a message broker for notifications/matching alerts | Supabase Realtime can push DB changes directly (useful for live notifications, baler status, incoming offers) |
| Hosting | phpMyAdmin-managed instance per current stack notes | Supabase-managed Postgres, integrates well with Render/Vercel deployment |

**Decision pending** — the schema above is written to be portable between both; ENUM columns and JSON fields are the only points needing adjustment for PostgreSQL's stricter typing (Postgres ENUM types or CHECK constraints instead of MySQL's inline ENUM).

## Authentication Layer (.NET)

The authentication layer is a separate ASP.NET Core service responsible for identity, credential management, and token issuance. FastAPI does not manage passwords or sessions directly — it only validates tokens issued by this service.

### General Auth Flow

1. **Registration** — user (farmer/buyer/CHC official) signs up via phone number and/or email through the frontend, which calls the .NET auth service. Role is captured at signup.
2. **Verification** — OTP verification (recommended for farmers, given phone-first usage) or email verification link.
3. **Login** — credentials (phone+OTP, or email+password) are validated by the .NET service.
4. **Token issuance** — on successful login, the .NET service issues:
   - an **access token** (short-lived, contains user ID, role, and expiry as claims)
   - a **refresh token** (longer-lived, used to obtain new access tokens without re-login)
5. **Token usage** — the frontend attaches the access token to every request to the FastAPI backend via the `Authorization: Bearer <token>` header.
6. **Token validation** — FastAPI validates the token's signature and expiry on each request (using a shared signing key or the .NET service's public key/JWKS endpoint) and extracts the user's identity and role for authorization checks — without needing to call the .NET service on every request.
7. **Refresh** — when the access token expires, the frontend calls the .NET service's refresh endpoint with the refresh token to obtain a new access token.
8. **Logout / revocation** — refresh tokens are invalidated server-side on logout; the .NET service maintains a revocation list or short refresh-token lifetimes to limit exposure.

### Role-Based Authorization

- Each issued token carries a `role` claim (`farmer`, `buyer`, `chc_official`, `admin`).
- FastAPI route dependencies check this claim to restrict access — e.g., only `chc_official` tokens can call baler-status-update or analytics endpoints; only `farmer` tokens can create farm/listing records for themselves.
- The `user_id` claim ties every action back to the corresponding row in the `users` table (and its role-specific profile table) for data ownership checks.

### Why a Separate .NET Service

- Keeps identity/credential management isolated from core business logic — the FastAPI backend never touches raw passwords.
- Allows the auth service to evolve independently (e.g., adding OAuth/social login, multi-factor auth) without changing the FastAPI API surface, as long as the token contract (claims format, signing method) stays stable.
- The two services can share the same underlying database (`users` and related auth tables owned by .NET, business tables owned by FastAPI) or use separate databases, depending on final infrastructure decisions.

### Open Decisions (flagged for later)

- Exact .NET auth mechanism (ASP.NET Core Identity, custom JWT issuance, or a hybrid with OTP) — not yet finalized.
- Whether the auth service and FastAPI backend share one database or communicate purely via token claims with fully separate stores.
- Whether Supabase's built-in Auth is used alongside or instead of parts of the .NET layer, if Supabase is the final database choice.

## Security Notes

- All inter-service calls (frontend ↔ .NET, frontend ↔ FastAPI) should be over HTTPS.
- Access tokens should be short-lived (e.g., 15–30 min); refresh tokens stored securely (httpOnly cookies preferred over local storage).
- Role checks must be enforced server-side in FastAPI, never trusted from the frontend alone.
- Sensitive fields (phone numbers, location data) should be access-controlled — e.g., a buyer only sees a farmer's contact details after a match is accepted.
- Rate-limit OTP requests and login attempts to prevent abuse.

---
*Source: ResidueLink Project Summary (SIH 2026), extended with backend/database/auth design details.*
