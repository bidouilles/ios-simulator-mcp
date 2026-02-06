# ios-simulator-mcp

MCP server for iOS Simulator automation via WebDriverAgent. Control simulators from Claude, Cursor, and other AI assistants. Tap, type, swipe, screenshot, launch apps, and more.

## Quick Start (3 Steps)

### 1. Install (one-time)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

### 2. Start WebDriverAgent on Simulator

```bash
# Start WDA (will show device list if no UDID provided)
./scripts/start_wda.sh

# Or with specific UDID
./scripts/start_wda.sh <UDID>
```

Note the WDA URL in output: `ServerURLHere->http://192.168.1.30:8100<-ServerURLHere`

### 3. Add to Claude Code

```bash
claude mcp add ios-simulator -- /path/to/ios-simulator-mcp/venv/bin/ios-simulator-mcp
```

Or with WDA_HOST (if not localhost):
```bash
claude mcp add ios-simulator -e WDA_HOST=192.168.1.30 -- /path/to/ios-simulator-mcp/venv/bin/ios-simulator-mcp
```

**That's it!** Now ask Claude to interact with your simulator.

---

## Features

- **Simulator Management**: List, boot, and shutdown iOS simulators via `xcrun simctl`
- **UI Automation**: Tap, type, swipe, and interact with apps via WebDriverAgent
- **Screenshot Capture**: Optimized screenshots (90% smaller with auto-compression)
- **App Control**: Launch, terminate, and list installed apps
- **Alert Handling**: Accept, dismiss, and read alert dialogs
- **System Control**: Set location, manage clipboard, press hardware buttons

## Prerequisites

- **macOS** with Xcode installed
- **Xcode Command Line Tools**: `xcode-select --install`
- **Python 3.10+**
- **WebDriverAgent** (included in `../WebDriverAgent`)

## Detailed Setup

### Starting WebDriverAgent

WDA must be running for UI automation:

```bash
# Option A: By simulator name
cd ../WebDriverAgent
xcodebuild -project WebDriverAgent.xcodeproj \
  -scheme WebDriverAgentRunner \
  -destination 'platform=iOS Simulator,name=iPhone 16 Pro' \
  test

# Option B: By UDID
xcodebuild -project WebDriverAgent.xcodeproj \
  -scheme WebDriverAgentRunner \
  -destination 'platform=iOS Simulator,id=D8D53F70-4AB1-4B44-8602-82ED2AF4F2A9' \
  test

# Option C: Helper script
WDA_PATH=../WebDriverAgent ./scripts/start_wda.sh <UDID>
```

### Finding Simulator UDID

```bash
xcrun simctl list devices | grep Booted
```

### WDA Host Configuration

WDA typically binds to your machine's IP (not localhost). Check the WDA output for the actual URL and set `WDA_HOST` accordingly.

## MCP Client Configuration

### Claude Code (CLI)

```bash
# Add MCP server
claude mcp add ios-simulator -- /path/to/ios-simulator-mcp/venv/bin/ios-simulator-mcp

# With WDA_HOST environment variable
claude mcp add ios-simulator -e WDA_HOST=192.168.1.30 -- /path/to/ios-simulator-mcp/venv/bin/ios-simulator-mcp

# Remove if needed
claude mcp remove ios-simulator
```

### Claude Code (Manual)

Add to `~/.claude/settings.json` or project `.claude/settings.json`:

```json
{
  "mcpServers": {
    "ios-simulator": {
      "command": "/path/to/ios-simulator-mcp/venv/bin/ios-simulator-mcp",
      "env": {
        "WDA_HOST": "192.168.1.30"
      }
    }
  }
}
```

### Cursor / Windsurf

```json
{
  "mcpServers": {
    "ios-simulator": {
      "command": "/path/to/ios-simulator-mcp/venv/bin/ios-simulator-mcp",
      "env": {
        "WDA_HOST": "192.168.1.30"
      }
    }
  }
}
```

## Available Tools

### Device Management

| Tool | Description |
|------|-------------|
| `list_devices` | List all iOS simulators (booted and available) |
| `get_device` | Get device info by UDID |
| `boot_simulator` | Boot a simulator |
| `shutdown_simulator` | Shutdown a simulator |
| `start_bridge` | Connect to WebDriverAgent and create session |
| `reset_session` | Reset WDA session (useful if errors occur) |

### UI Automation

| Tool | Description |
|------|-------------|
| `get_screenshot` | Capture screenshot with optimization (scale, format, quality) |
| `get_ui_tree` | Get accessibility tree with element indices |
| `tap` | Tap element by index, predicate, or coordinates |
| `type_text` | Type text (optionally tap element first via predicate) |
| `swipe` | Swipe gesture by direction or coordinates |
| `double_tap` | Double tap at coordinates |
| `long_press` | Long press at coordinates |

### Navigation & Apps

| Tool | Description |
|------|-------------|
| `go_home` | Navigate to home screen |
| `launch_app` | Launch app by bundle ID |
| `terminate_app` | Terminate app |
| `list_apps` | List installed apps |
| `open_url` | Open URL in Safari |
| `press_button` | Press hardware button (home, volumeUp, volumeDown) |

### System

