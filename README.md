# CPAP Analyzer

AI-powered CPAP sleep data analysis for ResMed AirSense machines. Upload your SD card data and get interactive charts, trend analysis, and AI-generated reports you can actually understand.

## What It Does

- **📊 Interactive Charts** — Pressure, leak, respiratory rate, tidal volume for every night
- **📈 Long-term Trends** — AHI over time, compliance rates, leak patterns across months
- **🤖 AI Reports** — Get a human-readable analysis of any night's data
- **💬 AI Q&A** — Ask questions about your sleep data in plain English ("Is my mask leaking too much?")
- **🗓️ Session Browser** — 216+ nights of data, sortable, with AHI color coding

## Quick Start

### 1. Install dependencies

```bash
cd backend
pip install -r requirements.txt

cd ../frontend
npm install
```

### 2. Load your CPAP data

Put your ResMed SD card data somewhere on your machine, then:

```bash
cd backend
python load_data.py /path/to/your/CPAP-Data-backup
```

Or zip the SD card folder and upload it through the web UI.

### 3. Configure AI (optional)

```bash
cp backend/.env.example backend/.env
# Edit backend/.env with your API key
```

### 4. Run it

```bash
# Terminal 1 — Backend
cd backend
uvicorn app.main:app --port 8000

# Terminal 2 — Frontend
cd frontend
npm run dev
```

Open **http://localhost:3000**

## Pages

| Page | URL | What |
|------|-----|------|
| Upload | `/` | Upload a zip of your SD card data |
| Sessions | `/sessions` | Browse all nights with AHI badges |
| Session Detail | `/sessions/{id}` | Charts, events, AI report, Q&A |
| Trends | `/trends` | AHI/duration/leak/pressure over time |
| AI Chat | `/ai` | Full chat interface with AI assistant |

## How to Get Your Data

1. Remove the SD card from your ResMed machine
2. Copy the entire SD card contents to your computer
3. The folder should contain `DATALOG/`, `Identification.json`, `STR.edf`, etc.
4. Either zip it and upload, or use `load_data.py` directly

## AI Configuration

The AI features use an OpenAI-compatible API. Edit `backend/.env`:

```env
OPENAI_API_KEY=your-key-here
OPENAI_BASE_URL=https://api.synthetic.new/openai/v1
OPENAI_MODEL=hf:moonshotai/Kimi-K2.6
```

Any OpenAI-compatible endpoint works — swap the URL and model as needed.

## Architecture

```
cpap-analyzer/
├── backend/               # Python FastAPI
│   ├── app/
│   │   ├── api/           # REST endpoints
│   │   │   ├── upload.py  # Zip upload + processing
│   │   │   ├── sessions.py# Session CRUD + signal data
│   │   │   ├── analytics.py# Trends + overview stats
│   │   │   └── ai.py      # Report generation + Q&A
│   │   ├── models/        # SQLAlchemy + Pydantic schemas
│   │   ├── parsers/       # ResMed EDF file parsers
│   │   └── services/      # Data extraction orchestration
│   ├── edf_lib/           # EDF/EDF+ binary format reader
│   ├── load_data.py       # CLI data loader
│   └── requirements.txt
├── frontend/              # Next.js + Recharts + Tailwind
│   └── src/app/           # App router pages
└── README.md
```

## What Gets Parsed

| File Type | Contents | Signals |
|-----------|----------|---------|
| **BRP** | High-res waveforms (25Hz) | Flow Rate (L/min), Mask Pressure, Resp Events |
| **PLD** | Low-res summaries (0.5Hz) | Pressure, Leak (L/min), RR, MV, TV (mL), Snore, FLG |
| **EVE** | Scored events | Obstructive Apnea, Central Apnea, Hypopnea, Arousal |
| **SA2** | Oximetry (1Hz) | Pulse (bpm), SpO₂ (%) |
| **STR** | Daily summaries | AHI, OAI, CAI, HI, leak/pressure stats, device settings |

## Data Privacy

All data is processed and stored locally on your machine. The SQLite database and uploaded files never leave your computer. AI features send only summary statistics (AHI, event counts, percentile data) to the AI API — never raw waveforms.

## EDF Parsing

The EDF parsing logic is a Python port of [OSCAR](https://github.com/MaynardHandley/OSCAR-code)'s C++ ResMed loader (`resmed_loader.cpp`, `edfparser.cpp`, `resmed_EDFinfo.cpp`). Key details:

- Reads EDF/EDF+ headers with custom header sizes (ResMed uses 1024–20224 byte headers)
- Applies ResMed-specific gain transforms (flow rate × 60 for L/min, tidal volume × 1000 for mL)
- Handles ResMed's sentinel values (-0.1, -0.02, -1.0) for missing data
- Parses EDF+ annotations for event scoring (apneas, hypopneas, arousals)
- STR file date decoding (days since Unix epoch 1970-01-01)

## Tech Stack

- **Backend**: Python 3.9+, FastAPI, SQLAlchemy, NumPy
- **Frontend**: Next.js 16, React, Recharts, Tailwind CSS, TypeScript
- **Database**: SQLite (zero config, single file)
- **AI**: OpenAI-compatible API (Kimi K2.6, 256k context)

## Unraid

Install from the Community Applications store, or run manually:

1. Go to **Apps** → search for **CPAP Analyzer**
2. Install with default settings
3. Copy your ResMed SD card data to your Unraid share
4. Open the container console and run:
   ```bash
   python /app/backend/load_data.py /data/sd_card
   ```
5. Restart the container
6. Open the WebUI

Or use Docker Compose from the repo for the standard two-container setup.
