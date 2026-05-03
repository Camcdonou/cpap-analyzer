#!/bin/bash
# Start CPAP Analyzer (backend + frontend)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "🏥 Starting CPAP Analyzer..."

# Start backend
echo "📡 Starting backend on port 8000..."
cd backend
if [ ! -f cpap.db ]; then
    echo "   No database found. Run: python load_data.py /path/to/sd_card"
fi
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start frontend
echo "🎨 Starting frontend on port 3000..."
cd ../frontend
npm run dev -- -p 3000 &
FRONTEND_PID=$!

echo ""
echo "✅ CPAP Analyzer is running!"
echo "   Frontend: http://localhost:3000"
echo "   Backend:  http://localhost:8000"
echo "   API docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM

wait
