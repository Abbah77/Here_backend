#!/bin/bash
echo "🚀 Starting Here Backend..."
echo "📊 Supabase URL: $SUPABASE_URL"
echo "🔧 Debug mode: $DEBUG"

# Run the app
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}