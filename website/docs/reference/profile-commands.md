---

sidebar_position: 7

---



# Profile Commands Reference



This page covers all commands related to [Clawksis profiles](../user-guide/profiles.md). For general CLI commands, see [CLI Commands Reference](./cli-commands.md).



## `clawk profile`



```bash

clawk profile <subcommand>

```



Top-level command for managing profiles. Running `clawk profile` without a subcommand shows help.



| Subcommand | Description |

|------------|-------------|

| `list` | List all profiles. |

| `use` | Set the active (default) profile. |

| `create` | Create a new profile. |

| `delete` | Delete a profile. |

| `show` | Show details about a profile. |

| `alias` | Regenerate the shell alias for a profile. |

| `rename` | Rename a profile. |

| `export` | Export a profile to a tar.gz archive. |

| `import` | Import a profile from a tar.gz archive. |

| `install` | Install a profile distribution from a git URL or local directory. See [Profile Distributions](../user-guide/profile-distributions.md). |

| `update` | Re-pull a distribution-managed profile and re-apply its bundle. |

| `info` | Show distribution metadata for a profile (origin URL, commit, last update). |



## `clawk profile list`



```bash

clawk profile list

```



Lists all profiles. The currently active profile is marked with `*`.



**Example:**



```bash

$ clawk profile list

  default

* work

  dev

  personal

```



No options.



## `clawk profile use`



```bash

clawk profile use <name>

```



Sets `<name>` as the active profile. All subsequent `clawk` commands (without `-p`) will use this profile.



| Argument | Description |

|----------|-------------|

| `<name>` | Profile name to activate. Use `default` to return to the base profile. |



**Example:**



```bash

clawk profile use work

clawk profile use default

```



## `clawk profile create`



```bash

clawk profile create <name> [options]

```



Creates a new profile.



| Argument / Option | Description |

|-------------------|-------------|

| `<name>` | Name for the new profile. Must be a valid directory name (alphanumeric, hyphens, underscores). |

| `--clone` | Copy `config.yaml`, `.env`, and `SOUL.md` from the current profile. |

| `--clone-all` | Copy everything (config, memories, skills, sessions, state) from the current profile. |

| `--clone-from <profile>` | Clone from a specific profile instead of the current one. Used with `--clone` or `--clone-all`. |

| `--no-alias` | Skip wrapper script creation. |

| `--description "<text>"` | One- or two-sentence description of what this profile is good at. Used by the kanban orchestrator to route tasks based on role instead of profile name alone. Skip and add later via `clawk profile describe`. Persisted in `<profile_dir>/profile.yaml`. |

| `--no-skills` | Create an **empty** profile with zero bundled skills enabled. Writes a `.no-bundled-skills` marker into the profile so future `clawk update` runs won't re-seed the bundled set, and refuses to combine with `--clone` / `--clone-all` (which would copy skills in anyway). Useful for narrow orchestrator profiles or sandbox profiles that should not inherit the full skill catalog. To toggle this on an already-created profile (including the default `~/.clawksis`), use `clawk skills opt-out` / `clawk skills opt-in`. |



Creating a profile does **not** make that profile directory the default project/workspace directory for terminal commands. If you want a profile to start in a specific project, set `terminal.cwd` in that profile's `config.yaml`.



**Examples:**



```bash

# Blank profile — needs full setup

clawk profile create mybot



# Clone config only from current profile

clawk profile create work --clone



# Clone everything from current profile

clawk profile create backup --clone-all



# Clone config from a specific profile

clawk profile create work2 --clone --clone-from work

```



## `clawk profile describe`



```bash

clawk profile describe [<name>] [options]

```



Read or set a profile's description. The description is consumed by the kanban orchestrator to route tasks based on what each profile is good at, rather than guessing from the profile name alone. Persisted in `<profile_dir>/profile.yaml` so it survives reboots and is shared with the gateway.



With no flags, prints the current description (or `(no description set for '<name>')` if empty).



| Argument / Option | Description |

|-------------------|-------------|

| `<name>` | Profile to describe. Required unless `--all --auto` is used. |

| `--text "<text>"` | Set the description to this exact text (user-authored). Overwrites any existing description. |

| `--auto` | Auto-generate a 1-2 sentence description via the auxiliary LLM, based on the profile's installed skills, configured model, and name. Configure the model under `auxiliary.profile_describer` in `config.yaml`. Auto-generated descriptions are marked `description_auto: true` so the dashboard can flag them for review. |

| `--overwrite` | With `--auto`, replace user-authored descriptions too (default: skip profiles whose description was set explicitly). |

| `--all` | With `--auto`, sweep every profile missing a description. |



**Examples:**



```bash

# Read the current description

clawk profile describe researcher



# Set it explicitly

clawk profile describe researcher --text "Reads source code and writes findings."



# Let the LLM generate one

clawk profile describe researcher --auto



# Fill in descriptions for every profile that doesn't have one

clawk profile describe --all --auto

```



## `clawk profile delete`



```bash

clawk profile delete <name> [options]

```



