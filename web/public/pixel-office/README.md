# Vendored pixel-agents office

This directory is a **prebuilt** copy of the [pixel-agents](https://github.com/PabloDeLucca/pixel-agents)
webview (MIT, Pablo De Lucca 2026), used by the dashboard **Visualization →
Pixel Office** tab. Character sprites derive from the JIK-A-4 "Metro City" pack
(CC0).

It runs in **browser mode**: `index.html` boots the React webview, `browserMock`
decodes the sprite PNGs and loads the default office layout, then the office
listens for the pixel-agents `postMessage` protocol.

The dashboard embeds it in an iframe and feeds it **real** Clawksis gateway
events: `web/src/visualization/PixelOfficeView.tsx` opens the live event feed
(`/api/events`) and `pixelBridge.ts` translates `tool.start` / `subagent.*` /
`message.*` events into `agentToolStart` / `agentStatus` / `subagentToolStart`
messages. The office visual is also swappable — see
`web/src/visualization/officeProviders.ts` to register another standalone build.

## Patches to upstream

Two iframe-mode patches:

- `webview-ui/src/vscodeApi.ts` — outbound `postMessage` forwards to the parent
  window (`{__pixelAgentsOut}`) instead of a console no-op.
- `webview-ui/src/browserMock.ts` — signals the host (`{__pixelAgentsReady}`)
  once assets + default layout are loaded.

Two rendering enhancements (in `webview-ui/src/office/engine/renderer.ts` +
`webview-ui/src/constants.ts`):

- **Activity labels** — a persistent label above every active character showing
  the tool it's using (`renderActivityLabels`), so the office reads at a glance.
- **Delegation links** — a marching-ants line from each sub-agent to its parent
  (`renderDelegationLines`), so a delegate_task hand-off is visible as a
  connection between the two agents.

Telegram-style activity (the `agentToolStart`/`subagentToolStart` protocol gains
an optional `label` field; emoji choice + Spanish copy live in `pixelBridge.ts`):

- **Emoji activity labels** — the activity label shows the bridge's emoji-prefixed
  text (`Character.currentToolLabel`, e.g. "📖 config.py", "🔎 …", "💻 …"). The raw
  tool name stays on `currentTool` so the read/type animation lookup is unaffected.
- **💭 Thinking bubble** — a floating emoji bubble (`bubbleType: 'thinking'`,
  drawn as a glyph in `renderBubbles`) while the agent reasons before its first
  tool. The bridge synthesizes it on `message.start`.
- **Clawksis tool animations** — `isReadingTool` (in `engine/characters.ts`) now
  recognizes snake_case Clawksis tools (`read_file`, `web_search`, …) so they pick
  the reading pose instead of always typing.
- **Fuel gauge for every agent** — `ToolOverlay.tsx` draws the context gauge for
  any agent with token usage, not only team agents.
- **Sound on by default** — `browserMock.ts` enables the turn-end / permission
  chime (still gated behind the first canvas click for AudioContext unlock).

Plus session identity (in `office/types.ts`, `officeState.addAgent`,
`hooks/useExtensionMessages.ts`, `office/components/ToolOverlay.tsx`):

- **Session name + model** — `Character.model`; the overlay shows the real
  session title (`folderName`) and a model/channel line. A new `agentMeta`
  message ({id, folderName?, model?}) updates them when the session metadata
  resolves after the desk was created.

## Rebuilding

After changing the upstream webview source:

```sh
cd <pixel-agents>/webview-ui && npm install && npx tsc --noEmit && npx vite build
# bundle lands in <pixel-agents>/dist/webview — copy it here (minus screenshots):
cp -r <pixel-agents>/dist/webview/. web/public/pixel-office/
rm -f web/public/pixel-office/Screenshot*.jpg
# (this README is not part of the build — keep it / re-add it after copying)
```

Do **not** hand-edit the JS/CSS/asset files here — they are build output.
