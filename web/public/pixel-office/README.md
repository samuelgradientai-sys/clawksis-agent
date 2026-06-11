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
messages. Two small patches in the upstream source make this work in an iframe:

- `webview-ui/src/vscodeApi.ts` — outbound `postMessage` forwards to the parent
  window (`{__pixelAgentsOut}`) instead of a console no-op.
- `webview-ui/src/browserMock.ts` — signals the host (`{__pixelAgentsReady}`)
  once assets + default layout are loaded.

## Rebuilding

After changing the upstream webview source:

```sh
cd <pixel-agents>/webview-ui && npm install && npx vite build
# bundle lands in <pixel-agents>/dist/webview — copy it here (minus screenshots):
cp -r <pixel-agents>/dist/webview/. web/public/pixel-office/
rm -f web/public/pixel-office/Screenshot*.jpg
```

Do **not** hand-edit files in this directory — they are build output.
