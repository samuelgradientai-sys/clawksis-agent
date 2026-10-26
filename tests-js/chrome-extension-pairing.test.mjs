// Mi Chrome extension, pure modules: the pairing string the dashboard shows becomes the one
// dashboard the extension may connect to (wss:// unless it is this same machine) plus the
// device token; anything else is refused with a message for the user. Tab facts: browser UI
// pages and the Web Store are never offered to the agent, and only "Clawksis" groups mark
// agent tabs. Manifest: no host permissions, and private windows are never shared.
import fs from 'node:fs'
import { describe, expect, test } from 'vitest'
import {
  PAIRING_PREFIX,
  parsePairing,
  reconnectDelayMs,
  socketUrl,
} from '../apps/chrome-extension/lib/pairing.js'
import { isDebuggableUrl, tabInfo } from '../apps/chrome-extension/lib/tabs.js'

const TOKEN = `mc1.${'A1b2_C3d-'.repeat(5).slice(0, 43)}`

// What clawk_cli/my_chrome_pairing.py:pairing_string produces: unpadded base64url JSON.
const shown = (data) => PAIRING_PREFIX + Buffer.from(JSON.stringify(data)).toString('base64url')

describe('pairing string', () => {
  test('carries the dashboard and the token, and the socket is wss:// on that dashboard', () => {
    const pairing = parsePairing(`  ${shown({ v: 1, u: 'https://vps.tailnet.ts.net/clawk/', t: TOKEN })}\n`)
    expect(pairing).toEqual({ base: 'https://vps.tailnet.ts.net/clawk', token: TOKEN })
    expect(socketUrl(pairing.base)).toBe('wss://vps.tailnet.ts.net/clawk/api/my-chrome/connect')
  })

  test('plain http:// is accepted only for this same machine', () => {
    const local = parsePairing(shown({ v: 1, u: 'http://127.0.0.1:9119', t: TOKEN }))
    expect(socketUrl(local.base)).toBe('ws://127.0.0.1:9119/api/my-chrome/connect')
    expect(() => parsePairing(shown({ v: 1, u: 'http://vps.example:9119', t: TOKEN }))).toThrow(/https/)
    expect(() => parsePairing(shown({ v: 1, u: 'ftp://vps.example', t: TOKEN }))).toThrow(/https/)
  })

  test.each([
    ['not a Mi Chrome code', 'hola'],
    ['truncated', shown({ v: 1, u: 'https://vps.example', t: TOKEN }).slice(0, 30)],
    ['another version', shown({ v: 2, u: 'https://vps.example', t: TOKEN })],
    ['a short token', shown({ v: 1, u: 'https://vps.example', t: 'mc1.short' })],
  ])('refuses %s with a message for the user', (_label, raw) => {
    expect(() => parsePairing(raw)).toThrow(/código|Mi Chrome/)
  })

  test('reconnects back off from 1s to a 30s ceiling', () => {
    expect([0, 1, 2, 5, 50].map(reconnectDelayMs)).toEqual([1000, 2000, 4000, 30000, 30000])
  })
})

describe('manifest', () => {
  test('asks only for what the relay needs and never runs in incognito', () => {
    const manifest = JSON.parse(
      fs.readFileSync(new URL('../apps/chrome-extension/manifest.json', import.meta.url), 'utf8'),
    )
    expect(manifest.manifest_version).toBe(3)
    expect([...manifest.permissions].sort()).toEqual(['alarms', 'debugger', 'storage', 'tabGroups', 'tabs'])
    expect(manifest.host_permissions).toBeUndefined()
    expect(manifest.incognito).toBe('not_allowed')
  })
})

describe('tabs', () => {
  test.each([
    ['https://vuelaya.example/', true],
    ['about:blank', true],
    ['chrome://settings/', false],
    ['edge://settings/', false],
    ['chrome-extension://abc/popup.html', false],
    ['https://chromewebstore.google.com/detail/x', false],
    ['', false],
  ])('%s debuggable: %s', (url, debuggable) => {
    expect(isDebuggableUrl(url)).toBe(debuggable)
  })

  test('only tabs in a Clawksis group are the agent\'s', () => {
    const groups = new Set([9])
    const base = { id: 1, windowId: 1, index: 0, url: 'https://a.example/', title: 'A', active: true }
    expect(tabInfo({ ...base, groupId: 9 }, groups).agent).toBe(true)
    expect(tabInfo({ ...base, groupId: 4 }, groups).agent).toBe(false)
    expect(tabInfo({ ...base, groupId: -1 }, groups).agent).toBe(false)
    expect(tabInfo({ ...base, url: '', pendingUrl: 'https://b.example/' }, groups).url).toBe('https://b.example/')
  })
})
