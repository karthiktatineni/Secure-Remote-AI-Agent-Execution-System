import os
import subprocess
import json
import logging
import asyncio
import base64
import uuid
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import mss
import cv2
import numpy as np
from io import BytesIO
from PIL import Image
import pyautogui
from openai import OpenAI

# GUI safety settings
pyautogui.FAILSAFE = True  # Move mouse to corner to abort

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pc-agent")

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("AGENT_API_KEY")
AGENT_USERNAME = os.getenv("AGENT_USERNAME", "admin")
AGENT_PASSWORD = os.getenv("AGENT_PASSWORD", "password")

if not API_KEY:
    logger.warning("AGENT_API_KEY not set! Backend is INSECURE.")

app = FastAPI(title="Safe Remote PC Agent")

# Secure CORS - though for Cloudflare we might keep it broad or specific to Vercel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, set this to your Vercel URL
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security check for all requests
from fastapi import Header, Query
async def verify_api_key(x_api_key: str = Header(None), token: str = Query(None)):
    provided_key = x_api_key or token
    if API_KEY and provided_key != API_KEY:
        logger.warning(f"Auth failed: expected {API_KEY[:5]}..., got {provided_key[:5] if provided_key else 'None'}...")
        raise HTTPException(status_code=403, detail="Forbidden: Invalid API Key")

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/login")
async def login(req: LoginRequest):
    if req.username == AGENT_USERNAME and req.password == AGENT_PASSWORD:
        return {"status": "success", "token": API_KEY}
    raise HTTPException(status_code=401, detail="Invalid credentials")

