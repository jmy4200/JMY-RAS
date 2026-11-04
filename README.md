# JMY Remote Access System (JMY-RAS)

Cross-platform, consent-based remote administration and digital forensics toolkit. Early development scaffold.

## Current status
**v0.1.0 — foundation scaffold.** This repository is not yet a production remote desktop tool. Screen capture/control, secure pairing, network transport, and platform adapters are planned and must be implemented and security-reviewed before deployment.

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

## Safety defaults
- Backend binds to loopback by default.
- Do not expose it directly to the public internet.
- Remote access must use authenticated, encrypted transport and explicit device pairing.
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
