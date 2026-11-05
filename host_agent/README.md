# JMY-RAS Linux Host Agent

First Linux agent release: **0.1.0 (read-only host inventory)**.

## What it does
- Runs visibly in the foreground on Kali Linux and other Linux distributions.
- Exposes authenticated health and host-inventory endpoints.
- Creates a random bearer token in `~/.config/jmy-ras/agent.token` with file mode `0600`.
- Uses constant-time token comparison and never logs the Authorization header.
- Binds to loopback by default. For remote use, bind only to the host's private VPN IP.

## What it does not do yet
No screen capture, remote desktop, keyboard/mouse injection, shell execution, or file transfer. No hidden service or persistence is installed. Do not treat this as a complete remote-control product.

## Install on the Kali host
From the repository root:

```bash
sudo apt update
sudo apt install -y python3-psutil
python3 host_agent/agent.py
```

The default listener is `127.0.0.1:8765`. To stop it, press Ctrl+C. The first run creates the token file. Keep it private and do not paste it into chats or screenshots.

## Secure remote access using Tailscale
Tailscale creates an encrypted private network using WireGuard. It is a network transport, not a JMY-RAS feature.

1. Install Tailscale on the Kali host and on the phone/laptop you will use remotely, using the official instructions: https://tailscale.com/kb/installation
2. Sign both devices into the same tailnet and enable MFA on the identity provider.
3. On Kali, obtain the VPN address:
   ```bash
   tailscale ip -4
   ```
4. Start the agent bound to that exact Tailscale IP (replace the example):
   ```bash
   python3 host_agent/agent.py --bind 100.x.y.z
   ```
   Do not use `0.0.0.0`. This avoids listening on the ordinary Wi-Fi/LAN interfaces.
5. From the remote device, access `http://100.x.y.z:8765/health` and `http://100.x.y.z:8765/v1/host`. The HTTP application traffic is protected by the Tailscale WireGuard tunnel while it stays inside the tailnet.
6. Add a tailnet ACL/grant so only your own remote device/user can reach TCP port 8765. Keep the token file private.

The agent token is separate from the existing dashboard pairing token. Read it locally on the Kali host only when configuring an authorized client:
```bash
cat ~/.config/jmy-ras/agent.token
``
Use it as an HTTP header: `Authorization: Bearer YOUR_TOKEN`. Never share the token publicly. If compromised, stop the agent, remove the token file, and restart to generate a new one.

## Local test
With the agent running on loopback:
```bash
TOKEN="$(cat ~/.config/jmy-ras/agent.token)"
curl -i http://127.0.0.1:8765/health -H "Authorization: Bearer $TOKEN"
curl -i http://127.0.0.1:8765/v1/host -H "Authorization: Bearer $TOKEN"
```
An unauthenticated request should return HTTP 401.

## Network limitations
Remote access requires the Kali PC to be powered on, awake, connected to the internet, and running the agent. Tailscale can traverse many NAT/CGNAT setups, but it cannot connect a powered-off or disconnected computer. Do not port-forward this agent or expose it directly to the public internet.
