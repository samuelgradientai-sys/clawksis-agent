---
sidebar_position: 3
title: "Nix & NixOS Setup"
description: "Install and deploy Clawksis with Nix — from quick `nix run` to fully declarative NixOS module with container mode"
---

# Nix & NixOS Setup

Clawksis ships a Nix flake with three levels of integration:

| Level | Who it's for | What you get |
|-------|-------------|--------------|
| **`nix run` / `nix profile install`** | Any Nix user (macOS, Linux) | Pre-built binary with all deps — then use the standard CLI workflow |
| **NixOS module (native)** | NixOS server deployments | Declarative config, hardened systemd service, managed secrets |
| **NixOS module (container)** | Agents that need self-modification | Everything above, plus a persistent Ubuntu container where the agent can `apt`/`pip`/`npm install` |

:::info What's different from the standard install
The `curl | bash` installer manages Python, Node, and dependencies itself. The Nix flake replaces all of that — every Python dependency is a Nix derivation built by [uv2nix](https://github.com/pyproject-nix/uv2nix), and runtime tools (Node.js, git, ripgrep, ffmpeg) are wrapped into the binary's PATH. There is no runtime pip, no venv activation, no `npm install`.

**For non-NixOS users**, this only changes the install step. Everything after (`clawk setup`, `clawk gateway install`, config editing) works identically to the standard install.

**For NixOS module users**, the entire lifecycle is different: configuration lives in `configuration.nix`, secrets go through sops-nix/agenix, the service is a systemd unit, and CLI config commands are blocked. You manage clawk the same way you manage any other NixOS service.
:::

## Prerequisites

- **Nix with flakes enabled** — [Determinate Nix](https://install.determinate.systems) recommended (enables flakes by default)
- **API keys** for the services you want to use (at minimum: an OpenRouter or Anthropic key)

---

## Quick Start (Any Nix User)

No clone needed. Nix fetches, builds, and runs everything:

```bash
# Run directly (builds on first use, cached after)
nix run github:samuelgradientai-sys/clawksis-agent -- setup
nix run github:samuelgradientai-sys/clawksis-agent -- chat

# Or install persistently
nix profile install github:samuelgradientai-sys/clawksis-agent
clawk setup
clawk chat
```

After `nix profile install`, `clawk`, `clawksis-agent`, and `clawk-acp` are on your PATH. From here, the workflow is identical to the [standard installation](./installation.md) — `clawk setup` walks you through provider selection, `clawk gateway install` sets up a launchd (macOS) or systemd user service, and config lives in `~/.clawksis/`.

:::warning Messaging platforms (Discord, Telegram, Slack)
The default package doesn't include messaging platform libraries — they were moved to on-demand installation, which can't work in Nix's read-only environment. If you plan to connect the agent to Discord, Telegram, or Slack, install the `messaging` variant:

```bash
nix profile install github:samuelgradientai-sys/clawksis-agent#messaging
```

For all optional extras (voice, all providers, all platforms):

```bash
nix profile install github:samuelgradientai-sys/clawksis-agent#full
```

The `full` variant adds ~700 MB to the closure. If you only need messaging platforms, `#messaging` adds just ~33 MB.
:::

<details>
<summary><strong>Building from a local clone</strong></summary>

```bash
git clone https://github.com/samuelgradientai-sys/clawksis-agent.git
cd clawksis-agent
nix build
./result/bin/clawk setup
```

</details>

---

## NixOS Module

The flake exports `nixosModules.default` — a full NixOS service module that declaratively manages user creation, directories, config generation, secrets, documents, and service lifecycle.

:::note
This module requires NixOS. For non-NixOS systems (macOS, other Linux distros), use `nix profile install` and the standard CLI workflow above.
:::

### Add the Flake Input

```nix
# /etc/nixos/flake.nix (or your system flake)
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    clawksis-agent.url = "github:samuelgradientai-sys/clawksis-agent";
  };

  outputs = { nixpkgs, clawksis-agent, ... }: {
    nixosConfigurations.your-host = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        clawksis-agent.nixosModules.default
        ./configuration.nix
      ];
    };
  };
}
```

### Minimal Configuration

```nix
# configuration.nix
{ config, ... }: {
  services.clawksis-agent = {
    enable = true;
    settings.model.default = "anthropic/claude-sonnet-4";
    environmentFiles = [ config.sops.secrets."clawk-env".path ];
    addToSystemPackages = true;
  };
}
```

That's it. `nixos-rebuild switch` creates the `clawk` user, generates `config.yaml`, wires up secrets, and starts the gateway — a long-running service that connects the agent to messaging platforms (Telegram, Discord, etc.) and listens for incoming messages.

:::warning Secrets are required
The `environmentFiles` line above assumes you have [sops-nix](https://github.com/Mic92/sops-nix) or [agenix](https://github.com/ryantm/agenix) configured. The file should contain at least one LLM provider key (e.g., `OPENROUTER_API_KEY=sk-or-...`). See [Secrets Management](#secrets-management) for full setup. If you don't have a secrets manager yet, you can use a plain file as a starting point — just ensure it's not world-readable:

```bash
echo "OPENROUTER_API_KEY=sk-or-your-key" | sudo install -m 0600 -o clawk /dev/stdin /var/lib/clawksis/env
```

```nix
services.clawksis-agent.environmentFiles = [ "/var/lib/clawksis/env" ];
```
:::

:::tip addToSystemPackages
Setting `addToSystemPackages = true` does two things: puts the `clawk` CLI on your system PATH **and** sets `CLAWK_HOME` system-wide so the interactive CLI shares state (sessions, skills, cron) with the gateway service. Without it, running `clawk` in your shell creates a separate `~/.clawksis/` directory.
:::

### Container-aware CLI

:::info
When `container.enable = true` and `addToSystemPackages = true`, **every** `clawk` command on the host automatically routes into the managed container. This means your interactive CLI session runs inside the same environment as the gateway service — with access to all container-installed packages and tools.

- The routing is transparent: `clawk chat`, `clawk sessions list`, `clawk version`, etc. all exec into the container under the hood
- All CLI flags are forwarded as-is
- If the container isn't running, the CLI retries briefly (5s with a spinner for interactive use, 10s silently for scripts) then fails with a clear error — no silent fallback
- For developers working on the clawk codebase, set `CLAWK_DEV=1` to bypass container routing and run the local checkout directly

Set `container.hostUsers` to create a `~/.clawksis` symlink to the service state directory, so the host CLI and the container share sessions, config, and memories:

```nix
services.clawksis-agent = {
  container.enable = true;
  container.hostUsers = [ "your-username" ];
  addToSystemPackages = true;
};
```

Users listed in `hostUsers` are automatically added to the `clawk` group for file permission access.

**Podman users:** The NixOS service runs the container as root. Docker users get access via the `docker` group socket, but Podman's rootful containers require sudo. Grant passwordless sudo for your container runtime:

```nix
security.sudo.extraRules = [{
  users = [ "your-username" ];
  commands = [{
    command = "/run/current-system/sw/bin/podman";
    options = [ "NOPASSWD" ];
  }];
}];
```

The CLI auto-detects when sudo is needed and uses it transparently. Without this, you'll need to run `sudo clawk chat` manually.
:::

### Verify It Works

After `nixos-rebuild switch`, check that the service is running:

```bash
# Check service status
systemctl status clawksis-agent

# Watch logs (Ctrl+C to stop)
journalctl -u clawksis-agent -f

# If addToSystemPackages is true, test the CLI
clawk version
clawk config       # shows the generated config
```

### Choosing a Deployment Mode

The module supports two modes, controlled by `container.enable`:

| | **Native** (default) | **Container** |
|---|---|---|
| How it runs | Hardened systemd service on the host | Persistent Ubuntu container with `/nix/store` bind-mounted |
| Security | `NoNewPrivileges`, `ProtectSystem=strict`, `PrivateTmp` | Container isolation, runs as unprivileged user inside |
| Agent can self-install packages | No — only tools on the Nix-provided PATH | Yes — `apt`, `pip`, `npm` installs persist across restarts |
| Config surface | Same | Same |
| When to choose | Standard deployments, maximum security, reproducibility | Agent needs runtime package installation, mutable environment, experimental tools |

To enable container mode, add one line:

```nix
{
  services.clawksis-agent = {
    enable = true;
    container.enable = true;
    # ... rest of config is identical
  };
}
```

:::info
Container mode auto-enables `virtualisation.docker.enable` via `mkDefault`. If you use Podman instead, set `container.backend = "podman"` and `virtualisation.docker.enable = false`.
:::

---

## Configuration

### Declarative Settings

The `settings` option accepts an arbitrary attrset that is rendered as `config.yaml`. It supports deep merging across multiple module definitions (via `lib.recursiveUpdate`), so you can split config across files:

```nix
# base.nix
services.clawksis-agent.settings = {
  model.default = "anthropic/claude-sonnet-4";
  toolsets = [ "all" ];
  terminal = { backend = "local"; timeout = 180; };
};

# personality.nix
services.clawksis-agent.settings = {
  display = { compact = false; personality = "kawaii"; };
  memory = { memory_enabled = true; user_profile_enabled = true; };
};
```

Both are deep-merged at evaluation time. Nix-declared keys always win over keys in an existing `config.yaml` on disk, but **user-added keys that Nix doesn't touch are preserved**. This means if the agent or a manual edit adds keys like `skills.disabled` or `streaming.enabled`, they survive `nixos-rebuild switch`.

:::note Model naming
`settings.model.default` uses the model identifier your provider expects. With [OpenRouter](https://openrouter.ai) (the default), these look like `"anthropic/claude-sonnet-4"` or `"google/gemini-3-flash"`. If you're using a provider directly (Anthropic, OpenAI), set `settings.model.base_url` to point at their API and use their native model IDs (e.g., `"claude-sonnet-4-20250514"`). When no `base_url` is set, Clawksis defaults to OpenRouter.
:::

:::tip Discovering available config keys
Run `nix build .#configKeys && cat result` to see every leaf config key extracted from Python's `DEFAULT_CONFIG`. You can paste your existing `config.yaml` into the `settings` attrset — the structure maps 1:1.
:::

<details>
<summary><strong>Full example: all commonly customized settings</strong></summary>

```nix
{ config, ... }: {
  services.clawksis-agent = {
    enable = true;
    container.enable = true;

    # ── Model ──────────────────────────────────────────────────────────
    settings = {
      model = {
        base_url = "https://openrouter.ai/api/v1";
        default = "anthropic/claude-opus-4.6";
      };
      toolsets = [ "all" ];
      max_turns = 100;
      terminal = { backend = "local"; cwd = "."; timeout = 180; };
      compression = {
        enabled = true;
        threshold = 0.85;
        summary_model = "google/gemini-3-flash-preview";
      };
      memory = { memory_enabled = true; user_profile_enabled = true; };
      display = { compact = false; personality = "kawaii"; };
      agent = { max_turns = 60; verbose = false; };
    };

    # ── Secrets ────────────────────────────────────────────────────────
    environmentFiles = [ config.sops.secrets."clawk-env".path ];

    # ── Documents ──────────────────────────────────────────────────────
    documents = {
      "USER.md" = ./documents/USER.md;
    };

    # ── MCP Servers ────────────────────────────────────────────────────
    mcpServers.filesystem = {
      command = "npx";
      args = [ "-y" "@modelcontextprotocol/server-filesystem" "/data/workspace" ];
    };

    # ── Container options ──────────────────────────────────────────────
    container = {
      image = "ubuntu:24.04";
      backend = "docker";
      hostUsers = [ "your-username" ];
      extraVolumes = [ "/home/user/projects:/projects:rw" ];
      extraOptions = [ "--gpus" "all" ];
    };

    # ── Service tuning ─────────────────────────────────────────────────
    addToSystemPackages = true;
    extraArgs = [ "--verbose" ];
    restart = "always";
    restartSec = 5;
  };
}
```

</details>

### Escape Hatch: Bring Your Own Config

If you'd rather manage `config.yaml` entirely outside Nix, use `configFile`:

```nix
services.clawksis-agent.configFile = /etc/clawksis/config.yaml;
```

This bypasses `settings` entirely — no merge, no generation. The file is copied as-is to `$CLAWK_HOME/config.yaml` on each activation.

### Customization Cheatsheet

Quick reference for the most common things Nix users want to customize:

| I want to... | Option | Example |
|---|---|---|
| Change the LLM model | `settings.model.default` | `"anthropic/claude-sonnet-4"` |
| Use a different provider endpoint | `settings.model.base_url` | `"https://openrouter.ai/api/v1"` |
| Add API keys | `environmentFiles` | `[ config.sops.secrets."clawk-env".path ]` |
| Give the agent a personality | `${services.clawksis-agent.stateDir}/.clawksis/SOUL.md` | manage the file directly |
| Add MCP tool servers | `mcpServers.<name>` | See [MCP Servers](#mcp-servers) |
| Enable Discord/Telegram/Slack | `extraDependencyGroups` | `[ "messaging" ]` |
| Mount host directories into container | `container.extraVolumes` | `[ "/data:/data:rw" ]` |
| Pass GPU access to container | `container.extraOptions` | `[ "--gpus" "all" ]` |
| Use Podman instead of Docker | `container.backend` | `"podman"` |
| Share state between host CLI and container | `container.hostUsers` | `[ "sidbin" ]` |
| Make extra tools available to the agent | `extraPackages` | `[ pkgs.pandoc pkgs.imagemagick ]` |
| Use a custom base image | `container.image` | `"ubuntu:24.04"` |
| Override the clawk package | `package` | `inputs.clawksis-agent.packages.${system}.default.override { ... }` |
| Change state directory | `stateDir` | `"/opt/clawksis"` |
| Set the agent's working directory | `workingDirectory` | `"/home/user/projects"` |

---

## Secrets Management

:::danger Never put API keys in `settings` or `environment`
Values in Nix expressions end up in `/nix/store`, which is world-readable. Always use `environmentFiles` with a secrets manager.
:::

Both `environment` (non-secret vars) and `environmentFiles` (secret files) are merged into `$CLAWK_HOME/.env` at activation time (`nixos-rebuild switch`). Clawksis reads this file on every startup, so changes take effect with a `systemctl restart clawksis-agent` — no container recreation needed.

### sops-nix

```nix
{
  sops = {
    defaultSopsFile = ./secrets/clawk.yaml;
    age.keyFile = "/home/user/.config/sops/age/keys.txt";
    secrets."clawk-env" = { format = "yaml"; };
  };

  services.clawksis-agent.environmentFiles = [
    config.sops.secrets."clawk-env".path
  ];
}
```

The secrets file contains key-value pairs:

```yaml
# secrets/clawk.yaml (encrypted with sops)
clawk-env: |
    OPENROUTER_API_KEY=sk-or-...
    TELEGRAM_BOT_TOKEN=123456:ABC...
    ANTHROPIC_API_KEY=sk-ant-...
```

### agenix

```nix
{
  age.secrets.clawk-env.file = ./secrets/clawk-env.age;

  services.clawksis-agent.environmentFiles = [
    config.age.secrets.clawk-env.path
  ];
}
```

### OAuth / Auth Seeding

For platforms requiring OAuth (e.g., Discord), use `authFile` to seed credentials on first deploy:

```nix
{
  services.clawksis-agent = {
    authFile = config.sops.secrets."clawk/auth.json".path;
    # authFileForceOverwrite = true;  # overwrite on every activation
  };
}
```

The file is only copied if `auth.json` doesn't already exist (unless `authFileForceOverwrite = true`). Runtime OAuth token refreshes are written to the state directory and preserved across rebuilds.

---

## Documents

The `documents` option installs files into the agent's working directory (the `workingDirectory`, which the agent reads as its workspace). Clawksis looks for specific filenames by convention:

- **`USER.md`** — context about the user the agent is interacting with.
- Any other files you place here are visible to the agent as workspace files.

The agent identity file is separate: Clawksis loads its primary `SOUL.md` from `$CLAWK_HOME/SOUL.md`, which in the NixOS module is `${services.clawksis-agent.stateDir}/.clawksis/SOUL.md`. Putting `SOUL.md` in `documents` only creates a workspace file and will not replace the main persona file.

```nix
{
  services.clawksis-agent.documents = {
    "USER.md" = ./documents/USER.md;  # path reference, copied from Nix store
  };
}
```

Values can be inline strings or path references. Files are installed on every `nixos-rebuild switch`.

---

## MCP Servers

The `mcpServers` option declaratively configures [MCP (Model Context Protocol)](https://modelcontextprotocol.io) servers. Each server uses either **stdio** (local command) or **HTTP** (remote URL) transport.

### Stdio Transport (Local Servers)

```nix
{
  services.clawksis-agent.mcpServers = {
    filesystem = {
      command = "npx";
      args = [ "-y" "@modelcontextprotocol/server-filesystem" "/data/workspace" ];
    };
    github = {
      command = "npx";
      args = [ "-y" "@modelcontextprotocol/server-github" ];
      env.GITHUB_PERSONAL_ACCESS_TOKEN = "\${GITHUB_TOKEN}"; # resolved from .env
    };
  };
}
```

:::tip
Environment variables in `env` values are resolved from `$CLAWK_HOME/.env` at runtime. Use `environmentFiles` to inject secrets — never put tokens directly in Nix config.
:::

### HTTP Transport (Remote Servers)

```nix
{
  services.clawksis-agent.mcpServers.remote-api = {
    url = "https://mcp.example.com/v1/mcp";
    headers.Authorization = "Bearer \${MCP_REMOTE_API_KEY}";
    timeout = 180;
  };
}
```

### HTTP Transport with OAuth

Set `auth = "oauth"` for servers using OAuth 2.1. Clawksis implements the full PKCE flow — metadata discovery, dynamic client registration, token exchange, and automatic refresh.

```nix
{
  services.clawksis-agent.mcpServers.my-oauth-server = {
    url = "https://mcp.example.com/mcp";
    auth = "oauth";
  };
}
```

Tokens are stored in `$CLAWK_HOME/mcp-tokens/<server-name>.json` and persist across restarts and rebuilds.

<details>
<summary><strong>Initial OAuth authorization on headless servers</strong></summary>

The first OAuth authorization requires a browser-based consent flow. In a headless deployment, Clawksis prints the authorization URL to stdout/logs instead of opening a browser.

**Option A: Interactive bootstrap** — run the flow once via `docker exec` (container) or `sudo -u clawk` (native):

```bash
# Container mode
docker exec -it clawksis-agent \
  clawk mcp add my-oauth-server --url https://mcp.example.com/mcp --auth oauth

# Native mode
sudo -u clawk CLAWK_HOME=/var/lib/clawksis/.clawksis \
  clawk mcp add my-oauth-server --url https://mcp.example.com/mcp --auth oauth
```

The container uses `--network=host`, so the OAuth callback listener on `127.0.0.1` is reachable from the host browser.

**Option B: Pre-seed tokens** — complete the flow on a workstation, then copy tokens:

```bash
clawk mcp add my-oauth-server --url https://mcp.example.com/mcp --auth oauth
scp ~/.clawksis/mcp-tokens/my-oauth-server{,.client}.json \
    server:/var/lib/clawksis/.clawksis/mcp-tokens/
# Ensure: chown clawk:clawk, chmod 0600
```

</details>

### Sampling (Server-Initiated LLM Requests)

Some MCP servers can request LLM completions from the agent:

```nix
{
  services.clawksis-agent.mcpServers.analysis = {
    command = "npx";
    args = [ "-y" "analysis-server" ];
    sampling = {
      enabled = true;
      model = "google/gemini-3-flash";
      max_tokens_cap = 4096;
      timeout = 30;
      max_rpm = 10;
    };
  };
}
```

---

## Managed Mode

When clawk runs via the NixOS module, the following CLI commands are **blocked** with a descriptive error pointing you to `configuration.nix`:

| Blocked command | Why |
|---|---|
| `clawk setup` | Config is declarative — edit `settings` in your Nix config |
| `clawk config edit` | Config is generated from `settings` |
| `clawk config set <key> <value>` | Config is generated from `settings` |
| `clawk gateway install` | The systemd service is managed by NixOS |
| `clawk gateway uninstall` | The systemd service is managed by NixOS |

This prevents drift between what Nix declares and what's on disk. Detection uses two signals:

1. **`CLAWK_MANAGED=true`** environment variable — set by the systemd service, visible to the gateway process
2. **`.managed` marker file** in `CLAWK_HOME` — set by the activation script, visible to interactive shells (e.g., `docker exec -it clawksis-agent clawk config set ...` is also blocked)

To change configuration, edit your Nix config and run `sudo nixos-rebuild switch`.

---

## Container Architecture

:::info
This section is only relevant if you're using `container.enable = true`. Skip it for native mode deployments.
:::

When container mode is enabled, clawk runs inside a persistent Ubuntu container with the Nix-built binary bind-mounted read-only from the host:

```
Host                                    Container
────                                    ─────────
/nix/store/...-clawksis-agent-0.1.0  ──►  /nix/store/... (ro)
~/.clawksis -> /var/lib/clawksis/.clawksis       (symlink bridge, per hostUsers)
/var/lib/clawksis/                    ──►  /data/          (rw)
  ├── current-package -> /nix/store/...    (symlink, updated each rebuild)
  ├── .gc-root -> /nix/store/...           (prevents nix-collect-garbage)
  ├── .container-identity                  (sha256 hash, triggers recreation)
  ├── .clawksis/                             (CLAWK_HOME)
  │   ├── .env                             (merged from environment + environmentFiles)
  │   ├── config.yaml                      (Nix-generated, deep-merged by activation)
  │   ├── .managed                         (marker file)
  │   ├── .container-mode                  (routing metadata: backend, exec_user, etc.)
  │   ├── state.db, sessions/, memories/   (runtime state)
  │   └── mcp-tokens/                      (OAuth tokens for MCP servers)
  ├── home/                                ──►  /home/clawk    (rw)
  └── workspace/                           (agent working directory)
      ├── SOUL.md                          (from documents option)
      └── (agent-created files)

Container writable layer (apt/pip/npm):   /usr, /usr/local, /tmp
```

The Nix-built binary works inside the Ubuntu container because `/nix/store` is bind-mounted — it brings its own interpreter and all dependencies, so there's no reliance on the container's system libraries. The container entrypoint resolves through a `current-package` symlink: `/data/current-package/bin/clawk gateway run --replace`. On `nixos-rebuild switch`, only the symlink is updated — the container keeps running.

### What Persists Across What

| Event | Container recreated? | `/data` (state) | `/home/clawk` | Writable layer (`apt`/`pip`/`npm`) |
|---|---|---|---|---|
| `systemctl restart clawksis-agent` | No | Persists | Persists | Persists |
| `nixos-rebuild switch` (code change) | No (symlink updated) | Persists | Persists | Persists |
| Host reboot | No | Persists | Persists | Persists |
| `nix-collect-garbage` | No (GC root) | Persists | Persists | Persists |
| Image change (`container.image`) | **Yes** | Persists | Persists | **Lost** |
| Volume/options change | **Yes** | Persists | Persists | **Lost** |
| `environment`/`environmentFiles` change | No | Persists | Persists | Persists |

The container is only recreated when its **identity hash** changes. The hash covers: schema version, image, `extraVolumes`, `extraOptions`, and the entrypoint script. Changes to environment variables, settings, documents, or the clawk package itself do **not** trigger recreation.

:::warning Writable layer loss
When the identity hash changes (image upgrade, new volumes, new container options), the container is destroyed and recreated from a fresh pull of `container.image`. Any `apt install`, `pip install`, or `npm install` packages in the writable layer are lost. State in `/data` and `/home/clawk` is preserved (these are bind mounts).

If the agent relies on specific packages, consider baking them into a custom image (`container.image = "my-registry/clawk-base:latest"`) or scripting their installation in the agent's SOUL.md.
:::

### GC Root Protection

The `preStart` script creates a GC root at `${stateDir}/.gc-root` pointing to the current clawk package. This prevents `nix-collect-garbage` from removing the running binary. If the GC root somehow breaks, restarting the service recreates it.

---

## Plugins

The NixOS module supports declarative plugin installation — no imperative `clawk plugins install` needed.

### Directory Plugins (`extraPlugins`)

For plugins that are just a source tree with `plugin.yaml` + `__init__.py` (e.g., [clawk-lcm](https://github.com/stephenschoettler/clawk-lcm)):

```nix
services.clawksis-agent.extraPlugins = [
  (pkgs.fetchFromGitHub {
    owner = "stephenschoettler";
    repo = "clawk-lcm";
    rev = "v0.7.0";
    hash = "sha256-...";
  })
];
```

Plugins are symlinked into `$CLAWK_HOME/plugins/` at activation time. Clawksis discovers them via its normal directory scan. Removing a plugin from the list and running `nixos-rebuild switch` removes the symlink.

### Entry-Point Plugins (`extraPythonPackages`)

For pip-packaged plugins that register via `[project.entry-points."clawk_agent.plugins"]` (e.g., [rtk-clawk](https://github.com/ogallotti/rtk-clawk)):

```nix
services.clawksis-agent.extraPythonPackages = [
  (pkgs.python312Packages.buildPythonPackage {
    pname = "rtk-clawk";
    version = "1.0.0";
    src = pkgs.fetchFromGitHub {
      owner = "ogallotti";
      repo = "rtk-clawk";
      rev = "v1.0.0";
      hash = "sha256-...";
    };
    format = "pyproject";
    build-system = [ pkgs.python312Packages.setuptools ];
  })
];
```

The package's `site-packages` is added to PYTHONPATH in the clawk wrapper. `importlib.metadata` discovers the entry point at session start.

### Optional Dependency Groups (`extraDependencyGroups`)

For optional extras declared in clawksis-agent's `pyproject.toml`, use `extraDependencyGroups` to include them in the sealed venv at build time. This is required for any extra not in the default `[all]` set — on Nix, runtime installation into the read-only store is not possible.

```nix
# Enable Discord, Telegram, Slack
services.clawksis-agent.extraDependencyGroups = [ "messaging" ];
```

```nix
# Enable a memory provider
services.clawksis-agent = {
  extraDependencyGroups = [ "hindsight" ];
  settings.memory.provider = "hindsight";
};
```

This is resolved by uv alongside core dependencies — no PYTHONPATH patching, no collision risk. Available groups:

| Group | What it enables |
|-------|-----------------|
| `messaging` | Discord, Telegram, Slack |
| `matrix` | Matrix/Element (mautrix with encryption; Linux only) |
| `dingtalk` | DingTalk |
| `feishu` | Feishu/Lark |
| `voice` | Local speech-to-text (faster-whisper) |
| `edge-tts` | Edge TTS provider |
| `tts-premium` | ElevenLabs TTS |
| `anthropic` | Native Anthropic SDK (not needed via OpenRouter) |
| `bedrock` | AWS Bedrock (boto3) |
| `azure-identity` | Azure Entra ID auth |
| `honcho` | Honcho memory provider |
| `hindsight` | Hindsight memory provider |
| `modal` | Modal terminal backend |
| `daytona` | Daytona terminal backend |
| `exa` | Exa web search |
| `firecrawl` | Firecrawl web search |
| `fal` | FAL image generation |

Or use the pre-built `#messaging` or `#full` flake packages instead of per-extra configuration (see [Quick Start](#quick-start-any-nix-user)).

**When to use which:**

| Need | Option |
|------|--------|
| Enable a pyproject.toml optional extra | `extraDependencyGroups` |
| Add an external Python plugin not in pyproject.toml | `extraPythonPackages` |
| Add a system binary (pandoc, jq, etc.) | `extraPackages` |
| Add a directory-based plugin source tree | `extraPlugins` |

### Combining Both

A directory plugin with third-party Python dependencies needs both options:

```nix
services.clawksis-agent = {
  extraPlugins = [ my-plugin-src ];          # plugin source
  extraPythonPackages = [ pkgs.python312Packages.redis ];  # its Python dep
  extraPackages = [ pkgs.redis ];            # system binary it needs
};
```

### Using the Overlay

External flakes can override the package directly:

```nix
{
  inputs.clawksis-agent.url = "github:samuelgradientai-sys/clawksis-agent";
  outputs = { clawksis-agent, nixpkgs, ... }: {
    nixpkgs.overlays = [ clawksis-agent.overlays.default ];
    # Then:
    #   pkgs.clawksis-agent.override { extraPythonPackages = [...]; }
    #   pkgs.clawksis-agent.override { extraDependencyGroups = [ "hindsight" ]; }
  };
}
```

### Plugin Configuration

Plugins still need to be enabled in `config.yaml`. Add them via the declarative settings:

```nix
services.clawksis-agent.settings.plugins.enabled = [
  "clawk-lcm"
  "rtk-rewrite"
];
```

:::note
A build-time collision check prevents plugin packages from shadowing core clawk dependencies. If a plugin provides a package already in the sealed venv, `nixos-rebuild` fails with a clear error.
:::

---

## Development

### Dev Shell

The flake provides a development shell with Python 3.12, uv, Node.js, and all runtime tools:

```bash
cd clawksis-agent
nix develop

# Shell provides:
#   - Python 3.12 + uv (deps installed into .venv on first entry)
#   - Node.js 22, ripgrep, git, openssh, ffmpeg on PATH
#   - Stamp-file optimization: re-entry is near-instant if deps haven't changed

clawk setup
clawk chat
```

### direnv (Recommended)

The included `.envrc` activates the dev shell automatically:

```bash
cd clawksis-agent
direnv allow    # one-time
# Subsequent entries are near-instant (stamp file skips dep install)
```

### Flake Checks

The flake includes build-time verification that runs in CI and locally:

```bash
# Run all checks
nix flake check

# Individual checks
nix build .#checks.x86_64-linux.package-contents   # binaries exist + version
nix build .#checks.x86_64-linux.entry-points-sync  # pyproject.toml ↔ Nix package sync
nix build .#checks.x86_64-linux.cli-commands        # gateway/config subcommands
nix build .#checks.x86_64-linux.managed-guard       # CLAWK_MANAGED blocks mutation
nix build .#checks.x86_64-linux.bundled-skills      # skills present in package
nix build .#checks.x86_64-linux.config-roundtrip    # merge script preserves user keys
```

<details>
<summary><strong>What each check verifies</strong></summary>

| Check | What it tests |
|---|---|
| `package-contents` | `clawk` and `clawksis-agent` binaries exist and `clawk version` runs |
| `entry-points-sync` | Every `[project.scripts]` entry in `pyproject.toml` has a wrapped binary in the Nix package |
| `cli-commands` | `clawk --help` exposes `gateway` and `config` subcommands |
| `managed-guard` | `CLAWK_MANAGED=true clawk config set ...` prints the NixOS error |
| `bundled-skills` | Skills directory exists, contains SKILL.md files, `CLAWK_BUNDLED_SKILLS` is set in wrapper |
| `config-roundtrip` | 7 merge scenarios: fresh install, Nix override, user key preservation, mixed merge, MCP additive merge, nested deep merge, idempotency |

</details>

---

## Options Reference

### Core

| Option | Type | Default | Description |
|---|---|---|---|
| `enable` | `bool` | `false` | Enable the clawksis-agent service |
| `package` | `package` | `clawksis-agent` | The clawksis-agent package to use |
| `user` | `str` | `"clawk"` | System user |
| `group` | `str` | `"clawk"` | System group |
| `createUser` | `bool` | `true` | Auto-create user/group |
| `stateDir` | `str` | `"/var/lib/clawk"` | State directory (`CLAWK_HOME` parent) |
| `workingDirectory` | `str` | `"${stateDir}/workspace"` | Agent working directory |
| `addToSystemPackages` | `bool` | `false` | Add `clawk` CLI to system PATH and set `CLAWK_HOME` system-wide |

### Configuration

| Option | Type | Default | Description |
|---|---|---|---|
| `settings` | `attrs` (deep-merged) | `{}` | Declarative config rendered as `config.yaml`. Supports arbitrary nesting; multiple definitions are merged via `lib.recursiveUpdate` |
| `configFile` | `null` or `path` | `null` | Path to an existing `config.yaml`. Overrides `settings` entirely if set |

### Secrets & Environment

| Option | Type | Default | Description |
|---|---|---|---|
| `environmentFiles` | `listOf str` | `[]` | Paths to env files with secrets. Merged into `$CLAWK_HOME/.env` at activation time |
| `environment` | `attrsOf str` | `{}` | Non-secret env vars. **Visible in Nix store** — do not put secrets here |
| `authFile` | `null` or `path` | `null` | OAuth credentials seed. Only copied on first deploy |
| `authFileForceOverwrite` | `bool` | `false` | Always overwrite `auth.json` from `authFile` on activation |

### Documents

| Option | Type | Default | Description |
|---|---|---|---|
| `documents` | `attrsOf (either str path)` | `{}` | Workspace files. Keys are filenames, values are inline strings or paths. Installed into `workingDirectory` on activation |

### MCP Servers

| Option | Type | Default | Description |
|---|---|---|---|
| `mcpServers` | `attrsOf submodule` | `{}` | MCP server definitions, merged into `settings.mcp_servers` |
| `mcpServers.<name>.command` | `null` or `str` | `null` | Server command (stdio transport) |
| `mcpServers.<name>.args` | `listOf str` | `[]` | Command arguments |
| `mcpServers.<name>.env` | `attrsOf str` | `{}` | Environment variables for the server process |
| `mcpServers.<name>.url` | `null` or `str` | `null` | Server endpoint URL (HTTP/StreamableHTTP transport) |
| `mcpServers.<name>.headers` | `attrsOf str` | `{}` | HTTP headers, e.g. `Authorization` |
| `mcpServers.<name>.auth` | `null` or `"oauth"` | `null` | Authentication method. `"oauth"` enables OAuth 2.1 PKCE |
| `mcpServers.<name>.enabled` | `bool` | `true` | Enable or disable this server |
| `mcpServers.<name>.timeout` | `null` or `int` | `null` | Tool call timeout in seconds (default: 120) |
| `mcpServers.<name>.connect_timeout` | `null` or `int` | `null` | Connection timeout in seconds (default: 60) |
| `mcpServers.<name>.tools` | `null` or `submodule` | `null` | Tool filtering (`include`/`exclude` lists) |
| `mcpServers.<name>.sampling` | `null` or `submodule` | `null` | Sampling config for server-initiated LLM requests |

### Service Behavior

| Option | Type | Default | Description |
|---|---|---|---|
| `extraArgs` | `listOf str` | `[]` | Extra args for `clawk gateway` |
| `extraPackages` | `listOf package` | `[]` | Extra packages available to the agent. Added to the clawk user's per-user profile so terminal commands, skills, and cron jobs all see them |
| `extraPlugins` | `listOf package` | `[]` | Directory plugin packages to symlink into `$CLAWK_HOME/plugins/`. Each must contain `plugin.yaml` |
| `extraPythonPackages` | `listOf package` | `[]` | Python packages added to PYTHONPATH for entry-point plugin discovery. Build with `python312Packages` |
| `extraDependencyGroups` | `listOf str` | `[]` | pyproject.toml optional extras to include in the sealed venv (e.g. `["hindsight"]`). Resolved by uv — no collisions |
| `restart` | `str` | `"always"` | systemd `Restart=` policy |
| `restartSec` | `int` | `5` | systemd `RestartSec=` value |

### Container

| Option | Type | Default | Description |
|---|---|---|---|
| `container.enable` | `bool` | `false` | Enable OCI container mode |
| `container.backend` | `enum ["docker" "podman"]` | `"docker"` | Container runtime |
| `container.image` | `str` | `"ubuntu:24.04"` | Base image (pulled at runtime) |
| `container.extraVolumes` | `listOf str` | `[]` | Extra volume mounts (`host:container:mode`) |
| `container.extraOptions` | `listOf str` | `[]` | Extra args passed to `docker create` |
| `container.hostUsers` | `listOf str` | `[]` | Interactive users who get a `~/.clawksis` symlink to the service stateDir and are auto-added to the `clawk` group |

---

## Directory Layout

### Native Mode

```
/var/lib/clawksis/                     # stateDir (owned by clawk:clawk, 0750)
├── .clawksis/                         # CLAWK_HOME
│   ├── config.yaml                  # Nix-generated (deep-merged each rebuild)
│   ├── .managed                     # Marker: CLI config mutation blocked
│   ├── .env                         # Merged from environment + environmentFiles
│   ├── auth.json                    # OAuth credentials (seeded, then self-managed)
│   ├── gateway.pid
│   ├── state.db
│   ├── mcp-tokens/                  # OAuth tokens for MCP servers
│   ├── sessions/
│   ├── memories/
│   ├── skills/
│   ├── cron/
│   └── logs/
├── home/                            # Agent HOME
└── workspace/                       # Agent working directory
    ├── SOUL.md                      # From documents option
    └── (agent-created files)
```

### Container Mode

Same layout, mounted into the container:

| Container path | Host path | Mode | Notes |
|---|---|---|---|
| `/nix/store` | `/nix/store` | `ro` | Clawksis binary + all Nix deps |
| `/data` | `/var/lib/clawk` | `rw` | All state, config, workspace |
| `/home/clawk` | `${stateDir}/home` | `rw` | Persistent agent home — `pip install --user`, tool caches |
| `/usr`, `/usr/local`, `/tmp` | (writable layer) | `rw` | `apt`/`pip`/`npm` installs — persists across restarts, lost on recreation |

---

## Updating

```bash
# Update the flake input (run from the directory containing flake.nix)
cd /etc/nixos && nix flake update clawksis-agent

# Rebuild
sudo nixos-rebuild switch
```

In container mode, the `current-package` symlink is updated and the agent picks up the new binary on restart. No container recreation, no loss of installed packages.

---

## Troubleshooting

:::tip Podman users
All `docker` commands below work the same with `podman`. Substitute accordingly if you set `container.backend = "podman"`.
:::

### Service Logs

```bash
# Both modes use the same systemd unit
journalctl -u clawksis-agent -f

# Container mode: also available directly
docker logs -f clawksis-agent
```

### Container Inspection

```bash
systemctl status clawksis-agent
docker ps -a --filter name=clawksis-agent
docker inspect clawksis-agent --format='{{.State.Status}}'
docker exec -it clawksis-agent bash
docker exec clawksis-agent readlink /data/current-package
docker exec clawksis-agent cat /data/.container-identity
```

### Force Container Recreation

If you need to reset the writable layer (fresh Ubuntu):

```bash
sudo systemctl stop clawksis-agent
docker rm -f clawksis-agent
sudo rm /var/lib/clawksis/.container-identity
sudo systemctl start clawksis-agent
```

### Verify Secrets Are Loaded

If the agent starts but can't authenticate with the LLM provider, check that the `.env` file was merged correctly:

```bash
# Native mode
sudo -u clawk cat /var/lib/clawksis/.clawksis/.env

# Container mode
docker exec clawksis-agent cat /data/.clawksis/.env
```

### GC Root Verification

```bash
nix-store --query --roots $(docker exec clawksis-agent readlink /data/current-package)
```

### Common Issues

| Symptom | Cause | Fix |
|---|---|---|
| `Cannot save configuration: managed by NixOS` | CLI guards active | Edit `configuration.nix` and `nixos-rebuild switch` |
| `No adapter available for discord` (or telegram/slack) | Messaging deps missing from the sealed Nix venv | Install `#messaging` variant: `nix profile install ...#messaging`. For NixOS module: `extraDependencyGroups = [ "messaging" ]`. Check `journalctl -u clawksis-agent` for `FeatureUnavailable` or `requirements not met` for the underlying error. |
| Container recreated unexpectedly | `extraVolumes`, `extraOptions`, or `image` changed | Expected — writable layer resets. Reinstall packages or use a custom image |
| `clawk version` shows old version | Container not restarted | `systemctl restart clawksis-agent` |
| Permission denied on `/var/lib/clawk` | State dir is `0750 clawk:clawk` | Use `docker exec` or `sudo -u clawk` |
| `nix-collect-garbage` removed clawk | GC root missing | Restart the service (preStart recreates the GC root) |
| `no container with name or ID "clawksis-agent"` (Podman) | Podman rootful container not visible to regular user | Add passwordless sudo for podman (see [Container Mode](#container-mode) section) |
| `unable to find user clawk` | Container still starting (entrypoint hasn't created user yet) | Wait a few seconds and retry — the CLI retries automatically |
| Tool added via `extraPackages` not found in terminal | Requires `nixos-rebuild switch` to update the per-user profile | Rebuild and restart: `nixos-rebuild switch && systemctl restart clawksis-agent` |
