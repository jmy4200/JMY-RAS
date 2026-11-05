# JMY Remote Access System (JMY-RAS)

Cross-platform, consent-based remote administration and digital forensics toolkit. Early development scaffold.

## Current status
**v0.3.0 — LAN discovery and pairing foundation.** The API can report usable IPv4 addresses and accept a pairing claim from a LAN client. Screen capture, keyboard/mouse control, terminal access, and file transfer are not implemented.

## Goals
- Offline access on a shared LAN
- Secure remote access over private networking (e.g. WireGuard)
- Windows and Linux host support, with additional OS adapters later
- Remote screen, keyboard/mouse, terminal, and file transfer with explicit user consent
- Forensic collection with audit trails and SHA-256 integrity verification

## Quick start (Kali Linux / Linux)
```bash
git clone https://github.com/jmy4200/JMY-RAS.git
cd JMY-RAS
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 and API docs at http://127.0.0.1:8000/docs.

## Development: connect a phone on the same private LAN

1. Connect the Linux host and phone to the same trusted Wi-Fi network or phone hotspot. Internet access is not required.
2. On the Linux host, start the API on the LAN interface:
   ```bash
   uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```
3. On the Linux host itself, open http://127.0.0.1:8000/docs and call **POST /api/pairing/code**. Pairing-code creation is restricted to loopback clients.
4. Open **GET /api/network/lan-info** to see the host's LAN IPv4 address.
5. On the phone, open `http://HOST_LAN_IP:8000/docs`, then call **POST /api/pairing/claim** with the six-digit code, a device name, and platform.
6. Keep the returned access token private. It is a credential; do not post it in chats, screenshots, or issue reports.

Example claim body:
```json
{
  "code": "123456",
  "device_name": "My Android Phone",
  "platform": "Android"
}
```

This is a development-only HTTP prototype. Use only on a trusted private network that you control. HTTP does not encrypt traffic, so the access token can be exposed to other devices able to observe the network. Do not use public Wi-Fi, port forwarding, or expose this server to the internet. Production LAN pairing must use TLS, owner approval, rate limiting, and network access controls.

## Safety defaults
- Backend binds to loopback by default in the quick-start command.
- Pairing codes can only be generated locally on the host computer.
- Pairing codes expire after five minutes and can be used once.
- Access tokens are stored as hashes in SQLite; the raw token is returned only during pairing.
- Do not expose the development HTTP server directly to the public internet.
- Only install agents on devices you own or are authorized to administer.
- Forensics features should preserve evidence integrity and record operator actions.

## Roadmap
1. API foundation and system inventory
2. Authentication, device identity, pairing, and audit events
3. LAN discovery and encrypted transport
4. Consent-based screen sharing and input adapters
5. Secure file transfer and terminal sessions
6. Forensic collection, manifests, and hash verification
7. Windows/Linux packaging; mobile and macOS clients

## License
MIT (see LICENSE).


## Web Dashboard (v0.4.0)

Start the API on your host computer:

```bash
source .venv/bin/activate
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open the dashboard on the same computer: **http://127.0.0.1:8000/dashboard/**

The dashboard displays host health, operating system, CPU and memory usage; generates local one-time pairing codes; and can show registered devices when supplied a paired bearer token. It is a development interface. The prototype uses HTTP and does not implement remote screen viewing or input control. Do not expose it to the public internet.
