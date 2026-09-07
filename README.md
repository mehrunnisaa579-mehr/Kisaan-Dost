# KisaanDost 🌾
> An AI farming assistant for Pakistani farmers — voice-first, multilingual (Urdu, Roman Urdu, English, Punjabi, Siraiki).

---

## 🚀 What It Does

**KisaanDost** is a comprehensive agricultural assistant designed specifically for Pakistani farmers to help them diagnose crop issues, manage weather risks, and check market rates in their native language:

- **Multilingual Voice & Text Crop Diagnosis:** Send text queries or record voice notes in Urdu, Roman Urdu, English, Punjabi, or Siraiki along with crop photos for instant diagnostic feedback.
- **Weather-Based Spray & Irrigation Advice:** Fetches live weather metrics and 48-hour forecasts to deliver actionable spray safety warnings and watering recommendations.
- **Live Mandi Rates:** Scrapes live market rates from AMIS Punjab (with reliable local fallback datasets) for major Pakistani crops across 17+ regional cities.
- **Local RAG Knowledge Engine:** Employs a zero-dependency keyword-scoring Retrieval-Augmented Generation engine tailored for Cotton, Wheat, and Mango farming guidelines.

---

## 🛠️ Tech Stack

- **Frontend:** React Native (Expo SDK 54, Expo-AV, Expo-Location, Expo-Image-Picker)
- **Backend:** FastAPI (Python), Uvicorn
- **AI & Speech Engine:** Google Gemini API (`google-generativeai` SDK) for multimodal reasoning, STT, and TTS
- **Weather Data:** Open-Meteo API
- **Market Data:** AMIS Punjab (Agriculture Market Information System)

---

## 📁 Project Structure

```
.
├── backend/
│   ├── agents/            # 7-agent diagnostic pipeline
│   ├── cotton/            # Cotton crop knowledge base (.md)
│   ├── mango/             # Mango crop knowledge base (.md)
│   ├── wheat/             # Wheat crop knowledge base (.md)
│   ├── routers/           # FastAPI routers (/analyze, /voice-analyze, /tts, /weather)
│   ├── services/          # Core services (Gemini, Key Manager, RAG, Mandi, Weather, STT, TTS)
│   ├── utils/             # Helper functions, constants & language detection
│   ├── main.py            # FastAPI entry point
│   ├── requirements.txt   # Python backend dependencies
│   └── .env.example       # Environment variables template
│
└── frontend/
    ├── assets/            # App icons and splash images
    ├── components/        # Reusable UI components
    ├── services/          # API client integration (api.js)
    ├── utils/             # Frontend formatters and helpers
    ├── App.js             # React Native main app entry & navigation
    ├── app.json           # Expo project configuration
    └── package.json       # React Native dependencies
```

---

## ⚙️ Getting Started

### 1. Backend Setup

1. **Navigate to the backend directory:**
   ```bash
   cd backend
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   Copy `.env.example` to `.env` and add your Google Gemini API Key:
   ```bash
   cp .env.example .env
   ```
   *Required variables in `.env`:*
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   ```

4. **Start the Backend Server:**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```
   The backend will be running at `http://localhost:8000`.

---

### 2. Frontend Setup

1. **Navigate to the frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install Node dependencies:**
   ```bash
   npm install
   ```

3. **Update API Endpoint URL:**
   In `frontend/services/api.js`, update `BASE_URL` with your local machine's IP address (for physical device / Expo Go testing) or keep local host for emulator testing:
   ```javascript
   const BASE_URL = 'http://<YOUR_LOCAL_IP>:8000';
   ```

4. **Start the Expo Development Server:**
   ```bash
   npx expo start
   ```
   Scan the QR code using Expo Go on your mobile device or press `a` for Android Emulator / `i` for iOS Simulator.

---

## 📜 License

This project is licensed under the MIT License.
