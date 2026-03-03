@echo off
echo Starting Antigravity PC Agent...

:: Start Backend Agent
start "Agent Backend" cmd /k "cd agent && python main.py"

:: Start Frontend UI
start "Agent Frontend" cmd /k "cd frontend && npm run dev"

:: Start Cloudflare Secure Tunnel
echo Launching Cloudflare Tunnel (agent-tunnel)...
start "Cloudflare Tunnel" cmd /k "cloudflared tunnel run agent-tunnel"

echo All services started!
echo Backend: back.tatinenikarthik.online
echo Frontend: http://localhost:3001
pause
