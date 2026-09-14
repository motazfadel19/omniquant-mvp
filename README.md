# OmniQuant MVP

This project is a minimal Python backend for a trading signal and MT5 bridge prototype.

## Structure

```text
omniquant-mvp/
├── backend/
│   ├── main.py
│   ├── mt5_bridge.py
│   ├── database.py
│   ├── models.py
│   └── requirements.txt
├── frontend/
│   └── (coming soon)
└── README.md
```

## Quick Start

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open:

- http://127.0.0.1:8000/
- http://127.0.0.1:8000/health
- http://127.0.0.1:8000/docs

## Notes

- The backend is designed to be easy to expand.
- MT5 integration is handled through a wrapper so the app can start without the MetaTrader package installed.
- SQLite is initialized with a simple schema for accounts and trading signals.
