const { contextBridge, ipcRenderer, webUtils } = require('electron')



contextBridge.exposeInMainWorld('clawkDesktop', {

  getConnection: () => ipcRenderer.invoke('clawk:connection'),

  getGatewayWsUrl: () => ipcRenderer.invoke('clawk:gateway:ws-url'),

  getBootProgress: () => ipcRenderer.invoke('clawk:boot-progress:get'),

  getConnectionConfig: () => ipcRenderer.invoke('clawk:connection-config:get'),

  saveConnectionConfig: payload => ipcRenderer.invoke('clawk:connection-config:save', payload),

  applyConnectionConfig: payload => ipcRenderer.invoke('clawk:connection-config:apply', payload),

  testConnectionConfig: payload => ipcRenderer.invoke('clawk:connection-config:test', payload),

  probeConnectionConfig: remoteUrl => ipcRenderer.invoke('clawk:connection-config:probe', remoteUrl),

  oauthLoginConnectionConfig: remoteUrl => ipcRenderer.invoke('clawk:connection-config:oauth-login', remoteUrl),

  oauthLogoutConnectionConfig: remoteUrl => ipcRenderer.invoke('clawk:connection-config:oauth-logout', remoteUrl),

  api: request => ipcRenderer.invoke('clawk:api', request),

  notify: payload => ipcRenderer.invoke('clawk:notify', payload),

  requestMicrophoneAccess: () => ipcRenderer.invoke('clawk:requestMicrophoneAccess'),

  readFileDataUrl: filePath => ipcRenderer.invoke('clawk:readFileDataUrl', filePath),

  readFileText: filePath => ipcRenderer.invoke('clawk:readFileText', filePath),

  selectPaths: options => ipcRenderer.invoke('clawk:selectPaths', options),

  writeClipboard: text => ipcRenderer.invoke('clawk:writeClipboard', text),

  saveImageFromUrl: url => ipcRenderer.invoke('clawk:saveImageFromUrl', url),

  saveImageBuffer: (data, ext) => ipcRenderer.invoke('clawk:saveImageBuffer', { data, ext }),

  saveClipboardImage: () => ipcRenderer.invoke('clawk:saveClipboardImage'),

  getPathForFile: file => {

    try {

      return webUtils.getPathForFile(file) || ''

    } catch {

      return ''

    }

  },

  normalizePreviewTarget: (target, baseDir) => ipcRenderer.invoke('clawk:normalizePreviewTarget', target, baseDir),

  watchPreviewFile: url => ipcRenderer.invoke('clawk:watchPreviewFile', url),

  stopPreviewFileWatch: id => ipcRenderer.invoke('clawk:stopPreviewFileWatch', id),

  setTitleBarTheme: payload => ipcRenderer.send('clawk:titlebar-theme', payload),

  setPreviewShortcutActive: active => ipcRenderer.send('clawk:previewShortcutActive', Boolean(active)),

  openExternal: url => ipcRenderer.invoke('clawk:openExternal', url),

  fetchLinkTitle: url => ipcRenderer.invoke('clawk:fetchLinkTitle', url),

  settings: {

    getDefaultProjectDir: () => ipcRenderer.invoke('clawk:setting:defaultProjectDir:get'),

    setDefaultProjectDir: dir => ipcRenderer.invoke('clawk:setting:defaultProjectDir:set', dir),

    pickDefaultProjectDir: () => ipcRenderer.invoke('clawk:setting:defaultProjectDir:pick')

  },

  revealLogs: () => ipcRenderer.invoke('clawk:logs:reveal'),

  getRecentLogs: () => ipcRenderer.invoke('clawk:logs:recent'),

  readDir: dirPath => ipcRenderer.invoke('clawk:fs:readDir', dirPath),

  gitRoot: startPath => ipcRenderer.invoke('clawk:fs:gitRoot', startPath),

  terminal: {

    dispose: id => ipcRenderer.invoke('clawk:terminal:dispose', id),

    resize: (id, size) => ipcRenderer.invoke('clawk:terminal:resize', id, size),

    start: options => ipcRenderer.invoke('clawk:terminal:start', options),

    write: (id, data) => ipcRenderer.invoke('clawk:terminal:write', id, data),

    onData: (id, callback) => {

      const channel = `clawk:terminal:${id}:data`

      const listener = (_event, payload) => callback(payload)

      ipcRenderer.on(channel, listener)

      return () => ipcRenderer.removeListener(channel, listener)

    },

    onExit: (id, callback) => {

      const channel = `clawk:terminal:${id}:exit`

      const listener = (_event, payload) => callback(payload)

      ipcRenderer.on(channel, listener)

      return () => ipcRenderer.removeListener(channel, listener)

    }

  },

  onClosePreviewRequested: callback => {

    const listener = () => callback()

    ipcRenderer.on('clawk:close-preview-requested', listener)

    return () => ipcRenderer.removeListener('clawk:close-preview-requested', listener)

  },

  onOpenUpdatesRequested: callback => {

    const listener = () => callback()

    ipcRenderer.on('clawk:open-updates', listener)

    return () => ipcRenderer.removeListener('clawk:open-updates', listener)

  },

  onWindowStateChanged: callback => {

    const listener = (_event, payload) => callback(payload)

    ipcRenderer.on('clawk:window-state-changed', listener)

    return () => ipcRenderer.removeListener('clawk:window-state-changed', listener)

  },

  onPreviewFileChanged: callback => {

    const listener = (_event, payload) => callback(payload)

    ipcRenderer.on('clawk:preview-file-changed', listener)

    return () => ipcRenderer.removeListener('clawk:preview-file-changed', listener)

  },

  onBackendExit: callback => {

    const listener = (_event, payload) => callback(payload)

    ipcRenderer.on('clawk:backend-exit', listener)

    return () => ipcRenderer.removeListener('clawk:backend-exit', listener)

  },

  onPowerResume: callback => {

    const listener = () => callback()

    ipcRenderer.on('clawk:power-resume', listener)

    return () => ipcRenderer.removeListener('clawk:power-resume', listener)

  },

  onBootProgress: callback => {

    const listener = (_event, payload) => callback(payload)

    ipcRenderer.on('clawk:boot-progress', listener)

    return () => ipcRenderer.removeListener('clawk:boot-progress', listener)

  },

  // First-launch bootstrap progress -- emitted by the install.ps1 stage

  // runner in main.cjs (apps/desktop/electron/bootstrap-runner.cjs).

  // Renderer's install overlay subscribes to live events and queries the

  // current snapshot via getBootstrapState() to recover after a devtools

  // reload mid-bootstrap.

  getBootstrapState: () => ipcRenderer.invoke('clawk:bootstrap:get'),

  resetBootstrap: () => ipcRenderer.invoke('clawk:bootstrap:reset'),

  repairBootstrap: () => ipcRenderer.invoke('clawk:bootstrap:repair'),

  cancelBootstrap: () => ipcRenderer.invoke('clawk:bootstrap:cancel'),

  onBootstrapEvent: callback => {

    const listener = (_event, payload) => callback(payload)

    ipcRenderer.on('clawk:bootstrap:event', listener)

    return () => ipcRenderer.removeListener('clawk:bootstrap:event', listener)

  },

  getVersion: () => ipcRenderer.invoke('clawk:version'),

  updates: {

    check: () => ipcRenderer.invoke('clawk:updates:check'),

    apply: opts => ipcRenderer.invoke('clawk:updates:apply', opts),

    getBranch: () => ipcRenderer.invoke('clawk:updates:branch:get'),

    setBranch: name => ipcRenderer.invoke('clawk:updates:branch:set', name),

    onProgress: callback => {

      const listener = (_event, payload) => callback(payload)

      ipcRenderer.on('clawk:updates:progress', listener)

      return () => ipcRenderer.removeListener('clawk:updates:progress', listener)

    }

  }

})

