import { contextBridge, ipcRenderer, webUtils } from 'electron'

contextBridge.exposeInMainWorld('clawkDesktop', {
  getConnection: profile => ipcRenderer.invoke('clawk:connection', profile),
  revalidateConnection: () => ipcRenderer.invoke('clawk:connection:revalidate'),
  touchBackend: profile => ipcRenderer.invoke('clawk:backend:touch', profile),
  getGatewayWsUrl: profile => ipcRenderer.invoke('clawk:gateway:ws-url', profile),
  openSessionWindow: (sessionId, opts) => ipcRenderer.invoke('clawk:window:openSession', sessionId, opts),
  openNewSessionWindow: () => ipcRenderer.invoke('clawk:window:openNewSession'),
  petOverlay: {
    // Main renderer → main process: window lifecycle + drag. `request` is
    // `{ bounds, screen }`; resolves with the screen bounds it actually used.
    open: request => ipcRenderer.invoke('clawk:pet-overlay:open', request),
    close: () => ipcRenderer.invoke('clawk:pet-overlay:close'),
    setBounds: bounds => ipcRenderer.send('clawk:pet-overlay:set-bounds', bounds),
    setIgnoreMouse: ignore => ipcRenderer.send('clawk:pet-overlay:ignore-mouse', ignore),
    // Flip the overlay focusable (and focus it) while the composer needs keys.
    setFocusable: focusable => ipcRenderer.send('clawk:pet-overlay:set-focusable', focusable),
    // Main renderer → overlay (forwarded by main): push the latest pet state.
    pushState: payload => ipcRenderer.send('clawk:pet-overlay:state', payload),
    // Overlay → main renderer (forwarded by main): pop back in / composer submit.
    control: payload => ipcRenderer.send('clawk:pet-overlay:control', payload),
    // Overlay subscribes to state pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('clawk:pet-overlay:state', listener)

      return () => ipcRenderer.removeListener('clawk:pet-overlay:state', listener)
    },
    // Main renderer subscribes to overlay control messages.
    onControl: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('clawk:pet-overlay:control', listener)

      return () => ipcRenderer.removeListener('clawk:pet-overlay:control', listener)
    }
  },
  getBootProgress: () => ipcRenderer.invoke('clawk:boot-progress:get'),
  getConnectionConfig: profile => ipcRenderer.invoke('clawk:connection-config:get', profile),
  saveConnectionConfig: payload => ipcRenderer.invoke('clawk:connection-config:save', payload),
  applyConnectionConfig: payload => ipcRenderer.invoke('clawk:connection-config:apply', payload),
  testConnectionConfig: payload => ipcRenderer.invoke('clawk:connection-config:test', payload),
  probeConnectionConfig: remoteUrl => ipcRenderer.invoke('clawk:connection-config:probe', remoteUrl),
  oauthLoginConnectionConfig: remoteUrl => ipcRenderer.invoke('clawk:connection-config:oauth-login', remoteUrl),
  oauthLogoutConnectionConfig: remoteUrl => ipcRenderer.invoke('clawk:connection-config:oauth-logout', remoteUrl),
  // Clawksis Cloud: one portal login powers discovery + silent per-agent sign-in
  // (cloud-auto-discovery Phase 3).
  cloud: {
    status: () => ipcRenderer.invoke('clawk:cloud:status'),
    login: () => ipcRenderer.invoke('clawk:cloud:login'),
    logout: () => ipcRenderer.invoke('clawk:cloud:logout'),
    discover: org => ipcRenderer.invoke('clawk:cloud:discover', org),
    agentSignIn: dashboardUrl => ipcRenderer.invoke('clawk:cloud:agent-sign-in', dashboardUrl)
  },
  profile: {
    get: () => ipcRenderer.invoke('clawk:profile:get'),
    set: name => ipcRenderer.invoke('clawk:profile:set', name)
  },
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
  setNativeTheme: mode => ipcRenderer.send('clawk:native-theme', mode),
  setTranslucency: payload => ipcRenderer.send('clawk:translucency', payload),
  setPreviewShortcutActive: active => ipcRenderer.send('clawk:previewShortcutActive', Boolean(active)),
  openExternal: url => ipcRenderer.invoke('clawk:openExternal', url),
  openPreviewInBrowser: url => ipcRenderer.invoke('clawk:openPreviewInBrowser', url),
  fetchLinkTitle: url => ipcRenderer.invoke('clawk:fetchLinkTitle', url),
  sanitizeWorkspaceCwd: cwd => ipcRenderer.invoke('clawk:workspace:sanitize', cwd),
  settings: {
    getDefaultProjectDir: () => ipcRenderer.invoke('clawk:setting:defaultProjectDir:get'),
    setDefaultProjectDir: dir => ipcRenderer.invoke('clawk:setting:defaultProjectDir:set', dir),
    pickDefaultProjectDir: () => ipcRenderer.invoke('clawk:setting:defaultProjectDir:pick')
  },
  zoom: {
    // Current zoom of this window, as { level, percent }.
    get: () => ipcRenderer.invoke('clawk:zoom:get'),
    setPercent: percent => ipcRenderer.send('clawk:zoom:set-percent', percent),
    // Fires on every zoom change, including the Ctrl/Cmd +/-/0 shortcuts,
    // so the settings UI can stay in sync with the keyboard.
    onChanged: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('clawk:zoom:changed', listener)

      return () => ipcRenderer.removeListener('clawk:zoom:changed', listener)
    }
  },
  revealLogs: () => ipcRenderer.invoke('clawk:logs:reveal'),
  getRecentLogs: () => ipcRenderer.invoke('clawk:logs:recent'),
  readDir: dirPath => ipcRenderer.invoke('clawk:fs:readDir', dirPath),
  gitRoot: startPath => ipcRenderer.invoke('clawk:fs:gitRoot', startPath),
  revealPath: targetPath => ipcRenderer.invoke('clawk:fs:reveal', targetPath),
  openDir: dirPath => ipcRenderer.invoke('clawk:fs:openDir', dirPath),
  renamePath: (targetPath, newName) => ipcRenderer.invoke('clawk:fs:rename', targetPath, newName),
  writeTextFile: (filePath, content) => ipcRenderer.invoke('clawk:fs:writeText', filePath, content),
  trashPath: targetPath => ipcRenderer.invoke('clawk:fs:trash', targetPath),
  git: {
    worktreeList: repoPath => ipcRenderer.invoke('clawk:git:worktreeList', repoPath),
    worktreeAdd: (repoPath, options) => ipcRenderer.invoke('clawk:git:worktreeAdd', repoPath, options),
    worktreeRemove: (repoPath, worktreePath, options) =>
      ipcRenderer.invoke('clawk:git:worktreeRemove', repoPath, worktreePath, options),
    branchSwitch: (repoPath, branch) => ipcRenderer.invoke('clawk:git:branchSwitch', repoPath, branch),
    branchList: repoPath => ipcRenderer.invoke('clawk:git:branchList', repoPath),
    baseBranchList: repoPath => ipcRenderer.invoke('clawk:git:baseBranchList', repoPath),
    repoStatus: repoPath => ipcRenderer.invoke('clawk:git:repoStatus', repoPath),
    fileDiff: (repoPath, filePath) => ipcRenderer.invoke('clawk:git:fileDiff', repoPath, filePath),
    scanRepos: (roots, options) => ipcRenderer.invoke('clawk:git:scanRepos', roots, options),
    review: {
      list: (repoPath, scope, baseRef) => ipcRenderer.invoke('clawk:git:review:list', repoPath, scope, baseRef),
      diff: (repoPath, filePath, scope, baseRef, staged) =>
        ipcRenderer.invoke('clawk:git:review:diff', repoPath, filePath, scope, baseRef, staged),
      stage: (repoPath, filePath) => ipcRenderer.invoke('clawk:git:review:stage', repoPath, filePath),
      unstage: (repoPath, filePath) => ipcRenderer.invoke('clawk:git:review:unstage', repoPath, filePath),
      revert: (repoPath, filePath) => ipcRenderer.invoke('clawk:git:review:revert', repoPath, filePath),
      revParse: (repoPath, ref) => ipcRenderer.invoke('clawk:git:review:revParse', repoPath, ref),
      commit: (repoPath, message, push) => ipcRenderer.invoke('clawk:git:review:commit', repoPath, message, push),
      commitContext: repoPath => ipcRenderer.invoke('clawk:git:review:commitContext', repoPath),
      push: repoPath => ipcRenderer.invoke('clawk:git:review:push', repoPath),
      shipInfo: repoPath => ipcRenderer.invoke('clawk:git:review:shipInfo', repoPath),
      createPr: repoPath => ipcRenderer.invoke('clawk:git:review:createPr', repoPath)
    }
  },
  terminal: {
    cwd: id => ipcRenderer.invoke('clawk:terminal:cwd', id),
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
  onDeepLink: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('clawk:deep-link', listener)

    return () => ipcRenderer.removeListener('clawk:deep-link', listener)
  },
  signalDeepLinkReady: () => ipcRenderer.invoke('clawk:deep-link-ready'),
  onWindowStateChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('clawk:window-state-changed', listener)

    return () => ipcRenderer.removeListener('clawk:window-state-changed', listener)
  },
  onFocusSession: callback => {
    const listener = (_event, sessionId) => callback(sessionId)
    ipcRenderer.on('clawk:focus-session', listener)

    return () => ipcRenderer.removeListener('clawk:focus-session', listener)
  },
  onNotificationAction: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('clawk:notification-action', listener)

    return () => ipcRenderer.removeListener('clawk:notification-action', listener)
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
  // Soft gateway-mode apply finished tearing down the primary backend. Renderer
  // should wipe session lists + re-dial without a window reload.
  onConnectionApplied: callback => {
    const listener = () => callback()
    ipcRenderer.on('clawk:connection:applied', listener)

    return () => ipcRenderer.removeListener('clawk:connection:applied', listener)
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
  // runner in main.ts (apps/desktop/electron/bootstrap-runner.ts).
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
  getRemoteDisplayReason: () => ipcRenderer.invoke('clawk:get-remote-display-reason'),
  uninstall: {
    summary: () => ipcRenderer.invoke('clawk:uninstall:summary'),
    run: mode => ipcRenderer.invoke('clawk:uninstall:run', { mode })
  },
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
  },
  themes: {
    fetchMarketplace: id => ipcRenderer.invoke('clawk:vscode-theme:fetch', id),
    searchMarketplace: query => ipcRenderer.invoke('clawk:vscode-theme:search', query)
  }
})
