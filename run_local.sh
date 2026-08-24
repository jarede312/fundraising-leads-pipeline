#!/bin/bash
# Local development server - mimics Render environment
# Usage: ./run_local.sh

set -e

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found"
    echo "Create a .env file with your PG_DSN and ANTHROPIC_API_KEY"
    exit 1
fi

# Load environment variables
set -a
source .env
set +a

# Install dependencies if needed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
fi

# Run the app
echo "🚀 Starting server on http://localhost:8000"
echo "Press Ctrl+C to stop"
uvicorn webapp.main:app --reload --host 0.0.0.0 --port 8000