Deletes a profile and removes its shell alias.



| Argument / Option | Description |

|-------------------|-------------|

| `<name>` | Profile to delete. |

| `--yes`, `-y` | Skip confirmation prompt. |



**Example:**



```bash

clawk profile delete mybot

clawk profile delete mybot --yes

```



:::warning

This permanently deletes the profile's entire directory including all config, memories, sessions, and skills. Cannot delete the currently active profile.

:::



## `clawk profile show`



```bash

clawk profile show <name>

```



Displays details about a profile including its home directory, configured model, gateway status, skills count, and configuration file status.



This shows the profile's Clawksis home directory, not the terminal working directory. Terminal commands start from `terminal.cwd` (or the launch directory on the local backend when `cwd: "."`).



| Argument | Description |

|----------|-------------|

| `<name>` | Profile to inspect. |



**Example:**



```bash

$ clawk profile show work

Profile: work

Path:    ~/.clawksis/profiles/work

Model:   anthropic/claude-sonnet-4 (anthropic)

Gateway: stopped

Skills:  12

.env:    exists

SOUL.md: exists

Alias:   ~/.local/bin/work

```



## `clawk profile alias`



```bash

clawk profile alias <name> [options]

```



Regenerates the shell alias script at `~/.local/bin/<name>`. Useful if the alias was accidentally deleted or if you need to update it after moving your Clawksis installation.



| Argument / Option | Description |

|-------------------|-------------|

| `<name>` | Profile to create/update the alias for. |

| `--remove` | Remove the wrapper script instead of creating it. |

| `--name <alias>` | Custom alias name (default: profile name). |



**Example:**



```bash

clawk profile alias work

# Creates/updates ~/.local/bin/work



clawk profile alias work --name mywork

# Creates ~/.local/bin/mywork



clawk profile alias work --remove

# Removes the wrapper script

```



## `clawk profile rename`



```bash

clawk profile rename <old-name> <new-name>

```



Renames a profile. Updates the directory and shell alias.



| Argument | Description |

|----------|-------------|

| `<old-name>` | Current profile name. |

| `<new-name>` | New profile name. |



**Example:**



```bash

clawk profile rename mybot assistant

# ~/.clawksis/profiles/mybot → ~/.clawksis/profiles/assistant

# ~/.local/bin/mybot → ~/.local/bin/assistant

```



## `clawk profile export`



```bash

clawk profile export <name> [options]

```



Exports a profile as a compressed tar.gz archive.



| Argument / Option | Description |

|-------------------|-------------|

| `<name>` | Profile to export. |

| `-o`, `--output <path>` | Output file path (default: `<name>.tar.gz`). |



**Example:**



```bash

clawk profile export work

# Creates work.tar.gz in the current directory



clawk profile export work -o ./work-2026-03-29.tar.gz

```



## `clawk profile import`



```bash

clawk profile import <archive> [options]

```



Imports a profile from a tar.gz archive.



| Argument / Option | Description |

|-------------------|-------------|

| `<archive>` | Path to the tar.gz archive to import. |

| `--name <name>` | Name for the imported profile (default: inferred from archive). |



**Example:**



```bash

clawk profile import ./work-2026-03-29.tar.gz

# Infers profile name from the archive



clawk profile import ./work-2026-03-29.tar.gz --name work-restored

```



## Distribution commands



:::tip

**New to distributions?** Start with the [Profile Distributions user guide](../user-guide/profile-distributions.md) — it covers the why, when, and how with full examples. The sections below are a dry CLI reference for when you know what you want.

:::



Distributions turn a profile into a shareable, versioned artifact published

as a **git repository**. A recipient installs the distribution with a single

command and can update it in place later without touching their local

memories, sessions, or credentials.



`auth.json` and `.env` are never part of a distribution — they stay on the

installing user's machine.



The recipient's user data (memories, sessions, auth, their own edits to

`.env`) is always preserved across the initial install and subsequent

updates.



:::info

`clawk profile export` / `import` are still the right commands for

**local backup and restore** of a profile on your own machine. Distribution

(`install` / `update` / `info`) is a separate concept: ship a profile via

git so someone else can install it.

:::



### `clawk profile install`



```bash

clawk profile install <source> [--name <name>] [--alias] [--force] [--yes]

```



Installs a profile distribution from a git URL or a local directory.



| Option | Description |

|--------|-------------|

| `<source>` | Git URL (`github.com/user/repo`, `https://...`, `git@...`, `ssh://`, `git://`) or a local directory containing `distribution.yaml` at its root. |

| `--name NAME` | Override the profile name from the manifest. |

| `--alias` | Also create a shell wrapper (e.g. `telemetry` → `clawk -p telemetry`). |

| `--force` | Overwrite an existing profile of the same name. User data is still preserved. |

| `-y`, `--yes` | Skip the manifest-preview confirmation prompt. |



The installer shows the manifest, lists required env vars, and warns about

cron jobs before asking for confirmation. Required env vars go into a

`.env.EXAMPLE` file you copy to `.env` and fill in.



