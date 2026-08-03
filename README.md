# Clipboard Share 🖥️

Cross-network clipboard sharing between two Windows laptops. **No server to deploy** — it relays through JSONBlob.com's free cloud storage.

## How it works

1. **Sender** presses **GENERATE CODE** → gets a 6-char code (e.g. `ABC123`)
2. **Receiver** enters that code → auto-connects through a shared directory
3. Copy/type anything on the sender → appears on the receiver instantly

Both apps work across any networks — no firewall configuration, no public IP, no SSH tunnel required. Just internet on both sides.

## Files

| File | Purpose |
|------|---------|
| `clipboard_sender.py` | Sender app: generates code, monitors clipboard, sends text |
| `clipboard_receiver.py` | Receiver app: enters code, polls, displays received text |
| `relay_server.py` | Optional self-hosted relay (LAN only, not required) |
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