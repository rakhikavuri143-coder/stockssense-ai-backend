# 📈 StockSense AI — Autonomous Indian Stock Market AI Trading & Signal Engine

> **B.Tech Final Year Capstone Project**  
> An end-to-end autonomous trading decision-support and paper trading system for Nifty 50 stocks, combining Gemini 2.5 Flash AI reasoning, technical indicators, 10 capital protection guards, and real-time Telegram alerts.

---

## 🌟 Key Features

- **🧠 Multi-Agent AI Analysis**: Powered by Google Gemini AI to analyze price action, technical structure, and real-time market sentiment.
- **🛡️ 10 Capital Protection Guards**:
  1. Sector Trend Guard
  2. VWAP Alignment Guard
  3. Nifty Macro Trend Guard
  4. Daily Loss Circuit Breaker
  5. Market Hours Guard (09:15 AM - 03:30 PM IST)
  6. Midday Dead-Zone Guard (11:30 AM - 01:30 PM IST)
  7. Risk-Reward Ratio Enforcer (Min 1:1.5)
  8. Historical Event Reaction Evaluator
  9. Structural Resistance & Support Scanner
  10. Auto-Exit Monitor (Trailing Stop Loss & Profit Lock)
- **⚡ Parallel Streaming Auto-Scan**: 3-minute auto-refresh countdown scanning Nifty 50 stocks asynchronously.
- **📱 Real-time Telegram Bot Alerts**: Instant alerts for BUY/SELL signals, order placements, SL/Target hits, and EOD performance reports.
- **📊 4-Week Paper Trading Simulator**: Virtual trade management with ₹10,000 initial capital buffer.

---

## 🏗️ Architecture & Tech Stack

- **Backend**: Python 3.13, FastAPI, APScheduler, SQLAlchemy (SQLite & MySQL support)
- **AI & Sentiment**: Google Gemini API, NewsFetcher
- **Frontend**: Vanilla JavaScript (ES6+), Modern Glassmorphism CSS UI, Server-Sent Events (SSE)
- **Alerts**: Telegram Bot API

---

## 🚀 Quick Start & Setup

### 1. Clone Repository
```bash
git clone https://github.com/YOUR_USERNAME/stocksense-ai.git
cd stocksense-ai
```

### 2. Environment Setup
Create a `.env` file in the root directory (copy from `.env.example`):
```bash
cp .env.example .env
```
Fill in your credentials:
```env
GEMINI_API_KEY=your_gemini_api_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
PAPER_CAPITAL=10000
```

### 3. Install Dependencies
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Run the Server
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
Open **`http://localhost:8000`** in your browser.

---

## 📱 Telegram Alerts Demonstration

- **Signal Alert**: Sent automatically when high-confidence BUY/SELL opportunities are detected during auto-scans.
- **Trade Execution**: Alerts triggered upon paper trade opening and closing (Target 1, Target 2, Stop Loss).
- **Daily Summary**: Auto-pushed at 03:30 PM IST with win rate and total P&L.

---

## 📜 License & Disclaimer

This project is created for educational and academic research purposes as a B.Tech capstone project. It does not constitute financial or investment advice.
