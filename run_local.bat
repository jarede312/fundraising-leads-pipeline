@echo off
REM Local development server - mimics Render environment
REM Usage: run_local.bat

if not exist .env (
    echo Error: .env file not found
    echo Create a .env file with your PG_DSN and ANTHROPIC_API_KEY
    exit /b 1
)

REM Load .env file
for /f "delims== tokens=1,2" %%a in (.env) do (
    if "%%a"=="PG_DSN" set PG_DSN=%%b
    if "%%a"=="ANTHROPIC_API_KEY" set ANTHROPIC_API_KEY=%%b
    if "%%a"=="LLM_MODEL" set LLM_MODEL=%%b
    if "%%a"=="USER_AGENT" set USER_AGENT=%%b
)

REM Install dependencies if needed
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
)

REM Run the app
echo.
echo Starting server on http://localhost:8000
echo Press Ctrl+C to stop
echo.
uvicorn webapp.main:app --reload --host 0.0.0.0 --port 8000
