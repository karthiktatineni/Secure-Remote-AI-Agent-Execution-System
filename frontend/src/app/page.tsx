"use client";

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';

interface PendingAction {
  action_id: string;
  action: {
    thought: string;
    command: string;
    action: string;
  };
}

export default function Home() {
  const [prompt, setPrompt] = useState('');
  const [logs, setLogs] = useState<string[]>([]);
  const [screenSrc, setScreenSrc] = useState<string>('');
  const [isThinking, setIsThinking] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);
  const websocketLogRef = useRef<WebSocket | null>(null);
  const websocketScreenRef = useRef<WebSocket | null>(null);
  const router = useRouter();

  // Use environment variables for API and local storage for key
  const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'https://back.tatinenikarthik.online';

  useEffect(() => {
    const token = localStorage.getItem('agent_token');
    if (!token) {
      router.push('/login');
    } else {
      setIsAuthenticated(true);
      setupWebSockets(token);
    }

    return () => {
      websocketLogRef.current?.close();
      websocketScreenRef.current?.close();
    };
  }, []);

  const setupWebSockets = (token: string) => {
    // Determine WS protocol based on API URL
    const wsBase = API_BASE.replace(/^http/, 'ws');
    const wsSuffix = `?token=${token}`;

    // Log WebSocket
    const logWs = new WebSocket(`${wsBase}/ws/logs${wsSuffix}`);
    logWs.onmessage = (event) => {
      setLogs((prev) => [...prev, event.data]);
    };
    websocketLogRef.current = logWs;

    // Screen WebSocket
    const screenWs = new WebSocket(`${wsBase}/ws/screen${wsSuffix}`);
    screenWs.binaryType = 'arraybuffer';
    screenWs.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        const blob = new Blob([event.data], { type: 'image/jpeg' });
        const url = URL.createObjectURL(blob);
        setScreenSrc(url);
      }
    };
    websocketScreenRef.current = screenWs;
  };

  const handleLogout = () => {
    localStorage.removeItem('agent_token');
    router.push('/login');
  };

  const getApiKey = () => localStorage.getItem('agent_token') || '';

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const triggerNextStep = async (sessId: string, originalPrompt: string) => {
    setIsThinking(true);
    const token = getApiKey();
    try {
      const res = await fetch(`${API_BASE}/run`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': token
        },
        body: JSON.stringify({ prompt: originalPrompt, session_id: sessId }),
      });
      if (res.status === 403) throw new Error("API access denied!");
      const data = await res.json();

      if (data.status === 'pending') {
        setPendingAction({
          action_id: data.action_id,
          action: data.action
        });
      }
    } catch (err) {
      setLogs((prev) => [...prev, `[Error]: Failed to continue session`]);
    } finally {
      setIsThinking(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent, customPrompt?: string) => {
    e?.preventDefault();
    const activePrompt = customPrompt || prompt;
    if (!activePrompt.trim() || isThinking || pendingAction) return;

    setIsThinking(true);
    setLogs((prev) => [...prev, `[System]: Starting new task: ${activePrompt}`]);
    const token = getApiKey();
    try {
      const res = await fetch(`${API_BASE}/run`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': token
        },
        body: JSON.stringify({ prompt: activePrompt }),
      });

      if (res.status === 403) {
        setLogs((prev) => [...prev, `[System]: API access denied! check your key.`]);
        return;
      }

      const data = await res.json();

      if (data.status === 'pending') {
        setPendingAction({
          action_id: data.action_id,
          action: data.action
        });
        setCurrentSessionId(data.session_id);
      }
    } catch (err) {
      setLogs((prev) => [...prev, `[Error]: Failed to connect to agent`]);
    } finally {
      if (!customPrompt) setPrompt('');
      setIsThinking(false);
    }
  };

  const handleApproval = async (approved: boolean) => {
    if (!pendingAction || !currentSessionId) return;

    const originalPrompt = prompt || logs.find(l => l.includes('Starting new task:'))?.split(': ').pop() || "";

    const token = getApiKey();
    try {
      const res = await fetch(`${API_BASE}/approve`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': token
        },
        body: JSON.stringify({
          action_id: pendingAction.action_id,
          approved,
          session_id: currentSessionId
        }),
      });
      const data = await res.json();

      if (data.status === 'finished') {
        setLogs((prev) => [...prev, `[System]: Task completed: ${data.message}`]);
        setCurrentSessionId(null);
        setPendingAction(null);
      } else if (data.status === 'success' && data.can_continue) {
        setPendingAction(null);
        // Automatically trigger next step
        await triggerNextStep(currentSessionId, originalPrompt);
      } else {
        setLogs((prev) => [...prev, `[System]: Action ${approved ? 'completed' : 'rejected'}`]);
        setPendingAction(null);
        if (!approved) setCurrentSessionId(null);
      }
    } catch (err) {
      setLogs((prev) => [...prev, `[Error]: Failed to send approval`]);
      setPendingAction(null);
    }
  };


  return (
    <main className="flex flex-col h-screen bg-slate-950 text-slate-100 font-sans p-4 gap-4">
      {/* Header */}
      <header className="flex justify-between items-center px-4 py-2 glass rounded-2xl">
        <div className="flex items-center gap-3">
          <div className="status-dot bg-emerald-500" />
          <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-blue-400 to-emerald-400 bg-clip-text text-transparent">
            ANTIGRAVITY PC AGENT
          </h1>
        </div>
        <div className="flex items-center gap-6">
          <div className="text-xs text-slate-400 uppercase tracking-widest font-semibold flex gap-4">
            <span>Ollama: llama3.2</span>
            <span>Screen: 720p 10fps</span>
          </div>
          <button
            onClick={handleLogout}
            className="text-xs font-bold text-red-400 hover:text-red-300 transition-colors uppercase tracking-tighter bg-red-500/10 px-3 py-1.5 rounded-lg border border-red-500/20"
          >
            Logout
          </button>
        </div>
      </header>

      <div className="flex flex-1 gap-4 overflow-hidden">
        {/* Left Panel: Stream & Controls */}
        <div className="flex-[3] flex flex-col gap-4">
          <div className="flex-1 glass rounded-3xl overflow-hidden relative group">
            {screenSrc ? (
              <img
                src={screenSrc}
                alt="PC Screen"
                className="w-full h-full object-contain bg-black"
              />
            ) : (
              <div className="flex items-center justify-center h-full text-slate-500 flex-col gap-2">
                <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-primary" />
                Waiting for screen stream...
              </div>
            )}
            <div className="absolute top-4 left-4 glass px-3 py-1 rounded-full text-xs font-mono opacity-0 group-hover:opacity-100 transition-opacity">
              LIVE STREAM
            </div>

            {/* Approval Overlay */}
            {pendingAction && (
              <div className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-8 z-50">
                <div className="glass max-w-lg w-full p-6 rounded-3xl border-2 border-primary/30 shadow-2xl space-y-4">
                  <div className="flex items-center gap-2 text-primary">
                    <span className="text-lg">🛡️</span>
                    <h2 className="text-lg font-bold uppercase tracking-tight">Security Approval Required</h2>
                  </div>
                  <div className="bg-white/5 p-4 rounded-xl border border-white/10 space-y-3">
                    <div>
                      <span className="text-[10px] text-slate-500 font-bold uppercase block">AI Thought</span>
                      <p className="text-sm italic text-slate-300">"{pendingAction.action.thought}"</p>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 font-bold uppercase block">Proposed Command</span>
                      <code className="text-sm font-mono text-emerald-400 bg-black/40 px-2 py-1 rounded block mt-1">
                        {pendingAction.action.command}
                      </code>
                    </div>
                  </div>
                  <div className="flex gap-4">
                    <button
                      onClick={() => handleApproval(true)}
                      className="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-3 rounded-xl transition-all shadow-lg shadow-emerald-900/20"
                    >
                      APPROVE & EXECUTE
                    </button>
                    <button
                      onClick={() => handleApproval(false)}
                      className="flex-1 bg-slate-800 hover:bg-slate-700 text-white font-bold py-3 rounded-xl transition-all"
                    >
                      REJECT
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Prompt Area */}
          <div className="glass rounded-2xl p-4">
            <form onSubmit={handleSubmit} className="flex gap-4">
              <input
                type="text"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder={pendingAction ? "Awaiting approval..." : "Ask your PC to do something..."}
                className="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-3 outline-none focus:border-blue-500/50 transition-colors"
                disabled={isThinking || !!pendingAction}
              />
              <button
                type="submit"
                disabled={isThinking || !!pendingAction}
                className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-bold py-3 px-8 rounded-xl transition-all shadow-lg shadow-blue-900/20"
              >
                {isThinking ? 'THINKING...' : 'RUN'}
              </button>
            </form>
          </div>
        </div>

        {/* Right Panel: Logs */}
        <div className="flex-1 glass rounded-3xl flex flex-col overflow-hidden max-w-sm">
          <div className="p-4 border-b border-white/10 flex justify-between items-center bg-white/5">
            <h2 className="text-sm font-bold uppercase tracking-widest text-slate-400">Agent Logs</h2>
            <button
              onClick={() => setLogs([])}
              className="text-[10px] text-slate-500 hover:text-white transition-colors"
            >
              CLEAR
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-4 font-mono text-[10px] space-y-2 terminal-scroll">
            {logs.map((log, i) => (
              <div key={i} className={`p-2 rounded leading-relaxed ${log.startsWith('[Error]') ? 'bg-red-500/10 text-red-400 border border-red-500/20' :
                log.includes('AWAITING APPROVAL') ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                  log.startsWith('[System]') ? 'bg-slate-800 text-slate-300' :
                    'bg-blue-500/5 text-blue-300 border border-blue-500/10'
                }`}>
                {log}
              </div>
            ))}
            <div ref={logEndRef} />
          </div>
        </div>
      </div>
    </main>
  );
}
