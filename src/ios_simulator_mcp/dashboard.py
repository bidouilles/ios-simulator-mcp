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
    <title>iOS Simulator MCP Dashboard</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
        }

        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
        }

        .header h1 {
            font-size: 1.5rem;
            font-weight: 600;
        }

        .status-badge {
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(255,255,255,0.1);
            padding: 8px 16px;
            border-radius: 20px;
        }

        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #4ade80;
            animation: pulse 2s infinite;
        }

        .status-dot.disconnected { background: #ef4444; animation: none; }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .container {
            display: grid;
            grid-template-columns: 1fr 350px;
            gap: 20px;
            padding: 20px;
            max-width: 1600px;
            margin: 0 auto;
        }

        .panel {
            background: #16213e;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        }

        .panel h2 {
            font-size: 1rem;
            color: #888;
            margin-bottom: 15px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .tool-calls {
            max-height: 70vh;
            overflow-y: auto;
        }

        .tool-call {
            background: #1a1a2e;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 10px;
            border-left: 3px solid #667eea;
            transition: transform 0.2s;
        }

        .tool-call:hover { transform: translateX(5px); }
        .tool-call.success { border-left-color: #4ade80; }
        .tool-call.error { border-left-color: #ef4444; }
        .tool-call.pending { border-left-color: #fbbf24; }

        .tool-call-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }

        .tool-name {
            font-weight: 600;
            color: #fff;
        }

        .tool-time {
            font-size: 0.8rem;
            color: #666;
        }

        .tool-args {
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 0.75rem;
            color: #888;
            background: rgba(0,0,0,0.2);
            padding: 8px;
            border-radius: 4px;
            overflow-x: auto;
            white-space: pre-wrap;
            word-break: break-all;
        }

        .tool-result {
            margin-top: 8px;
            font-size: 0.8rem;
            color: #4ade80;
        }

        .tool-error {
            margin-top: 8px;
            font-size: 0.8rem;
            color: #ef4444;
        }

        .tool-duration {
            font-size: 0.75rem;
            color: #666;
            margin-top: 4px;
        }

        .sidebar { display: flex; flex-direction: column; gap: 20px; }

        .stat-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
        }

        .stat {
            background: #1a1a2e;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }

        .stat-value {
            font-size: 1.5rem;
            font-weight: 700;
            color: #667eea;
        }

        .stat-label {
            font-size: 0.75rem;
            color: #666;
            margin-top: 4px;
        }

        .device-info {
            font-size: 0.85rem;
        }

        .device-info div {
            padding: 8px 0;
            border-bottom: 1px solid #1a1a2e;
            display: flex;
            justify-content: space-between;
        }

        .device-info .label { color: #666; }
        .device-info .value { color: #fff; font-weight: 500; }

        .screenshot-preview {
            text-align: center;
        }

        .screenshot-preview img {
            max-width: 100%;
            max-height: 300px;
            border-radius: 8px;
            border: 2px solid #333;
        }

        .screenshot-preview .no-screenshot {
            color: #666;
            padding: 40px;
            background: #1a1a2e;
            border-radius: 8px;
        }

        .recording-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #ef4444;
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 600;
        }

        .recording-badge::before {
            content: '';
            width: 8px;
            height: 8px;
            background: white;
            border-radius: 50%;
            animation: blink 1s infinite;
        }

        @keyframes blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }

        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #1a1a2e; }
        ::-webkit-scrollbar-thumb { background: #333; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #444; }
    </style>
</head>
<body>
    <div class="header">
        <h1>iOS Simulator MCP Dashboard</h1>
        <div class="status-badge">
            <div class="status-dot" id="connectionStatus"></div>
            <span id="connectionText">Connecting...</span>
        </div>
    </div>

    <div class="container">
        <div class="panel">
            <h2>Tool Calls</h2>
            <div class="tool-calls" id="toolCalls">
                <div style="color: #666; text-align: center; padding: 40px;">
                    Waiting for tool calls...
                </div>
            </div>
        </div>

        <div class="sidebar">
            <div class="panel">
                <h2>Statistics</h2>
                <div class="stat-grid">
                    <div class="stat">
                        <div class="stat-value" id="totalCalls">0</div>
                        <div class="stat-label">Total Calls</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="uptime">0s</div>
                        <div class="stat-label">Uptime</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="successRate">-</div>
                        <div class="stat-label">Success Rate</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="avgDuration">-</div>
                        <div class="stat-label">Avg Duration</div>
                    </div>
                </div>
            </div>

            <div class="panel">
                <h2>Device Info</h2>
                <div class="device-info" id="deviceInfo">
                    <div style="color: #666; text-align: center;">No device connected</div>
                </div>
            </div>

            <div class="panel">
                <h2>
                    Last Screenshot
                    <span id="recordingBadge" class="recording-badge" style="display: none; margin-left: 10px;">REC</span>
                </h2>
                <div class="screenshot-preview" id="screenshotPreview">
                    <div class="no-screenshot">No screenshot yet</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let ws;
        let toolCalls = [];
        let reconnectAttempts = 0;

        function connect() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

            ws.onopen = () => {
                document.getElementById('connectionStatus').classList.remove('disconnected');
                document.getElementById('connectionText').textContent = 'Connected';
                reconnectAttempts = 0;
            };

            ws.onclose = () => {
                document.getElementById('connectionStatus').classList.add('disconnected');
                document.getElementById('connectionText').textContent = 'Disconnected';
                // Reconnect with exponential backoff
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
                    toolCalls = msg.data.tool_calls || [];
                    renderToolCalls();
                    updateStats(msg.data);
                    updateDeviceInfo(msg.data.device_info);
                    updateScreenshot(msg.data.last_screenshot);
                    updateRecording(msg.data.recording_active);
                    break;
                case 'tool_call':
                    toolCalls.unshift(msg.data);
                    if (toolCalls.length > 50) toolCalls.pop();
                    renderToolCalls();
                    break;
                case 'tool_complete':
                    const idx = toolCalls.findIndex(c => c.id === msg.data.id);
                    if (idx >= 0) toolCalls[idx] = msg.data;
                    renderToolCalls();
                    updateStatsFromCalls();
                    break;
                case 'device_info':
                    updateDeviceInfo(msg.data);
                    break;
            }
        }

        function renderToolCalls() {
            const container = document.getElementById('toolCalls');
            if (toolCalls.length === 0) {
                container.innerHTML = '<div style="color: #666; text-align: center; padding: 40px;">Waiting for tool calls...</div>';
                return;
            }

            container.innerHTML = toolCalls.map(call => `
                <div class="tool-call ${call.status}">
                    <div class="tool-call-header">
                        <span class="tool-name">${call.tool_name}</span>
                        <span class="tool-time">${call.time_str}</span>
                    </div>
                    <div class="tool-args">${formatArgs(call.arguments)}</div>
                    ${call.result ? `<div class="tool-result">${escapeHtml(call.result)}</div>` : ''}
                    ${call.error ? `<div class="tool-error">${escapeHtml(call.error)}</div>` : ''}
                    ${call.duration_ms ? `<div class="tool-duration">${call.duration_ms.toFixed(0)}ms</div>` : ''}
                </div>
            `).join('');
        }

        function formatArgs(args) {
            if (!args || Object.keys(args).length === 0) return '(no arguments)';
            return Object.entries(args)
                .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`)
                .join(', ');
        }

        function escapeHtml(str) {
            if (!str) return '';
            return str.replace(/&/g, '&amp;')
                      .replace(/</g, '&lt;')
                      .replace(/>/g, '&gt;')
                      .replace(/\\n/g, '<br>');
        }

        function updateStats(data) {
            document.getElementById('totalCalls').textContent = data.total_calls || 0;
            document.getElementById('uptime').textContent = formatUptime(data.uptime || 0);
            updateStatsFromCalls();
        }

        function updateStatsFromCalls() {
            const completed = toolCalls.filter(c => c.status !== 'pending');
            const success = completed.filter(c => c.status === 'success');

            if (completed.length > 0) {
                const rate = (success.length / completed.length * 100).toFixed(0);
                document.getElementById('successRate').textContent = `${rate}%`;

                const durations = completed.filter(c => c.duration_ms).map(c => c.duration_ms);
                if (durations.length > 0) {
                    const avg = durations.reduce((a, b) => a + b, 0) / durations.length;
                    document.getElementById('avgDuration').textContent = `${avg.toFixed(0)}ms`;
                }
            }

            document.getElementById('totalCalls').textContent = toolCalls.length;
        }

        function formatUptime(seconds) {
            if (seconds < 60) return `${Math.floor(seconds)}s`;
            if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
            return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
        }

        function updateDeviceInfo(info) {
            const container = document.getElementById('deviceInfo');
            if (!info || Object.keys(info).length === 0) {
                container.innerHTML = '<div style="color: #666; text-align: center;">No device connected</div>';
                return;
            }

            container.innerHTML = `
                <div><span class="label">Name</span><span class="value">${info.name || '-'}</span></div>
                <div><span class="label">UDID</span><span class="value">${(info.udid || '-').slice(0, 8)}...</span></div>
                <div><span class="label">iOS</span><span class="value">${info.ios_version || '-'}</span></div>
                <div><span class="label">State</span><span class="value">${info.state || '-'}</span></div>
                <div><span class="label">WDA</span><span class="value">${info.wda_connected ? 'Connected' : 'Disconnected'}</span></div>
            `;
        }

        function updateScreenshot(path) {
            const container = document.getElementById('screenshotPreview');
            if (!path) {
                container.innerHTML = '<div class="no-screenshot">No screenshot yet</div>';
                return;
            }
            // Add timestamp to prevent caching
            container.innerHTML = `<img src="/screenshot?t=${Date.now()}" alt="Last screenshot" onerror="this.parentElement.innerHTML='<div class=\\'no-screenshot\\'>Failed to load</div>'">`;
        }

        function updateRecording(active) {
            document.getElementById('recordingBadge').style.display = active ? 'inline-flex' : 'none';
        }

        // Update uptime every second
        setInterval(() => {
            const el = document.getElementById('uptime');
            const current = parseFloat(el.dataset.seconds || 0) + 1;
            el.dataset.seconds = current;
            el.textContent = formatUptime(current);
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