| Tool | Description |
|------|-------------|
| `set_location` | Set GPS location |
| `get_clipboard` | Get clipboard content |
| `set_clipboard` | Set clipboard content |
| `get_window_size` | Get screen dimensions |

### Alerts

| Tool | Description |
|------|-------------|
| `accept_alert` | Accept alert dialog |
| `dismiss_alert` | Dismiss alert dialog |
| `get_alert_text` | Get alert text |

## Usage Examples

### Basic Workflow

```
1. list_devices (only_booted: true)     → Get booted simulator UDID
2. start_bridge (device_id: "...")       → Connect to WDA
3. get_ui_tree (device_id: "...")        → See UI elements
4. tap (device_id: "...", index: 5)      → Tap element [5]
```

### Tap by Different Methods

```
# By index (from get_ui_tree)
tap device_id="..." index=5

# By predicate
tap device_id="..." predicate={"text_contains": "Settings"}
tap device_id="..." predicate={"type": "Button", "text": "OK"}

# By coordinates
tap device_id="..." x=200 y=400
```

### Type Text

```
# Type into focused field
type_text device_id="..." text="Hello World"

# Tap field first, then type
type_text device_id="..." text="username" predicate={"type": "TextField"}
```

### Swipe/Scroll

```
# By direction
swipe device_id="..." direction="up"      # Scroll down
swipe device_id="..." direction="down"    # Scroll up

# By coordinates
swipe device_id="..." from_x=200 from_y=600 to_x=200 to_y=200
```

### Launch App

```
launch_app device_id="..." bundle_id="com.apple.Preferences"
```

### Screenshot (Optimized)

Screenshots are automatically optimized to reduce file size and context usage:

```
# Default (recommended) - JPEG at 50% scale, ~85-90% smaller
get_screenshot device_id="..."

# Full size JPEG (when you need full detail)
get_screenshot device_id="..." scale=1.0

# PNG format (lossless, for text recognition)
get_screenshot device_id="..." format="png" scale=0.5

# Tiny preview (quick checks)
get_screenshot device_id="..." scale=0.25 quality=70
```

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `scale` | 0.5 | Scale factor 0.1-1.0 (0.5 = half size) |
| `format` | jpeg | Image format: `jpeg` or `png` |
| `quality` | 85 | JPEG quality 1-100 (ignored for PNG) |

**Example output:**
```
Screenshot saved: /tmp/ios-simulator-mcp/screenshots/screenshot-20260206-100447.jpg
Original: 1170x2532 (618.7KB)
Optimized: 585x1266 (52.3KB)
Reduction: 91.5%
```

## Predicate Fields

When using predicates to find elements:

| Field | Description |
|-------|-------------|
| `text` | Exact text match |
| `text_contains` | Contains substring (case-insensitive) |
| `text_starts_with` | Starts with prefix |
| `type` | Element type (Button, TextField, Switch, etc.) |
| `label` | Accessibility label |
| `identifier` | Accessibility identifier |
| `index` | Select Nth match (0-based) |

## Common Bundle IDs

| App | Bundle ID |
|-----|-----------|
| Settings | `com.apple.Preferences` |
| Safari | `com.apple.mobilesafari` |
| Maps | `com.apple.Maps` |
| Photos | `com.apple.Photos` |
| Calendar | `com.apple.mobilecal` |
| Notes | `com.apple.mobilenotes` |
| Mail | `com.apple.mobilemail` |
| Messages | `com.apple.MobileSMS` |
| App Store | `com.apple.AppStore` |
| Calculator | `com.apple.calculator` |
| Camera | `com.apple.camera` |
| Clock | `com.apple.clock` |

## Troubleshooting

### "Cannot connect to WebDriverAgent"

1. Make sure WDA is running (`./scripts/start_wda.sh <UDID>`)
2. Check the WDA output for the actual host/port
3. Set `WDA_HOST` if not `127.0.0.1`

### "WDA error: Unknown error" or tap not working

1. Reset the session: `reset_session device_id="..."`
2. Restart WDA if needed
3. Check coordinates are within screen bounds

### Screenshots not appearing

Screenshots are saved to `/tmp/ios-simulator-mcp/screenshots/`. Use the file path returned by `get_screenshot`.

### UI tree is empty

1. Ensure WDA is connected (`start_bridge`)
2. Wait for app to fully load
3. Some system dialogs may not expose accessibility info

### Session expires

Use `reset_session` to create a fresh WDA session.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WDA_HOST` | `127.0.0.1` | WebDriverAgent host |
| `WDA_PORT` | `8100` | WebDriverAgent port (via start_bridge) |

## Project Structure

```
ios-simulator-mcp/
├── pyproject.toml                    # Package configuration
├── README.md                         # This file
├── CLAUDE.md                         # AI assistant context
├── scripts/
│   ├── setup.sh                      # Setup script
│   ├── run_server.sh                 # Run MCP server
│   ├── start_wda.sh                  # Start WebDriverAgent
│   └── test_install.py               # Test installation
└── src/ios_simulator_mcp/
    ├── __init__.py
    ├── server.py                     # MCP server & tools
    ├── simulator.py                  # simctl integration
    ├── wda_client.py                 # WebDriverAgent client
    └── ui_tree.py                    # UI hierarchy parsing
```

## License

Apache 2.0