**Examples:**



```bash

# Install from a GitHub repo (shorthand)

clawk profile install github.com/kyle/telemetry-distribution --alias



# Install from a full HTTPS git URL

clawk profile install https://github.com/kyle/telemetry-distribution.git



# Install from SSH

clawk profile install git@github.com:kyle/telemetry-distribution.git



# Install from a local directory during development

clawk profile install ./telemetry/

```



### `clawk profile update`



```bash

clawk profile update <name> [--force-config] [--yes]

```



Re-clones the distribution from its recorded source and applies updates.

Distribution-owned files (SOUL.md, skills/, cron/, mcp.json) are

overwritten; user data (memories, sessions, auth, .env) is never touched.



`config.yaml` is preserved by default to keep your local overrides.

Pass `--force-config` to reset it to the distribution's shipped config.



### `clawk profile info`



```bash

clawk profile info <name>

```



Prints the profile's distribution manifest — name, version, required

Clawksis version, author, env var requirements, the source URL/path, and

the `Installed:` timestamp recorded when the distribution was last

`install`-ed or `update`-d. Useful for checking what a shared profile

needs before installing it, and for spotting "this profile was installed

6 months ago and hasn't been updated."



`clawk profile list` also shows the distribution name and version in a

`Distribution` column, and `clawk profile show <name>` / `delete <name>`

surface the source URL so you can tell at a glance which profiles came

from a git repo vs. were created locally.



### Private distributions



A private git repository works as a distribution source with no extra

configuration — the install shells out to your normal `git` binary, so

whatever authentication your shell is already set up for (SSH key,

`git credential` helper, GitHub CLI's stored HTTPS credentials) applies

transparently.



```bash

# Uses your SSH key, the same as any other `git clone`

clawk profile install git@github.com:your-org/internal-assistant.git



# Uses your git credential helper

clawk profile install https://github.com/your-org/internal-assistant.git

```



If a clone prompts for credentials interactively in your terminal during

install, that prompt flows through. Set up your auth the way you'd

normally use `git clone` against the same repo first, then install.



### Distribution manifest (`distribution.yaml`)



Every distribution has a `distribution.yaml` at the root of its repository:



```yaml

name: telemetry

version: 0.1.0

description: "Compliance monitoring harness"

clawk_requires: ">=0.12.0"

author: "Your Name"

license: "MIT"

env_requires:

  - name: OPENAI_API_KEY

    description: "OpenAI API key"

    required: true

  - name: GRAPHITI_MCP_URL

    description: "Memory graph URL"

    required: false

    default: "http://127.0.0.1:8000/sse"

distribution_owned:   # optional; defaults to SOUL.md, config.yaml,

                      #   mcp.json, skills/, cron/, distribution.yaml

  - SOUL.md

  - skills/compliance/

  - cron/

```



`clawk_requires` supports `>=`, `<=`, `==`, `!=`, `>`, `<`, or a bare

version (treated as `>=`). Install fails with a clear error if the current

Clawksis version doesn't satisfy the spec.



`distribution_owned` is optional. If set, only those paths are replaced on

update; anything else in the profile stays user-owned. If omitted, the

defaults above apply.



### Publishing a distribution



Authoring a distribution is just a git push:



1. In your profile directory, create `distribution.yaml` with at least `name`

   and `version`.

2. Initialize a git repo (or use an existing one) and push to GitHub /

   GitLab / any host Clawksis can clone from.

3. Tell recipients to run `clawk profile install <your-repo-url>`.



Use git tags for versioned releases — recipients who clone `HEAD` get your

latest state, and you can always bump `version:` in the manifest.



## `clawk -p` / `clawk --profile`



```bash

clawk -p <name> <command> [options]

clawk --profile <name> <command> [options]

```



Global flag to run any Clawksis command under a specific profile without changing the sticky default. This overrides the active profile for the duration of the command.



| Option | Description |

|--------|-------------|

| `-p <name>`, `--profile <name>` | Profile to use for this command. |



**Examples:**



```bash

clawk -p work chat -q "Check the server status"

clawk --profile dev gateway start

clawk -p personal skills list

clawk -p work config edit

```



## `clawk completion`



```bash

clawk completion <shell>

```



Generates shell completion scripts. Includes completions for profile names and profile subcommands.



| Argument | Description |

|----------|-------------|

| `<shell>` | Shell to generate completions for: `bash`, `zsh`, or `fish`. |



**Examples:**



```bash

# Install completions

clawk completion bash >> ~/.bashrc

clawk completion zsh >> ~/.zshrc

clawk completion fish > ~/.config/fish/completions/clawk.fish



# Reload shell

source ~/.bashrc

```



After installation, tab completion works for:

- `clawk profile <TAB>` — subcommands (list, use, create, etc.)

- `clawk profile use <TAB>` — profile names

- `clawk -p <TAB>` — profile names



## See also



- [Profiles User Guide](../user-guide/profiles.md)

- [CLI Commands Reference](./cli-commands.md)

- [FAQ — Profiles section](./faq.md#profiles)

