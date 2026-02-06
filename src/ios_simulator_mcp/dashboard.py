"""Web dashboard for iOS Simulator MCP server."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import webbrowser
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from aiohttp import web, WSMsgType

logger = logging.getLogger(__name__)

# Dashboard configuration (can be overridden via environment variables)
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", "8200"))
DASHBOARD_AUTO_OPEN = os.environ.get("DASHBOARD_AUTO_OPEN", "true").lower() in ("true", "1", "yes")


@dataclass
class ToolCall:
    """Represents a single tool call."""

    id: int
    timestamp: float
    tool_name: str
    arguments: dict[str, Any]
    status: str = "pending"  # pending, success, error
    result: str | None = None
    error: str | None = None
    duration_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "time_str": datetime.fromtimestamp(self.timestamp).strftime("%H:%M:%S"),
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "status": self.status,
            "result": self.result[:500] if self.result and len(self.result) > 500 else self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


class DashboardState:
    """Holds the dashboard state."""

    def __init__(self, max_calls: int = 100):
        self.max_calls = max_calls
        self.tool_calls: list[ToolCall] = []
        self.call_counter = 0
        self.websockets: set[web.WebSocketResponse] = set()
        self.server_start_time = time.time()
        self.device_info: dict[str, Any] = {}
        self.wda_status: dict[str, Any] = {}
        self.last_screenshot: str | None = None
        self.recording_active: bool = False

    def add_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> ToolCall:
        """Add a new tool call and return it."""
        self.call_counter += 1
        call = ToolCall(
            id=self.call_counter,
            timestamp=time.time(),
            tool_name=tool_name,
            arguments=arguments,
        )
        self.tool_calls.append(call)

        # Trim old calls
        if len(self.tool_calls) > self.max_calls:
            self.tool_calls = self.tool_calls[-self.max_calls:]

        # Broadcast to websockets
        asyncio.create_task(self._broadcast({
            "type": "tool_call",
            "data": call.to_dict(),
        }))

        return call

    def complete_tool_call(self, call: ToolCall, result: str | None = None, error: str | None = None):
        """Mark a tool call as complete."""
        call.duration_ms = (time.time() - call.timestamp) * 1000
        if error:
            call.status = "error"
            call.error = error
        else:
            call.status = "success"
            call.result = result

        # Track screenshots
        if call.tool_name == "get_screenshot" and result:
            for line in result.split("\n"):
                if line.startswith("Screenshot saved:"):
                    self.last_screenshot = line.split(": ", 1)[1].strip()
                    break

        # Track recording
        if call.tool_name == "start_recording" and call.status == "success":
            self.recording_active = True
        elif call.tool_name == "stop_recording" and call.status == "success":
            self.recording_active = False

        # Broadcast update
        asyncio.create_task(self._broadcast({
            "type": "tool_complete",
            "data": call.to_dict(),
        }))

    def update_device_info(self, info: dict[str, Any]):
        """Update device info."""
        self.device_info = info
        asyncio.create_task(self._broadcast({
            "type": "device_info",
            "data": info,
        }))

    def update_wda_status(self, status: dict[str, Any]):
        """Update WDA status."""
        self.wda_status = status
        asyncio.create_task(self._broadcast({
            "type": "wda_status",
            "data": status,
        }))

    async def _broadcast(self, message: dict[str, Any]):
        """Broadcast message to all connected websockets."""
        if not self.websockets:
            return

        msg_str = json.dumps(message)
        dead_ws = set()

        for ws in self.websockets:
            try:
                await ws.send_str(msg_str)
            except Exception:
                dead_ws.add(ws)

        self.websockets -= dead_ws

    def get_state(self) -> dict[str, Any]:
        """Get current state for initial load."""
        return {
            "uptime": time.time() - self.server_start_time,
            "tool_calls": [c.to_dict() for c in self.tool_calls[-50:]],
            "device_info": self.device_info,
            "wda_status": self.wda_status,
            "last_screenshot": self.last_screenshot,
            "recording_active": self.recording_active,
            "total_calls": self.call_counter,
        }


# Global dashboard state
dashboard_state = DashboardState()


# HTML Dashboard Template
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>iOS Simulator MCP</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-tertiary: #1a1a24;
            --bg-card: rgba(255, 255, 255, 0.03);
            --bg-card-hover: rgba(255, 255, 255, 0.05);
            --border-color: rgba(255, 255, 255, 0.06);
            --text-primary: #ffffff;
            --text-secondary: #a1a1aa;
            --text-muted: #52525b;
            --accent-primary: #6366f1;
            --accent-secondary: #8b5cf6;
            --accent-gradient: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a855f7 100%);
            --success: #22c55e;
            --error: #ef4444;
            --warning: #f59e0b;
            --radius-sm: 8px;
            --radius-md: 12px;
            --radius-lg: 16px;
            --radius-xl: 24px;
            --shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.3);
            --shadow-md: 0 4px 20px rgba(0, 0, 0, 0.4);
            --shadow-lg: 0 8px 40px rgba(0, 0, 0, 0.5);
            --shadow-glow: 0 0 40px rgba(99, 102, 241, 0.15);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            overflow-x: hidden;
        }

        /* Animated background */
        .bg-gradient {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: 100vh;
            background:
                radial-gradient(ellipse 80% 50% at 50% -20%, rgba(99, 102, 241, 0.15), transparent),
                radial-gradient(ellipse 60% 40% at 100% 0%, rgba(139, 92, 246, 0.1), transparent),
                radial-gradient(ellipse 60% 40% at 0% 100%, rgba(168, 85, 247, 0.08), transparent);
            pointer-events: none;
            z-index: 0;
        }

        .app {
            position: relative;
            z-index: 1;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }

        /* Header */
        .header {
            padding: 16px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            backdrop-filter: blur(20px);
            background: rgba(10, 10, 15, 0.8);
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .logo-icon {
            width: 36px;
            height: 36px;
            background: var(--accent-gradient);
            border-radius: var(--radius-sm);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            box-shadow: var(--shadow-glow);
        }

        .logo-text {
            font-size: 1.1rem;
            font-weight: 600;
            letter-spacing: -0.02em;
        }

        .logo-text span {
            color: var(--text-secondary);
            font-weight: 400;
        }

        .status-pill {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 100px;
            font-size: 0.85rem;
            font-weight: 500;
            transition: all 0.3s ease;
        }

        .status-pill.connected {
            border-color: rgba(34, 197, 94, 0.3);
            background: rgba(34, 197, 94, 0.1);
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--success);
            box-shadow: 0 0 12px var(--success);
            animation: pulse 2s ease-in-out infinite;
        }

        .status-pill.disconnected .status-dot {
            background: var(--error);
            box-shadow: 0 0 12px var(--error);
            animation: none;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.6; transform: scale(0.9); }
        }

        /* Main Layout */
        .main {
            flex: 1;
            display: grid;
            grid-template-columns: 1fr 380px;
            gap: 24px;
            padding: 24px;
            max-width: 1800px;
            margin: 0 auto;
            width: 100%;
        }

        @media (max-width: 1200px) {
            .main {
                grid-template-columns: 1fr;
            }
            .sidebar {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
            }
        }

        /* Cards */
        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            backdrop-filter: blur(10px);
            overflow: hidden;
            transition: all 0.3s ease;
        }

        .card:hover {
            border-color: rgba(255, 255, 255, 0.1);
            box-shadow: var(--shadow-md);
        }

        .card-header {
            padding: 16px 20px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .card-title {
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--text-secondary);
        }

        .card-body {
            padding: 20px;
        }

        /* Tool Calls */
        .tool-calls-card {
            display: flex;
            flex-direction: column;
            max-height: calc(100vh - 140px);
        }

        .tool-calls-list {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
        }

        .tool-call {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
            padding: 16px;
            margin-bottom: 12px;
            transition: all 0.2s ease;
            animation: slideIn 0.3s ease;
        }

        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(-10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .tool-call:hover {
            background: var(--bg-tertiary);
            border-color: rgba(255, 255, 255, 0.1);
            transform: translateX(4px);
        }

        .tool-call-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 12px;
        }

        .tool-name-wrapper {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .tool-status-indicator {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--accent-primary);
        }

        .tool-call.success .tool-status-indicator { background: var(--success); }
        .tool-call.error .tool-status-indicator { background: var(--error); }
        .tool-call.pending .tool-status-indicator { background: var(--warning); animation: pulse 1s infinite; }

        .tool-name {
            font-weight: 600;
            font-size: 0.95rem;
            color: var(--text-primary);
        }

        .tool-meta {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .tool-time {
            font-size: 0.8rem;
            color: var(--text-muted);
            font-variant-numeric: tabular-nums;
        }

        .tool-duration {
            font-size: 0.75rem;
            color: var(--text-secondary);
            background: var(--bg-card);
            padding: 2px 8px;
            border-radius: 100px;
            font-weight: 500;
        }

        .tool-args {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            color: var(--text-secondary);
            background: rgba(0, 0, 0, 0.3);
            padding: 10px 12px;
            border-radius: var(--radius-sm);
            overflow-x: auto;
            white-space: pre-wrap;
            word-break: break-all;
            line-height: 1.5;
        }

        .tool-result {
            margin-top: 12px;
            padding: 10px 12px;
            background: rgba(34, 197, 94, 0.1);
            border: 1px solid rgba(34, 197, 94, 0.2);
            border-radius: var(--radius-sm);
            font-size: 0.8rem;
            color: var(--success);
            font-family: 'JetBrains Mono', monospace;
            line-height: 1.5;
        }

        .tool-error {
            margin-top: 12px;
            padding: 10px 12px;
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.2);
            border-radius: var(--radius-sm);
            font-size: 0.8rem;
            color: var(--error);
        }

        .empty-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 60px 20px;
            color: var(--text-muted);
            text-align: center;
        }

        .empty-state-icon {
            font-size: 48px;
            margin-bottom: 16px;
            opacity: 0.5;
        }

        .empty-state-text {
            font-size: 0.9rem;
        }

        /* Sidebar */
        .sidebar {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        /* Stats Grid */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }

        .stat-card {
            background: var(--bg-secondary);
            border-radius: var(--radius-md);
            padding: 16px;
            text-align: center;
            transition: all 0.2s ease;
        }

        .stat-card:hover {
            background: var(--bg-tertiary);
            transform: translateY(-2px);
        }

        .stat-value {
            font-size: 1.75rem;
            font-weight: 700;
            background: var(--accent-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            line-height: 1.2;
        }

        .stat-label {
            font-size: 0.7rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-top: 4px;
        }

        /* Device Info */
        .device-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .device-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid var(--border-color);
        }

        .device-row:last-child {
            border-bottom: none;
        }

        .device-label {
            font-size: 0.85rem;
            color: var(--text-muted);
        }

        .device-value {
            font-size: 0.85rem;
            font-weight: 500;
            color: var(--text-primary);
        }

        .device-value.connected {
            color: var(--success);
        }

        /* Screenshot */
        .screenshot-container {
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }

        .phone-frame {
            position: relative;
            background: #1a1a1a;
            border-radius: 40px;
            padding: 12px;
            box-shadow:
                0 0 0 2px #333,
                0 0 0 4px #1a1a1a,
                var(--shadow-lg);
            max-width: 200px;
            width: 100%;
        }

        .phone-frame::before {
            content: '';
            position: absolute;
            top: 8px;
            left: 50%;
            transform: translateX(-50%);
            width: 60px;
            height: 24px;
            background: #0a0a0a;
            border-radius: 20px;
            z-index: 10;
        }

        .phone-screen {
            background: #000;
            border-radius: 28px;
            overflow: hidden;
            aspect-ratio: 9/19.5;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .phone-screen img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .no-screenshot {
            color: var(--text-muted);
            font-size: 0.75rem;
            text-align: center;
            padding: 20px;
        }

        .recording-badge {
            position: absolute;
            top: 40px;
            right: 16px;
            display: flex;
            align-items: center;
            gap: 6px;
            background: var(--error);
            color: white;
            padding: 4px 10px;
            border-radius: 100px;
            font-size: 0.65rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            z-index: 20;
            animation: recPulse 1.5s ease-in-out infinite;
        }

        .recording-badge::before {
            content: '';
            width: 6px;
            height: 6px;
            background: white;
            border-radius: 50%;
        }

        @keyframes recPulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }

        /* Scrollbar */
        ::-webkit-scrollbar {
            width: 6px;
        }

        ::-webkit-scrollbar-track {
            background: transparent;
        }

        ::-webkit-scrollbar-thumb {
            background: var(--bg-tertiary);
            border-radius: 3px;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.15);
        }

        /* Responsive */
        @media (max-width: 768px) {
            .header {
                padding: 12px 16px;
            }

            .main {
                padding: 16px;
            }

            .phone-frame {
                max-width: 160px;
            }
        }
    </style>
</head>
<body>
    <div class="bg-gradient"></div>

    <div class="app">
        <header class="header">
            <div class="logo">
                <div class="logo-icon">📱</div>
                <div class="logo-text">iOS Simulator <span>MCP</span></div>
            </div>
            <div class="status-pill" id="statusPill">
                <div class="status-dot"></div>
                <span id="connectionText">Connecting...</span>
            </div>
        </header>

        <main class="main">
            <div class="card tool-calls-card">
                <div class="card-header">
                    <span class="card-title">Tool Calls</span>
                    <span class="card-title" id="callCount">0 calls</span>
                </div>
                <div class="tool-calls-list" id="toolCalls">
                    <div class="empty-state">
                        <div class="empty-state-icon">⚡</div>
                        <div class="empty-state-text">Waiting for tool calls...</div>
                    </div>
                </div>
            </div>

            <div class="sidebar">
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">Statistics</span>
                    </div>
                    <div class="card-body">
                        <div class="stats-grid">
                            <div class="stat-card">
                                <div class="stat-value" id="totalCalls">0</div>
                                <div class="stat-label">Total Calls</div>
                            </div>
                            <div class="stat-card">
                                <div class="stat-value" id="uptime">0s</div>
                                <div class="stat-label">Uptime</div>
                            </div>
                            <div class="stat-card">
                                <div class="stat-value" id="successRate">—</div>
                                <div class="stat-label">Success Rate</div>
                            </div>
                            <div class="stat-card">
                                <div class="stat-value" id="avgDuration">—</div>
                                <div class="stat-label">Avg Time</div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <span class="card-title">Device</span>
                    </div>
                    <div class="card-body">
                        <div class="device-list" id="deviceInfo">
                            <div style="color: var(--text-muted); text-align: center; padding: 20px; font-size: 0.85rem;">
                                No device connected
                            </div>
                        </div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <span class="card-title">Live Preview</span>
                    </div>
                    <div class="screenshot-container" id="screenshotContainer">
                        <div class="phone-frame">
                            <span id="recordingBadge" class="recording-badge" style="display: none;">REC</span>
                            <div class="phone-screen" id="phoneScreen">
                                <div class="no-screenshot">No screenshot yet</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </main>
    </div>

    <script>
        let ws;
        let toolCalls = [];
        let reconnectAttempts = 0;
        let uptimeSeconds = 0;

        function connect() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

            ws.onopen = () => {
                document.getElementById('statusPill').classList.add('connected');
                document.getElementById('statusPill').classList.remove('disconnected');
                document.getElementById('connectionText').textContent = 'Connected';
                reconnectAttempts = 0;
            };

            ws.onclose = () => {
                document.getElementById('statusPill').classList.add('disconnected');
                document.getElementById('statusPill').classList.remove('connected');
                document.getElementById('connectionText').textContent = 'Reconnecting...';
                setTimeout(connect, Math.min(1000 * Math.pow(2, reconnectAttempts++), 30000));
            };

            ws.onmessage = (event) => {
                const msg = JSON.parse(event.data);
                handleMessage(msg);
            };
        }

        function handleMessage(msg) {
            switch (msg.type) {
                case 'init':
                    toolCalls = (msg.data.tool_calls || []).reverse();
                    uptimeSeconds = msg.data.uptime || 0;
                    renderToolCalls();
                    updateStats(msg.data);
                    updateDeviceInfo(msg.data.device_info);
                    updateScreenshot(msg.data.last_screenshot);
                    updateRecording(msg.data.recording_active);
                    break;
                case 'tool_call':
                    toolCalls.unshift(msg.data);
                    if (toolCalls.length > 100) toolCalls.pop();
                    renderToolCalls();
                    updateCallCount();
                    break;
                case 'tool_complete':
                    const idx = toolCalls.findIndex(c => c.id === msg.data.id);
                    if (idx >= 0) toolCalls[idx] = msg.data;
                    renderToolCalls();
                    updateStatsFromCalls();
                    if (msg.data.tool_name === 'get_screenshot' && msg.data.status === 'success') {
                        setTimeout(() => updateScreenshot(true), 500);
                    }
                    break;
                case 'device_info':
                    updateDeviceInfo(msg.data);
                    break;
            }
        }

        function renderToolCalls() {
            const container = document.getElementById('toolCalls');
            updateCallCount();

            if (toolCalls.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">⚡</div>
                        <div class="empty-state-text">Waiting for tool calls...</div>
                    </div>
                `;
                return;
            }

            container.innerHTML = toolCalls.map(call => `
                <div class="tool-call ${call.status}">
                    <div class="tool-call-header">
                        <div class="tool-name-wrapper">
                            <div class="tool-status-indicator"></div>
                            <span class="tool-name">${call.tool_name}</span>
                        </div>
                        <div class="tool-meta">
                            ${call.duration_ms ? `<span class="tool-duration">${call.duration_ms.toFixed(0)}ms</span>` : ''}
                            <span class="tool-time">${call.time_str}</span>
                        </div>
                    </div>
                    <div class="tool-args">${formatArgs(call.arguments)}</div>
                    ${call.result ? `<div class="tool-result">${escapeHtml(call.result)}</div>` : ''}
                    ${call.error ? `<div class="tool-error">${escapeHtml(call.error)}</div>` : ''}
                </div>
            `).join('');
        }

        function formatArgs(args) {
            if (!args || Object.keys(args).length === 0) return '(no arguments)';
            return Object.entries(args)
                .map(([k, v]) => {
                    const val = typeof v === 'object' ? JSON.stringify(v) : v;
                    const shortVal = String(val).length > 50 ? String(val).slice(0, 47) + '...' : val;
                    return `${k}: ${shortVal}`;
                })
                .join('\\n');
        }

        function escapeHtml(str) {
            if (!str) return '';
            return str.replace(/&/g, '&amp;')
                      .replace(/</g, '&lt;')
                      .replace(/>/g, '&gt;')
                      .replace(/\\n/g, '<br>');
        }

        function updateCallCount() {
            document.getElementById('callCount').textContent = `${toolCalls.length} call${toolCalls.length !== 1 ? 's' : ''}`;
        }

        function updateStats(data) {
            document.getElementById('totalCalls').textContent = data.total_calls || 0;
            updateStatsFromCalls();
        }

        function updateStatsFromCalls() {
            const completed = toolCalls.filter(c => c.status !== 'pending');
            const success = completed.filter(c => c.status === 'success');

            document.getElementById('totalCalls').textContent = toolCalls.length;

            if (completed.length > 0) {
                const rate = (success.length / completed.length * 100).toFixed(0);
                document.getElementById('successRate').textContent = `${rate}%`;

                const durations = completed.filter(c => c.duration_ms).map(c => c.duration_ms);
                if (durations.length > 0) {
                    const avg = durations.reduce((a, b) => a + b, 0) / durations.length;
                    document.getElementById('avgDuration').textContent = avg < 1000 ? `${avg.toFixed(0)}ms` : `${(avg/1000).toFixed(1)}s`;
                }
            }
        }

        function formatUptime(seconds) {
            if (seconds < 60) return `${Math.floor(seconds)}s`;
            if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            return `${h}h ${m}m`;
        }

        function updateDeviceInfo(info) {
            const container = document.getElementById('deviceInfo');
            if (!info || Object.keys(info).length === 0) {
                container.innerHTML = `
                    <div style="color: var(--text-muted); text-align: center; padding: 20px; font-size: 0.85rem;">
                        No device connected
                    </div>
                `;
                return;
            }

            container.innerHTML = `
                <div class="device-row">
                    <span class="device-label">Name</span>
                    <span class="device-value">${info.name || '—'}</span>
                </div>
                <div class="device-row">
                    <span class="device-label">iOS Version</span>
                    <span class="device-value">${info.ios_version || '—'}</span>
                </div>
                <div class="device-row">
                    <span class="device-label">UDID</span>
                    <span class="device-value" title="${info.udid || ''}">${(info.udid || '—').slice(0, 12)}...</span>
                </div>
                <div class="device-row">
                    <span class="device-label">WDA Status</span>
                    <span class="device-value ${info.wda_connected ? 'connected' : ''}">${info.wda_connected ? '● Connected' : '○ Disconnected'}</span>
                </div>
            `;
        }

        function updateScreenshot(pathOrRefresh) {
            const phoneScreen = document.getElementById('phoneScreen');
            const timestamp = Date.now();
            phoneScreen.innerHTML = `<img src="/screenshot?t=${timestamp}" alt="Screenshot" onerror="this.parentElement.innerHTML='<div class=\\'no-screenshot\\'>No screenshot yet</div>'">`;
        }

        function updateRecording(active) {
            document.getElementById('recordingBadge').style.display = active ? 'flex' : 'none';
        }

        // Update uptime every second
        setInterval(() => {
            uptimeSeconds++;
            document.getElementById('uptime').textContent = formatUptime(uptimeSeconds);
        }, 1000);

        // Connect on load
        connect();
    </script>
</body>
</html>
"""


