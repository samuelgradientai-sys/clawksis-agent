# VS Code Server Headless Setup + Cloudflare Tunnel

## Purpose
Expose VS Code Server (with extensions installed) on a headless Linux server via Cloudflare quick tunnel, enabling browser-based access to the full VS Code IDE — including the ability to install and run AI extensions (Kickbacks.dev, Claude Code, etc.).

## Steps

### 1. Install VS Code CLI standalone
```bash
curl -Lk 'https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64' -o /tmp/vscode-cli.tar.gz
tar -xzf /tmp/vscode-cli.tar.gz -C /usr/local/bin/
```

### 2. Start VS Code Web Server
```bash
code serve-web --accept-server-license-terms --without-connection-token --port 8765 --server-data-dir /root/.vscode-serve
```

### 3. Expose via Cloudflare Tunnel
```bash
cloudflared tunnel --url http://localhost:8765
```
Creates a URL like `https://random-words.trycloudflare.com`

### 4. Install extensions via Marketplace UI
- Open the Cloudflare tunnel URL in a browser
- Navigate to Extensions tab (Ctrl+Shift+X)
- Search for the extension in the marketplace
- Click Install

### 5. Alternative: Pre-install extensions by copying to extensions dir
```bash
# Download VSIX
curl -L <vsix-url> -o /tmp/ext.vsix
# Extract to temp dir
unzip /tmp/ext.vsix -d /tmp/ext-tmp
# Copy to VS Code extensions directory
mkdir -p /root/.vscode-serve/extensions/<publisher>.<name>-<version>
cp -r /tmp/ext-tmp/extension/* /root/.vscode-serve/extensions/<publisher>.<name>-<version>/
# Restart serve-web
```

## Known Issues
- Standalone `code` CLI cannot install VSIX files (requires full VS Code desktop installation)
- Extensions must be installed via the web UI marketplace or pre-placed in the extensions directory
- First startup downloads VS Code Server (~200MB) — takes 10-30 seconds

## Kickbacks.dev Extension
- Marketplace ID: `kickbacks.kickbacks-dev`
- Publisher: Kickbacks
- Model: Earn 70% of ad revenue from sponsored content in Claude Code/Codex wait states
- Works with: VS Code, Claude Code CLI, Codex CLI
- Source: https://github.com/andrewmccalip/kickbacks.ai.git
