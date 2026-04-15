# BTC 1-Second Signal Platform (Demo)

Real‑time Bitcoin trading signal dashboard with 1‑second candlesticks and AI‑ready alert pipeline.

> ⚠️ **Educational Project** – This is a starter template. The "AI" is a placeholder random generator. Replace it with your own trained model to achieve a target win rate.

## Features
- Live 1‑second OHLCV candles from Binance WebSocket
- TradingView Lightweight Charts integration
- Real‑time alert streaming via WebSockets
- Alert history stored in SQLite (easily swappable for TimescaleDB)
- FastAPI backend with async performance

## Quick Start

### Backend
```bash
cd backend
pip install -r requirements.txt
python main.py
