# Clipboard Share 🖥️

Cross-network clipboard sharing between two Windows laptops. Relays through a small public HTTP server deployed to Render.com (free tier). **No firewall setup, no public IP, no tunnels.**

## How it works

1. **Sender** presses **GENERATE CODE** → gets a 6-char code (e.g. `ABC123`)
2. **Receiver** enters that code → connects through the shared relay server
3. Copy/type anything on the sender → appears on the receiver instantly

Both apps talk to a single shared relay (`https://clipboard-relay-ra48.onrender.com`) via simple room-based HTTP endpoints. Works across any networks with internet on both sides.

## Public relay

The relay is a tiny REST server deployed to Render.com's free tier. It keeps short-lived rooms in memory:

- `POST /send/<ROOM>` — `{"text": "..."}` pushes text to a room
- `GET /receive/<ROOM>` — polls & returns the latest text (HTTP 404 if empty)
- `GET /health` — `{"status":"alive","rooms":N}`

Free Render instances spin down after ~15 min idle and wake on the next request (adds ~30s to the first call). Source: `relay_server.py` (deploy with `Dockerfile` + `render.yaml`).

## Files

| File | Purpose |
|------|---------|
| `clipboard_sender.py` | Sender app: generates code, monitors clipboard, sends text |
| `clipboard_receiver.py` | Receiver app: enters code, polls, displays received text |
| `relay_server.py` | The relay server (deploy this to Render.com) |
| `Dockerfile` | Container definition for Render.com |
| `render.yaml` | Render.com blueprint (web service) |
| `install_autostart.bat` | Adds receiver to Windows startup (stealth mode) |

## Build executables

```bash
# Sender
pip install pyinstaller pywin32 pillow random2
pyinstaller --onefile --windowed clipboard_sender.py

# Receiver (with stealth --silent support)
pip install keyboard
pyinstaller --onefile --windowed --hidden-import keyboard clipboard_receiver.py
```

## Run

```bash
python clipboard_sender.py
python clipboard_receiver.py
```

## Stealth mode

```bash
# Receiver runs hidden, press Ctrl+Shift+H to show
python clipboard_receiver.py --silent
```

Built as `RuntimeBroker.exe` it blends into Task Manager (legitimate Windows process).

## Requirements

- Python 3.8+ (Windows)
- `pillow`, `pywin32` (sender)
- `pillow`, `keyboard` (receiver)