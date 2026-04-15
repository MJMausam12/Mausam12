import asyncio
import json
import time
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List

import aiosqlite
import uvicorn
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------- Global State -------------------
# Store the latest 1‑second candle (OHLCV)
latest_candle = {
    "time": 0,           # Unix timestamp in seconds
    "open": 0.0,
    "high": 0.0,
    "low": 0.0,
    "close": 0.0,
    "volume": 0.0,
}
# Keep a rolling window of candles for chart initial load
candle_history = deque(maxlen=300)  # last 5 minutes at 1s

# Active WebSocket connections for frontend clients
clients: List[WebSocket] = []

# Alert storage
DB_PATH = "alerts.db"

# ------------------- Database Setup -------------------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                signal TEXT NOT NULL,
                confidence REAL NOT NULL,
                price REAL NOT NULL,
                entry_price REAL,
                exit_price REAL
            )
        """)
        await db.commit()

# ------------------- Binance Trade Stream Aggregator -------------------
async def binance_trade_stream():
    """
    Connects to Binance WebSocket for BTCUSDT trades,
    aggregates into 1‑second candles, and updates latest_candle.
    """
    uri = "wss://stream.binance.com:9443/ws/btcusdt@trade"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                print("Connected to Binance WebSocket")
                current_sec = int(time.time())
                candle = {
                    "time": current_sec,
                    "open": 0.0,
                    "high": -1e9,
                    "low": 1e9,
                    "close": 0.0,
                    "volume": 0.0,
                }
                async for msg in ws:
                    data = json.loads(msg)
                    price = float(data['p'])
                    qty = float(data['q'])
                    trade_time = data['T'] // 1000  # ms to seconds

                    # Check if we crossed a second boundary
                    if trade_time != current_sec:
                        # Finalize previous candle
                        if candle["open"] != 0.0:
                            candle_history.append(candle.copy())
                            global latest_candle
                            latest_candle = candle.copy()
                            # Broadcast to all frontend clients
                            await broadcast_candle(latest_candle)
                            # Generate a placeholder alert (replace with real AI model)
                            await maybe_generate_alert(latest_candle)

                        # Start new candle
                        current_sec = trade_time
                        candle = {
                            "time": current_sec,
                            "open": price,
                            "high": price,
                            "low": price,
                            "close": price,
                            "volume": qty,
                        }
                    else:
                        # Update current candle
                        candle["high"] = max(candle["high"], price)
                        candle["low"] = min(candle["low"], price)
                        candle["close"] = price
                        candle["volume"] += qty

        except Exception as e:
            print(f"Binance WebSocket error: {e}, reconnecting in 5s...")
            await asyncio.sleep(5)

# ------------------- Frontend Broadcast -------------------
async def broadcast_candle(candle: dict):
    """Send new candle to all connected WebSocket clients."""
    if not clients:
        return
    message = json.dumps({"type": "candle", "data": candle})
    disconnected = []
    for ws in clients:
        try:
            await ws.send_text(message)
        except:
            disconnected.append(ws)
    for ws in disconnected:
        clients.remove(ws)

# ------------------- Placeholder AI Alert Generator -------------------
async def maybe_generate_alert(candle: dict):
    """
    Dummy AI: random signal with confidence.
    Replace this with your real model inference.
    """
    import random
    if random.random() > 0.85:  # ~15% chance to generate an alert
        signal = random.choice(["BUY", "SELL"])
        confidence = random.uniform(0.70, 0.99)
        price = candle["close"]

        # Save to database
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO alerts (timestamp, signal, confidence, price) VALUES (?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), signal, confidence, price)
            )
            await db.commit()

        # Broadcast alert to all clients
        alert_msg = json.dumps({
            "type": "alert",
            "data": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "signal": signal,
                "confidence": round(confidence, 4),
                "price": price
            }
        })
        for ws in clients:
            try:
                await ws.send_text(alert_msg)
            except:
                pass

# ------------------- FastAPI Routes -------------------
@app.on_event("startup")
async def startup():
    await init_db()
    asyncio.create_task(binance_trade_stream())

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the frontend HTML file."""
    with open("../frontend/index.html", "r") as f:
        return f.read()

@app.get("/api/history")
async def get_candle_history():
    """Return recent candles for chart initialization."""
    return list(candle_history)

@app.get("/api/alerts")
async def get_alerts(limit: int = 50):
    """Fetch recent alerts from database."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT * FROM alerts ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )
        rows = await cursor.fetchall()
        alerts = []
        for row in rows:
            alerts.append({
                "id": row[0],
                "timestamp": row[1],
                "signal": row[2],
                "confidence": row[3],
                "price": row[4],
                "entry_price": row[5],
                "exit_price": row[6],
            })
        return alerts

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.append(websocket)
    try:
        while True:
            # Keep connection alive; client may send pings
            data = await websocket.receive_text()
            # You could handle client commands here
    except WebSocketDisconnect:
        clients.remove(websocket)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