async def handle_index(request: web.Request) -> web.Response:
    """Serve the dashboard HTML."""
    return web.Response(text=DASHBOARD_HTML, content_type="text/html")


async def handle_api_state(request: web.Request) -> web.Response:
    """Return current dashboard state as JSON."""
    return web.json_response(dashboard_state.get_state())


async def handle_screenshot(request: web.Request) -> web.Response:
    """Serve the last screenshot."""
    if not dashboard_state.last_screenshot:
        return web.Response(status=404, text="No screenshot available")

    path = Path(dashboard_state.last_screenshot)
    if not path.exists():
        return web.Response(status=404, text="Screenshot file not found")

    content_type = "image/jpeg" if path.suffix.lower() in [".jpg", ".jpeg"] else "image/png"
    return web.Response(body=path.read_bytes(), content_type=content_type)


async def handle_websocket(request: web.Request) -> web.WebSocketResponse:
    """Handle WebSocket connections."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    dashboard_state.websockets.add(ws)
    logger.info(f"WebSocket client connected ({len(dashboard_state.websockets)} total)")

    # Send initial state
    await ws.send_json({
        "type": "init",
        "data": dashboard_state.get_state(),
    })

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                # Handle any client messages if needed
                pass
            elif msg.type == WSMsgType.ERROR:
                logger.error(f"WebSocket error: {ws.exception()}")
    finally:
        dashboard_state.websockets.discard(ws)
        logger.info(f"WebSocket client disconnected ({len(dashboard_state.websockets)} remaining)")

    return ws


def create_dashboard_app() -> web.Application:
    """Create the dashboard web application."""
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/state", handle_api_state)
    app.router.add_get("/screenshot", handle_screenshot)
    app.router.add_get("/ws", handle_websocket)
    return app


async def start_dashboard(port: int = DASHBOARD_PORT, auto_open: bool = DASHBOARD_AUTO_OPEN) -> web.AppRunner:
    """Start the dashboard server.

    Args:
        port: Port to run dashboard on
        auto_open: Whether to automatically open browser (default: True, set DASHBOARD_AUTO_OPEN=false to disable)
    """
    app = create_dashboard_app()
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    url = f"http://localhost:{port}"
    logger.info(f"Dashboard started at {url}")
    print(f"\n{'='*50}", flush=True)
    print(f"  Dashboard: {url}", flush=True)
    print(f"{'='*50}\n", flush=True)

    # Auto-open browser
    if auto_open:
        try:
            webbrowser.open(url)
            logger.info("Opened dashboard in browser")
        except Exception as e:
            logger.warning(f"Could not open browser: {e}")

    return runner


async def stop_dashboard(runner: web.AppRunner) -> None:
    """Stop the dashboard server."""
    await runner.cleanup()
    logger.info("Dashboard stopped")
