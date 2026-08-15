# sg-hostd

`sg-hostd` is the small host-side helper for SG-Gateway.

It exposes only explicit, allow-listed operations. It must never provide
arbitrary shell execution to the web panel.

## Current MVP Commands

- `awg.status`
- `xray.status`
- `nftables.status`
- `system.diagnostics`

## Local Run

```powershell
cd hostd
python -m pip install -r requirements.txt
waitress-serve --host=127.0.0.1 --port=8090 sg_hostd.app:app
```

## API

```text
GET  /health
GET  /commands
POST /commands/<allowed-command>
```

Unknown commands return `403`.