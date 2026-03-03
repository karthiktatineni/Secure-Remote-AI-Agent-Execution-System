"use client";

import { useState } from 'react';
import { useRouter } from 'next/navigation';

export default function Login() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [isLoggingIn, setIsLoggingIn] = useState(false);
    const router = useRouter();

    const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'https://back.tatinenikarthik.online';

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoggingIn(true);
        setError('');

        try {
            const res = await fetch(`${API_BASE}/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });

            if (res.ok) {
                const data = await res.json();
                // Store token in session or local storage
                localStorage.setItem('agent_token', data.token);
                router.push('/');
            } else {
                setError('Invalid username or password');
            }
        } catch (err) {
            setError('Connection failed. Backend might be offline.');
        } finally {
            setIsLoggingIn(false);
        }
    };

    return (
        <main className="min-h-screen flex items-center justify-center bg-slate-950 text-slate-100 p-4">
            <div className="w-full max-w-md space-y-8 glass p-10 rounded-[2.5rem] border border-white/10 shadow-2xl relative overflow-hidden">
                {/* Glow Effects */}
                <div className="absolute -top-24 -left-24 w-48 h-48 bg-blue-600/20 blur-[100px] rounded-full" />
                <div className="absolute -bottom-24 -right-24 w-48 h-48 bg-emerald-600/20 blur-[100px] rounded-full" />

                <div className="text-center space-y-2 relative z-10">
                    <h1 className="text-3xl font-black bg-gradient-to-r from-blue-400 to-emerald-400 bg-clip-text text-transparent">
                        SECURE ACCESS
                    </h1>
                    <p className="text-slate-400 text-sm font-medium tracking-wide uppercase">Antigravity PC Agent</p>
                </div>

                <form onSubmit={handleLogin} className="space-y-6 relative z-10">
                    {error && (
                        <div className="bg-red-500/10 border border-red-500/20 text-red-400 px-4 py-3 rounded-xl text-sm text-center">
                            {error}
                        </div>
                    )}

                    <div className="space-y-1">
                        <label className="text-[10px] font-bold text-slate-500 uppercase ml-2">Username</label>
                        <input
                            type="text"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            className="w-full bg-white/5 border border-white/10 rounded-2xl px-5 py-3.5 focus:border-blue-500/50 outline-none transition-all placeholder:text-slate-700"
                            placeholder="Enter username"
                            required
                        />
                    </div>

                    <div className="space-y-1">
                        <label className="text-[10px] font-bold text-slate-500 uppercase ml-2">Password</label>
                        <input
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            className="w-full bg-white/5 border border-white/10 rounded-2xl px-5 py-3.5 focus:border-blue-500/50 outline-none transition-all placeholder:text-slate-700"
                            placeholder="••••••••"
                            required
                        />
                    </div>

                    <button
                        type="submit"
                        disabled={isLoggingIn}
                        className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-4 rounded-2xl transition-all shadow-lg shadow-blue-900/30 transform active:scale-[0.98] disabled:opacity-50"
                    >
                        {isLoggingIn ? 'AUTHENTICATING...' : 'ACCESS AGENT'}
                    </button>
                </form>

                <div className="text-center pt-4 relative z-10">
                    <span className="text-xs text-slate-500 font-mono">ENCRYPTED TUNNEL: ACTIVE</span>
                </div>
            </div>
        </main>
    );
}