# Configuration for Lightning AI (GPT-120B)
LIGHTNING_BASE_URL = os.getenv("LIGHTNING_BASE_URL", "https://lightning.ai/api/v1/")
LIGHTNING_API_KEY = os.getenv("LIGHTNING_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "lightning-ai/gpt-oss-120b")

if not LIGHTNING_API_KEY:
    logger.error("LIGHTNING_API_KEY not found in .env!")

client = OpenAI(
    base_url=LIGHTNING_BASE_URL,
    api_key=LIGHTNING_API_KEY,
)

# Simple in-memory store for pending actions and session history
pending_actions: Dict[str, dict] = {}
session_history: Dict[str, List[dict]] = {}

class PromptRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = None

class ApprovalRequest(BaseModel):
    action_id: str
    approved: bool
    session_id: Optional[str] = None

# WebSocket for real-time logs and screen
class ConnectionManager:
    def __init__(self):
        self.log_connections: List[WebSocket] = []
        self.screen_connections: List[WebSocket] = []

    async def connect_log(self, websocket: WebSocket):
        await websocket.accept()
        self.log_connections.append(websocket)

    def disconnect_log(self, websocket: WebSocket):
        self.log_connections.remove(websocket)

    async def broadcast_log(self, message: str):
        for connection in self.log_connections:
            try:
                await connection.send_text(message)
            except:
                pass

    async def connect_screen(self, websocket: WebSocket):
        await websocket.accept()
        self.screen_connections.append(websocket)

    def disconnect_screen(self, websocket: WebSocket):
        self.screen_connections.remove(websocket)

manager = ConnectionManager()

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket, token: str = Query(None)):
    if API_KEY and token != API_KEY:
        await websocket.close(code=1008)
        return
    await manager.connect_log(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_log(websocket)

@app.websocket("/ws/screen")
async def websocket_screen(websocket: WebSocket, token: str = Query(None)):
    logger.info(f"Screen WebSocket connecting... Token provided: {'Yes' if token else 'No'}")
    if API_KEY and token != API_KEY:
        logger.warning("Screen WebSocket connection rejected: Invalid Key")
        await websocket.close(code=1008)
        return
    await manager.connect_screen(websocket)
    logger.info("Screen WebSocket connected.")
    sct = mss.mss()
    monitor = sct.monitors[1]
    
    try:
        while True:
            sct_img = sct.grab(monitor)
            # logger.info(f"Frame captured, size: {sct_img.size}") # Too noisy for prod, keep commented but available
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            frame = cv2.resize(frame, (1280, 720))
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            await websocket.send_bytes(buffer.tobytes())
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        manager.disconnect_screen(websocket)
    except Exception as e:
        logger.error(f"Screen stream error: {e}")
        manager.disconnect_screen(websocket)

def get_system_context():
    """Gathers real-time context about the system state (RAG)."""
    try:
        active_window = "Unknown"
        try:
            import pygetwindow as gw
            win = gw.getActiveWindow()
            if win: active_window = win.title
        except: pass
        
        processes = []
        try:
            output = subprocess.check_output('powershell "Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object ProcessName, MainWindowTitle | ConvertTo-Json"', shell=True, text=True)
            if output:
                import json
                procs = json.loads(output)
                if isinstance(procs, list):
                    processes = [f"{p['ProcessName']} ({p['MainWindowTitle']})" for p in procs if p.get('MainWindowTitle')]
                else:
                    processes = [f"{procs['ProcessName']} ({procs['MainWindowTitle']})"] if procs.get('MainWindowTitle') else []
        except: pass
        
        return {
            "active_window": active_window,
            "running_processes": list(set(processes))[:25]
        }
    except Exception as e:
        logger.error(f"Context gathering error: {e}")
        return {}

@app.post("/run")
async def run_prompt(req: PromptRequest, x_api_key: str = Header(None)):
    await verify_api_key(x_api_key)
    session_id = req.session_id or str(uuid.uuid4())
    if session_id not in session_history:
        session_history[session_id] = []
    
    history = session_history[session_id]
    
    # GATHER SYSTEM CONTEXT (RAG)
    sys = get_system_context()
    
    logger.info(f"Received prompt for session {session_id}: {req.prompt}")
    await manager.broadcast_log(f"Thinking (120B + System Awareness)...")
    
    # Format history
    history_str = "\n".join([
        f"Step {i+1}: {h['action']} -> {h.get('result', 'Success')}"
        for i, h in enumerate(history)
    ]) if history else "Start of task."

    system_prompt = (
        "You are an ELITE PC AGENT with REAL-TIME SYSTEM AWARENESS.\n\n"
        "SYSTEM CONTEXT (RAG):\n"
        f"- ACTIVE WINDOW: {sys.get('active_window')}\n"
        f"- RUNNING PROCESSES: {', '.join(sys.get('running_processes', []))}\n\n"
        "ACTION HISTORY:\n"
        f"{history_str}\n\n"
        "ALLOWED ACTIONS (STRICTLY USE THESE ONLY):\n"
        "1. 'execute_shell': Run Powershell command. Use for launching apps (e.g., 'start brave'). Require 'command' field.\n"
        "2. 'type': Type text. Require 'parameters': {'text': '...'}.\n"
        "3. 'click': Click mouse. Optional 'parameters': {'x': ..., 'y': ...}. If omitted, clicks current pos.\n"
        "4. 'press': Press single key (e.g., 'enter'). Require 'parameters': {'key': '...'}.\n"
        "5. 'hotkey': Multiple keys (e.g., ['win', 'r']). Require 'parameters': {'keys': [...]}.\n"
        "6. 'wait': Wait seconds. Require 'parameters': {'seconds': ...}.\n"
        "7. 'done': Task finished. Require 'parameters': {'message': '...'}.\n\n"
        "STRICT RULES:\n"
        "1. USE 'execute_shell' with 'command' field for ANY system command like opening File Explorer (start explorer.exe) or launching browsers.\n"
        "2. DO NOT REPEAT actions that have already succeeded or are visible in the System Context.\n"
        "3. If an app is already in Running Processes, move to the next logical step.\n"
        "4. Output ONLY valid JSON.\n\n"
        "OUTPUT FORMAT (STRICT JSON):\n"
        "{\n"
        "  \"thought\": \"Verify system state and decide NEXT PROGRESSIVE step\",\n"
        "  \"action\": \"one of the allowed action names above\",\n"
        "  \"command\": \"powershell command if using execute_shell, else null\",\n"
        "  \"parameters\": {}\n"
        "}\n"
    )
    
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": req.prompt}
            ],
            temperature=0.1
        )
        
        raw_response = completion.choices[0].message.content.strip()
        
        # --- INDUSTRIAL-GRADE JSON RECOVERY ---
        def rescue_json(text):
            # 1. Direct Try
            try: return json.loads(text)
            except: pass
            
            import re
            
            # 2. Extract most complete { } block
            # Find the index of the first '{' and the last '}'
            start_idx = text.find('{')
            end_idx = text.rfind('}')
            
            if start_idx != -1 and end_idx != -1:
                fragment = text[start_idx:end_idx+1]
                
                # Try cleaning and loading
                try:
                    # Clean common LLM noise
                    c = fragment
                    c = re.sub(r'//.*', '', c) # Comments
                    c = re.sub(r',\s*([\]}])', r'\1', c) # Trailing commas
                    return json.loads(c)
                except:
                    # 3. DEEP KEY EXTRACTION (The 'Last Resort')
                    # If JSON is totally broken, we extract keys manually via regex
                    thought = re.search(r'"thought"\s*:\s*"(.*?)"', fragment, re.DOTALL)
                    action = re.search(r'"action"\s*:\s*"(.*?)"', fragment, re.DOTALL)
                    command = re.search(r'"command"\s*:\s*"(.*?)"', fragment, re.DOTALL)
                    
                    if action:
                        return {
                            "thought": thought.group(1).replace('\\"', '"') if thought else "Extracted from malformed output",
                            "action": action.group(1),
                            "command": command.group(1).replace('\\"', '"') if command else None,
                            "parameters": {}
                        }
            return None

        action_data = rescue_json(raw_response)
        
        if not action_data:
            # Final attempt: search for ANY 'action' string and 'command' string
            import re
            action_match = re.search(r'action["\s:]+([a-z_]+)', raw_response.lower())
            if action_match:
                action_data = {
                    "thought": "Emergency recovery from text",
                    "action": action_match.group(1),
                    "command": None,
                    "parameters": {}
                }
                # Check for command if shell
                cmd_match = re.search(r'command["\s:]+([^"}]+)', raw_response)
                if cmd_match: action_data["command"] = cmd_match.group(1).strip()
            else:
                raise ValueError(f"120B model produced unparseable garbage: {raw_response[:100]}")

        await manager.broadcast_log(f"Brain thought: {action_data.get('thought', 'Deciding next step...')}")
        
        # Store for approval
        action_id = str(uuid.uuid4())
        pending_actions[action_id] = {
            "session_id": session_id,
            "data": action_data
        }
        
        display_cmd = action_data.get("command") or f"{action_data.get('action')}({action_data.get('parameters', '')})"
        await manager.broadcast_log(f"AWAITING APPROVAL: {display_cmd}")
        
        return {
            "status": "pending", 
            "action_id": action_id, 
            "session_id": session_id,
            "action": action_data
        }
        
    except Exception as e:
        logger.error(f"Error in /run: {e}")
        await manager.broadcast_log(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/approve")
async def approve_action(req: ApprovalRequest, x_api_key: str = Header(None)):
    await verify_api_key(x_api_key)
    if req.action_id not in pending_actions:
        raise HTTPException(status_code=404, detail="Action not found")
    
    pending = pending_actions[req.action_id]
    session_id = pending["session_id"]
    action_data = pending["data"]
    
    if not req.approved:
        del pending_actions[req.action_id]
        await manager.broadcast_log(f"Action rejected by user.")
        return {"status": "rejected", "session_id": session_id}
    
    action = action_data.get("action")
    params = action_data.get("parameters", {})
    output = ""
    
    try:
        # Robustness: Map common hallucinations to standard actions
        action_mapping = {
            "run_command": "execute_shell",
            "execute": "execute_shell",
            "run": "execute_shell",
            "start_process": "execute_shell",
            "shell": "execute_shell",
            "open": "execute_shell"
        }
        
        effective_action = action_mapping.get(action, action)
        
        if effective_action == "execute_shell":
            command = action_data.get("command")
            if not command and effective_action != action:
                # If the hallucinated action passed the command in parameters
                command = params.get("command") or params.get("path")
            
            if not command:
                raise ValueError("No command provided for shell execution")

            await manager.broadcast_log(f"Executing: {command}")
            # Use list-based execution for safety against injection and quoting issues
            result = subprocess.run(["powershell", "-Command", command], capture_output=True, text=True, timeout=20)
            stdout = result.stdout if result.stdout is not None else ""
            stderr = result.stderr if result.stderr is not None else ""
            output = stdout + stderr
            
        elif action == "type":
            text = params.get("text", "")
            await manager.broadcast_log(f"Typing text...")
            pyautogui.typewrite(text, interval=0.02)
            output = f"Typed successfully"
            
        elif action == "click":
            x, y = params.get("x"), params.get("y")
            if x is not None and y is not None:
                pyautogui.click(x, y)
            else:
                pyautogui.click()
            output = f"Clicked"
            
        elif action == "press":
            key = params.get("key", "enter")
            pyautogui.press(key)
            output = f"Pressed {key}"
            
        elif action == "hotkey":
            keys = params.get("keys", [])
            pyautogui.hotkey(*keys)
            output = f"Ran hotkey {keys}"

        elif action == "wait":
            secs = params.get("seconds", 1)
            await asyncio.sleep(secs)
            output = f"Waited {secs}s"
            
        elif action == "done":
            output = params.get("message", "Task complete")
            await manager.broadcast_log(f"TASK COMPLETE: {output}")
            if session_id in session_history:
                del session_history[session_id]
            del pending_actions[req.action_id]
            return {"status": "finished", "message": output}
        
        else:
            output = f"Unknown action: {action}"

        # Update history
        if session_id not in session_history:
            session_history[session_id] = []
        
        session_history[session_id].append({
            "action": action,
            "parameters": params,
            "command": action_data.get("command"),
            "result": output[:200] # Cap result size
        })

        del pending_actions[req.action_id]
        await manager.broadcast_log(f"Action Success. Result: {output[:50]}...")
        
        return {
            "status": "success", 
            "session_id": session_id, 
            "last_action": action,
            "can_continue": True
        }
    except Exception as e:
        logger.error(f"Execution error: {e}")
        await manager.broadcast_log(f"Execution error: {str(e)}")
        return {"status": "error", "detail": str(e), "session_id": session_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
