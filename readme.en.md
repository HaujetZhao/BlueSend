English | [中文](readme.md)

# BlueSend

Turn your phone into a wireless keyboard, clipboard bridge, and file channel for your PC over Bluetooth Low Energy (BLE).

**No app to install on the phone**: open a web page in the browser and connect. The PC side runs a small portable program.

> [!NOTE]
> Typing and clipboard sync **do not need the same network** — data goes directly over Bluetooth. File transfer uses the local network, so the phone and PC must be on the same Wi-Fi.

## Features

- **Instant typing**: characters appear at the PC cursor as you type, just like a physical keyboard
- **Classic send**: compose a block of text and send it in one go
- **Clipboard sync**: push and pull clipboard contents in both directions
- **File transfer over LAN**: Bluetooth delivers the upload URL to the phone; one tap opens a page hosted by the PC, where you can pick multiple files and save them to a chosen folder
- **Auto-reconnect**: after a Bluetooth drop, the page reconnects silently in the background
- **Link watchdog**: the PC sends a heartbeat every 3 seconds; if the page receives nothing for 9 seconds, it treats the link as dead and reconnects
- **Tray resident**: the PC app lives in the system tray instead of the taskbar

## Install and use

### 1. Run the PC app

Requirements: Windows 10/11 with a Bluetooth adapter that supports the BLE peripheral role (built-in adapters on most laptops do).

1. Open [Releases](https://github.com/HaujetZhao/BlueSend/releases/latest) and download the latest `BlueSend-<version>-win64.zip`.
2. Unzip and double-click `BlueSend.exe`. The app hides to the system tray. Hover the tray icon to see the version; right-click for show/hide window, copy upload address, restart, and quit. Double-clicking the icon toggles the window.

No Python installation needed. Delete the program folder to uninstall.

### 2. Connect from the phone

1. On the phone, open **https://haujetzhao.github.io/BlueSend/**.
2. Turn on Bluetooth, tap the connection status pill in the top-left corner, and pick your PC from the list.
3. When the status bar at the bottom shows “Connected (attempt N)”, you're in. Typing and clipboard actions are reported on the same line.

Browser requirements:

- **Android**: Chromium-based browsers such as Chrome or Edge
- **iOS**: open the URL above in a Web Bluetooth–capable browser such as [Bluefy](https://apps.apple.com/app/bluefy-web-ble-browser/id1492828568)

> [!IMPORTANT]
> Keep a single tab open. Multiple tabs each create their own Bluetooth client and fight over the same device, which shows up as failed connections or instant drops. The PC app also runs as a single instance; a second launch prints a notice and exits.

### 3. Daily use

- **Typing**: use the phone as a keyboard. “Instant” sends as you type; “Classic send” is for composing a paragraph first.
- **Clipboard**: push and pull between phone and PC. If another program is holding the PC clipboard, the app reports it instead of wiping the phone clipboard.
- **Files**: with both devices on the same LAN, tap “Send file”. The first time, the browser asks for local network permission; after you allow it, the page probes the PC. Files land in a `手机传输` (Phone Transfer) folder under Downloads or Desktop (switchable on the upload page; Downloads by default).
- **Leaving and coming back**: after a signal drop, the page reconnects in the background on its own.

### FAQ

- **The PC doesn't show up in the phone's device list**: make sure the PC app is running (the newest log under `logs\` should contain “广播状态：2”), Bluetooth is on, and the app isn't running twice.
- **Can't connect after restarting the PC app**: Chrome caches the old Bluetooth service handles, and the page keeps retrying in the background. Refresh the page, or tap the status pill to scan again.
- **The file upload page won't open**: confirm both devices are on the same LAN and Windows Firewall allows the program. Bluetooth keeps working regardless.
- **Moving to another PC**: copy the whole program folder. Configuration lives in `core\config.toml`, logs in `logs\`.

## Development

### Environment

- Python 3.12+, dependencies managed with [uv](https://docs.astral.sh/uv/)
- Node.js 22+

### Run from source

```powershell
cd server
uv run python main.py
```

Seeing “广播状态：2（Started）” means it's advertising and waiting for the phone. When running from source, the console window stays visible for logs.

Two ways to reach the phone page:

- **Online**: `https://haujetzhao.github.io/BlueSend/` (built and deployed by GitHub Actions on every push to `main`)
- **Local dev**: run `npm run dev` under `web\`, open `https://<PC LAN IP>:5173` on the phone, and trust the self-signed certificate on first visit

If a network change alters the LAN IP and the certificate no longer matches, re-issue it from the `web` directory:

```bash
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout certs/key.pem -out certs/cert.pem -days 3650 \
  -subj "/CN=ble-local" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:<current LAN IP>"
```

### Frontend commands

All run under `web\`:

```powershell
npm install
npm run dev        # HTTPS dev server, reachable from the phone
npm test           # frame codec and locale key parity tests
npm run build      # single-file output dist/index.html
npm run build:pwa  # PWA output for GitHub Pages
```

### PC unit tests

```powershell
cd server
uv run pytest
```

### Project layout

```text
├── web/                    Phone web app (Vue 3 + Vite)
│   ├── src/                App.vue, styles.css, logic/, composables/
│   ├── public/             PWA icons
│   ├── certs/              Self-signed certs for the dev server
│   └── vite.config*.js     Dev / single-file / PWA builds
├── server/                 PC side, WinRT GATT Server
│   ├── main.py             Entry: logging, single-instance lock, start and restart
│   ├── BlueSend.spec       PyInstaller config
│   ├── core/               Protocol, codec, clipboard, typing, upload server, tray
│   └── tests/              pytest
├── .github/workflows/      GitHub Actions: build the PWA and deploy to Pages
├── protocol.md             Protocol: UUIDs, frame format, message types
├── AGENTS.md               Project notes and development conventions
├── readme.md               Chinese README
└── readme.en.md            English README
```

### Build the exe

```powershell
cd server
uv run pyinstaller BlueSend.spec
```

Output lands in `server\dist\BlueSend\`. Zip the whole folder to distribute; the target machine needs no Python. `core\` ships as editable source — after changing config or code, restart the exe and the change takes effect without repackaging.

### Release

The single source of truth for the version is [server/pyproject.toml](server/pyproject.toml); [web/package.json](web/package.json) must match. The version is baked into the exe and shown in the startup banner and tray tooltip.

1. Bump the version in both `server/pyproject.toml` and `web/package.json`.
2. Commit and tag: `git tag v<version>`, then push `main` and the tag.
3. Pushing `main` triggers GitHub Actions to build and publish the phone page (the workflow runs `npm ci`, `npm test`, and `npm run build:pwa` under `web/`). The repository's Settings → Pages Source must be set to **GitHub Actions**.
4. Build the PC app, zip `server\dist\BlueSend\` into `BlueSend-<version>-win64.zip`, and attach it to the matching GitHub Release.

When changing the protocol, keep `protocol.md`, `server/core/server.py`, `server/core/protocol.py`, `web/src/logic/protocol.js`, and `web/src/logic/frame-codec.js` in sync.
