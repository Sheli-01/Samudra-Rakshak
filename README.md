# Samudra-Rakshak
# 🌊 Samudra Rakshak

**Samudra Rakshak** ("Ocean Protector") is a real-time monitoring system for maritime safety, connecting an autonomous vessel, a sensor buoy, and a base station to a live dashboard.

![Status](https://img.shields.io/badge/status-in--development-yellow)
![Python](https://img.shields.io/badge/python-3.x-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 📖 Overview

The system collects live telemetry (location, sensor readings, connectivity status) from three hardware nodes and streams it to a web dashboard in real time:

| Node | Hardware | Role |
|------|----------|------|
| **Vessel** | ESP32 | Reports GPS position and vessel telemetry |
| **Buoy** | Raspberry Pi | Reports GPS position and environmental sensor data |
| **Base Station** | — | Relays messages between nodes and the backend |

Data flows into a unified Flask backend, which exposes both a **REST API** (for history/status queries) and a **WebSocket** feed (for live dashboard updates).

## 🏗️ Architecture

```
 ┌──────────┐      ┌─────────┐      ┌──────────────┐      ┌───────────┐
 │  Vessel  │ ───▶ │         │      │              │      │           │
 │ (ESP32)  │      │  Base   │ ───▶ │   Backend    │ ───▶ │ Dashboard │
 ├──────────┤      │ Station │      │ (Flask +     │      │ (Frontend)│
 │   Buoy   │ ───▶ │         │      │  Socket.IO)  │      │           │
 │(Raspberry│      │         │      │              │      │           │
 │   Pi)    │      └─────────┘      └──────────────┘      └───────────┘
 └──────────┘
```

- **REST API** — nodes POST readings, dashboards GET history/status
- **WebSocket (Socket.IO)** — pushes live updates to connected dashboards the moment new data arrives
- **In-memory store** — last 1000 readings per node (deque-based), no database required for the free-tier deployment

## 🚀 Tech Stack

- **Backend:** Python, Flask, Flask-SocketIO, Flask-CORS
- **Frontend:** [add your stack here, e.g. React, hosted on CodeSandbox]
- **Hardware:** ESP32 (vessel), Raspberry Pi (buoy)

## 📡 API Reference

### Vessel
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/vessel/data` | Submit vessel telemetry |
| GET | `/api/vessel/latest` | Get latest vessel reading |
| GET | `/api/vessel/history?limit=100` | Get vessel history |

### Buoy
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/buoy/data` | Submit buoy telemetry |
| GET | `/api/buoy/latest` | Get latest buoy reading |
| GET | `/api/buoy/history?limit=100` | Get buoy history |

### Base Station
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/basestation/data` | Submit base station data |
| GET | `/api/basestation/latest` | Get latest base station data |
| GET | `/api/basestation/history?limit=100` | Get base station history |

### System
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/all/latest` | Get latest data from all sources |
| GET | `/api/status` | Get online/offline status of each node |
| GET | `/api/health` | Health check |

### WebSocket Events
| Event | Direction | Description |
|-------|-----------|-------------|
| `vessel_update` | server → client | Emitted on new vessel data |
| `buoy_update` | server → client | Emitted on new buoy data |
| `basestation_update` | server → client | Emitted on new base station data |
| `request_all_data` | client → server | Request a full snapshot of current data |

## 📂 Project Structure

```
samudra-rakshak/
├── backend/          # Flask API + WebSocket server
├── firmware/          # ESP32 (vessel) and Raspberry Pi (buoy) code
├── frontend/          # Dashboard web app
├── docs/              # Architecture notes, diagrams, screenshots
└── README.md
```

## 🛠️ Getting Started

```bash
# Clone the repo
git clone https://github.com/Sheli-01/samudra-rakshak.git
cd samudra-rakshak/backend

# Install dependencies
pip install -r requirements.txt

# Run the server
python backend_server.py
```

The server starts on `http://localhost:8000` by default (override with the `PORT` env variable).

## 🗺️ Roadmap

- [ ] Persistent database (replace in-memory deque storage)
- [ ] Authentication for node/API access
- [ ] Historical data visualization on dashboard
- [ ] Alerting system for anomalies (e.g. vessel offline, sensor thresholds)

## 🤝 Contributing

Contributions, issues, and feature requests are welcome. Feel free to open a PR against `dev`.

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
