# JMY Remote Access System (JMY-RAS)

Cross-platform, consent-based remote administration and digital forensics toolkit. Early development scaffold.

## Current status
**Dashboard/backend v0.4.2 + Linux host agent v0.1.0.** Offline-first dashboard, LAN pairing, and a separate authenticated read-only Kali/Linux host agent are available. The host agent reports system inventory over a private VPN interface. Screen capture, keyboard/mouse control, terminal access, and file transfer are not implemented.

## Linux host agent (v0.1.0)\n\nSee [host_agent/README.md](host_agent/README.md) for installation and private Tailscale/WireGuard network setup. The agent defaults to loopback, requires a private bearer token, and exposes read-only health/inventory endpoints. Bind it only to the host's VPN IP for remote access; never use `0.0.0.0` or public port forwarding.\n\n## Goals
- Offline access on a shared LAN
- Offline-first local notes with authenticated, idempotent synchronization
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

## Offline-first behavior (v0.4.2)
- The dashboard application shell is cached by its service worker for offline reopening after it has first loaded successfully.
- Operator notes are stored in the current browser's local storage while offline.
- When the host API becomes reachable and the browser has a valid paired bearer token, queued notes are sent to `POST /api/sync/events`.
- The server deduplicates events by UUID so retrying a sync does not create duplicate notes.
- Local notes remain in that browser until the server confirms the sync. Clearing browser site data can erase notes that have not synced; do not use this queue as the only copy of critical forensic evidence.
- Offline mode does not mean remote control works without a communication path. For access between sites 100 km apart, use an independently available private network link (for example a properly secured site-to-site VPN over available connectivity, or a private radio/fiber WAN).

## Roadmap
1. Offline-first dashboard, queued notes, and authenticated synchronization
2. Owner authentication, device revocation, and audit improvements
3. Encrypted transport and private networking (e.g. WireGuard)
4. Consent-based screen sharing and visible input-control approval
5. Secure file transfer and explicitly approved terminal sessions
6. Forensic collection, manifests, and SHA-256 integrity verification
7. Windows/Linux packaging; mobile clients

## License
MIT (see LICENSE).


## Web Dashboard (v0.4.1)

Start the API on your host computer:

```bash
source .venv/bin/activate
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open the dashboard on the same computer: **http://127.0.0.1:8000/dashboard/**

The dashboard displays host health, operating system, CPU and memory usage; generates local one-time pairing codes; and can show registered devices when supplied a paired bearer token. After pairing, the token is retained in the current browser tab session so a page refresh does not immediately lose it. Closing the tab clears that session; never share the token in screenshots or chat. It is a development interface. The prototype uses HTTP and does not implement remote screen viewing or input control. On Android, the current HTTP LAN URL is not a secure context for service-worker offline installation; HTTPS setup is a required next step for reliable offline reopening. Do not expose it to the public internet.
