# Troubleshooting

## Cannot connect to WebDriverAgent

1. Start WDA: `./scripts/start_wda.sh <UDID>`
2. Check WDA output for actual host/port
3. Set `WDA_HOST` when WDA is not on `127.0.0.1`

## WDA unknown error or taps not working

1. Reset session: `reset_session device_id="..."`
2. Restart WDA
3. Verify tap coordinates are in bounds

## Screenshots missing

Screenshots are saved under `/tmp/ios-simulator-mcp/screenshots/`.
Use the returned file path from `get_screenshot`.

## UI tree is empty

1. Ensure WDA session exists with `start_bridge`
2. Wait for target app to fully load
3. System dialogs can expose limited accessibility content

## Session expires

Call `reset_session` to create a fresh WDA session.
