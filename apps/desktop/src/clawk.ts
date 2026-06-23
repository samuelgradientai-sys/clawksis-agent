import { JsonRpcGatewayClient } from '@clawk/shared'



import type {

  ActionResponse,

  ActionStatusResponse,

  AnalyticsResponse,

  AudioSpeakResponse,

  AudioTranscriptionResponse,

  AuxiliaryModelsResponse,

  BackendUpdateCheckResponse,

  ConfigSchemaResponse,

  CronJob,

  CronJobCreatePayload,

  CronJobUpdates,

  ElevenLabsVoicesResponse,

  EnvVarInfo,

  ClawksisConfig,

  ClawksisConfigRecord,

  LogsResponse,

  MessagingPlatformsResponse,

  MessagingPlatformTestResponse,

  MessagingPlatformUpdate,

  ModelAssignmentRequest,

  ModelAssignmentResponse,

  ModelInfoResponse,

  ModelOptionsResponse,

  OAuthPollResponse,

  OAuthProvidersResponse,

  OAuthStartResponse,

  OAuthSubmitResponse,

  PaginatedSessions,

  ProfileCreatePayload,

  ProfileSetupCommand,

  ProfileSoul,

  ProfilesResponse,

  SessionInfo,

  SessionMessagesResponse,

  SessionSearchResponse,

  SkillInfo,

  StatusResponse,

  ToolsetConfig,

  ToolsetInfo

} from '@/types/clawk'



const DEFAULT_GATEWAY_REQUEST_TIMEOUT_MS = 30_000



export type {

  ActionResponse,

  ActionStatusResponse,

  AnalyticsDailyEntry,

  AnalyticsModelEntry,

  AnalyticsResponse,

  AnalyticsSkillEntry,

  AnalyticsSkillsSummary,

  AnalyticsTotals,

  AudioSpeakResponse,

  AudioTranscriptionResponse,

  AuxiliaryModelsResponse,

  ConfigFieldSchema,

  ConfigSchemaResponse,

  CronJob,

  CronJobCreatePayload,

  CronJobSchedule,

  CronJobUpdates,

  ElevenLabsVoice,

  ElevenLabsVoicesResponse,

  EnvVarInfo,

  GatewayReadyPayload,

  ClawksisConfig,

  ClawksisConfigRecord,

  LogsResponse,

  MessagingEnvVarInfo,

  MessagingHomeChannel,

  MessagingPlatformInfo,

  MessagingPlatformsResponse,

  MessagingPlatformTestResponse,

  MessagingPlatformUpdate,

  ModelAssignmentRequest,

  ModelAssignmentResponse,

  ModelInfoResponse,

  ModelOptionProvider,

  ModelOptionsResponse,

  PaginatedSessions,

  ProfileCreatePayload,

  ProfileInfo,

  ProfileSetupCommand,

  ProfileSoul,

  ProfilesResponse,

  RpcEvent,

  SessionCreateResponse,

  SessionInfo,

  SessionMessage,

  SessionMessagesResponse,

  SessionResumeResponse,

  SessionRuntimeInfo,

  SessionSearchResponse,

  SessionSearchResult,

  SkillInfo,

  StaleAuxAssignment,

  StatusResponse,

  ToolsetConfig,

  ToolsetInfo

} from '@/types/clawk'



export class ClawksisGateway extends JsonRpcGatewayClient {

  constructor() {

    super({

      closedErrorMessage: 'Clawksis gateway connection closed',

      connectErrorMessage: 'Could not connect to Clawksis gateway',

      createRequestId: nextId => nextId,

      notConnectedErrorMessage: 'Clawksis gateway is not connected',

      requestTimeoutMs: DEFAULT_GATEWAY_REQUEST_TIMEOUT_MS

    })

  }

}



// The profile whose backend profile-scoped REST calls should target by default,
// set from `$activeGatewayProfile`. Empty string / "default" means the primary
// (window) backend. Kept here so the gateway swap can re-point settings reads
// without each call site threading the profile through.
let _apiRequestProfile = ''

export function setApiRequestProfile(profile: string | null): void {
  _apiRequestProfile = (profile ?? '').trim()
}

export function getApiRequestProfile(): string {
  return _apiRequestProfile
}



export async function listSessions(

  limit = 40,

  minMessages = 0,

  archived: 'exclude' | 'include' | 'only' = 'exclude',

  order: 'created' | 'recent' = 'recent'

): Promise<PaginatedSessions> {

  const result = await window.clawkDesktop.api<PaginatedSessions>({

    path: `/api/sessions?limit=${limit}&offset=0&min_messages=${Math.max(0, minMessages)}&archived=${archived}&order=${order}`,

    timeoutMs: 60_000

  })



  return {

    ...result,

    sessions: result.sessions.slice(0, limit),

    offset: 0

  }

}



// Cross-profile session list, served by the primary backend's aggregator. The
// extra optional `profile`/`options` args let the sidebar scope a fetch to one
// profile and/or filter by message source without changing the simpler call
// sites (the test's `listAllProfileSessions(50, 1)`, the pickers' three-arg
// form). Like `listSessions`, it uses a longer timeout because aggregating
// every profile's recent sessions is heavier than a single-profile read.
export interface ListProfileSessionsOptions {
  /** Restrict to a single message source (e.g. 'cron', a platform name). */
  source?: string
  /** Drop these message sources from the result (e.g. messaging platforms). */
  excludeSources?: readonly string[]
}

export async function listAllProfileSessions(
  limit = 40,
  minMessages = 0,
  archived: 'exclude' | 'include' | 'only' = 'exclude',
  order: 'created' | 'recent' = 'recent',
  profile = 'all',
  options: ListProfileSessionsOptions = {}
): Promise<PaginatedSessions> {
  const query = new URLSearchParams({
    limit: String(limit),
    offset: '0',
    min_messages: String(Math.max(0, minMessages)),
    archived,
    order,
    profile
  })

  if (options.source) {
    query.set('source', options.source)
  }

  if (options.excludeSources && options.excludeSources.length > 0) {
    query.set('exclude_sources', options.excludeSources.join(','))
  }

  const result = await window.clawkDesktop.api<PaginatedSessions>({
    path: `/api/profiles/sessions?${query.toString()}`,
    timeoutMs: 60_000
  })

  return {
    ...result,
    sessions: result.sessions.slice(0, limit),
    offset: 0
  }
}



export function setSessionArchived(
  id: string,
  archived: boolean,
  profile?: string | null
): Promise<{ ok: boolean }> {

  return window.clawkDesktop.api<{ ok: boolean }>({

    path: `/api/sessions/${encodeURIComponent(id)}`,

    method: 'PATCH',

    body: { archived },

    ...(profile ? { profile } : {})

  })

}



export function searchSessions(query: string): Promise<SessionSearchResponse> {

  return window.clawkDesktop.api<SessionSearchResponse>({

    path: `/api/sessions/search?q=${encodeURIComponent(query)}`

  })

}



export function getSessionMessages(id: string, profile?: string | null): Promise<SessionMessagesResponse> {

  const suffix = profile ? `?profile=${encodeURIComponent(profile)}` : ''

  return window.clawkDesktop.api<SessionMessagesResponse>({

    path: `/api/sessions/${encodeURIComponent(id)}/messages${suffix}`,

    ...(profile ? { profile } : {})

  })

}



// Single-session lookup by id. Used to resolve a session that isn't in the
// sidebar's recent window (e.g. a deep-linked id, a cron run) — mirrors
// `getSessionMessages`'s profile routing so a cross-profile id resolves against
// the owning profile's backend.
export function getSession(id: string, profile?: string | null): Promise<SessionInfo> {

  const suffix = profile ? `?profile=${encodeURIComponent(profile)}` : ''

  return window.clawkDesktop.api<SessionInfo>({

    path: `/api/sessions/${encodeURIComponent(id)}${suffix}`,

    ...(profile ? { profile } : {})

  })

}



export function deleteSession(id: string, profile?: string | null): Promise<{ ok: boolean }> {

  return window.clawkDesktop.api<{ ok: boolean }>({

    path: `/api/sessions/${encodeURIComponent(id)}`,

    method: 'DELETE',

    ...(profile ? { profile } : {})

  })

}



export function renameSession(
  id: string,
  title: string,
  profile?: string | null
): Promise<{ ok: boolean; title: string }> {

  return window.clawkDesktop.api<{ ok: boolean; title: string }>({

    path: `/api/sessions/${encodeURIComponent(id)}`,

    method: 'PATCH',

    body: { title },

    ...(profile ? { profile } : {})

  })

}



export function getGlobalModelInfo(): Promise<ModelInfoResponse> {

  return window.clawkDesktop.api<ModelInfoResponse>({

    path: '/api/model/info'

  })

}



export function getStatus(): Promise<StatusResponse> {

  return window.clawkDesktop.api<StatusResponse>({

    path: '/api/status'

  })

}



export function getLogs(params: {

  component?: string

  file?: string

  level?: string

  lines?: number

}): Promise<LogsResponse> {

  const query = new URLSearchParams()



  if (params.file) {

    query.set('file', params.file)

  }



  if (typeof params.lines === 'number') {

    query.set('lines', String(params.lines))

  }



  if (params.level && params.level !== 'ALL') {

    query.set('level', params.level)

  }



  if (params.component && params.component !== 'all') {

    query.set('component', params.component)

  }



  const suffix = query.toString()



  return window.clawkDesktop.api<LogsResponse>({

    path: suffix ? `/api/logs?${suffix}` : '/api/logs'

  })

}



export function getClawksisConfig(): Promise<ClawksisConfig> {

  return window.clawkDesktop.api<ClawksisConfig>({

    path: '/api/config'

  })

}



export function getClawksisConfigRecord(): Promise<ClawksisConfigRecord> {

  return window.clawkDesktop.api<ClawksisConfigRecord>({

    path: '/api/config'

  })

}



export function getClawksisConfigDefaults(): Promise<ClawksisConfigRecord> {

  return window.clawkDesktop.api<ClawksisConfigRecord>({

    path: '/api/config/defaults'

  })

}



export function getClawksisConfigSchema(): Promise<ConfigSchemaResponse> {

  return window.clawkDesktop.api<ConfigSchemaResponse>({

    path: '/api/config/schema'

  })

}



export function saveClawksisConfig(config: ClawksisConfigRecord): Promise<{ ok: boolean }> {

  return window.clawkDesktop.api<{ ok: boolean }>({

    path: '/api/config',

    method: 'PUT',

    body: { config }

  })

}



export function getEnvVars(): Promise<Record<string, EnvVarInfo>> {

  return window.clawkDesktop.api<Record<string, EnvVarInfo>>({

    path: '/api/env'

  })

}



export function setEnvVar(key: string, value: string): Promise<{ ok: boolean }> {

  return window.clawkDesktop.api<{ ok: boolean }>({

    path: '/api/env',

    method: 'PUT',

    body: { key, value }

  })

}



export function validateProviderCredential(

  key: string,

  value: string,

  apiKey?: string

): Promise<{ ok: boolean; reachable: boolean; message: string; models?: string[] }> {

  return window.clawkDesktop.api<{ ok: boolean; reachable: boolean; message: string; models?: string[] }>({

    path: '/api/providers/validate',

    method: 'POST',

    body: { key, value, ...(apiKey ? { api_key: apiKey } : {}) }

  })

}



export function deleteEnvVar(key: string): Promise<{ ok: boolean }> {

  return window.clawkDesktop.api<{ ok: boolean }>({

    path: '/api/env',

    method: 'DELETE',

    body: { key }

  })

}



export function revealEnvVar(key: string): Promise<{ key: string; value: string }> {

  return window.clawkDesktop.api<{ key: string; value: string }>({

    path: '/api/env/reveal',

    method: 'POST',

    body: { key }

  })

}



export function listOAuthProviders(): Promise<OAuthProvidersResponse> {

  return window.clawkDesktop.api<OAuthProvidersResponse>({

    path: '/api/providers/oauth'

  })

}



export function startOAuthLogin(providerId: string): Promise<OAuthStartResponse> {

  return window.clawkDesktop.api<OAuthStartResponse>({

    path: `/api/providers/oauth/${encodeURIComponent(providerId)}/start`,

    method: 'POST',

    body: {}

  })

}



export function submitOAuthCode(providerId: string, sessionId: string, code: string): Promise<OAuthSubmitResponse> {

  return window.clawkDesktop.api<OAuthSubmitResponse>({

    path: `/api/providers/oauth/${encodeURIComponent(providerId)}/submit`,

    method: 'POST',

    body: { session_id: sessionId, code }

  })

}



export function pollOAuthSession(providerId: string, sessionId: string): Promise<OAuthPollResponse> {

  return window.clawkDesktop.api<OAuthPollResponse>({

    path: `/api/providers/oauth/${encodeURIComponent(providerId)}/poll/${encodeURIComponent(sessionId)}`

  })

}



export function cancelOAuthSession(sessionId: string): Promise<{ ok: boolean }> {

  return window.clawkDesktop.api<{ ok: boolean }>({

    path: `/api/providers/oauth/sessions/${encodeURIComponent(sessionId)}`,

    method: 'DELETE'

  })

}



// Forget a connected OAuth account (clears its stored tokens). Mirrors the
// CLI's "remove account" — the provider settings page calls it then refetches
// the provider list to drop the now-disconnected row.
export function disconnectOAuthProvider(providerId: string): Promise<{ ok: boolean; provider: string }> {

  return window.clawkDesktop.api<{ ok: boolean; provider: string }>({

    path: `/api/providers/oauth/${encodeURIComponent(providerId)}`,

    method: 'DELETE'

  })

}



export function getSkills(): Promise<SkillInfo[]> {

  return window.clawkDesktop.api<SkillInfo[]>({

    path: '/api/skills'

  })

}



export function toggleSkill(name: string, enabled: boolean): Promise<{ ok: boolean; name: string; enabled: boolean }> {

  return window.clawkDesktop.api<{ ok: boolean; name: string; enabled: boolean }>({

    path: '/api/skills/toggle',

    method: 'PUT',

    body: { name, enabled }

  })

}



export function getToolsets(): Promise<ToolsetInfo[]> {

  return window.clawkDesktop.api<ToolsetInfo[]>({

    path: '/api/tools/toolsets'

  })

}



export function toggleToolset(

  name: string,

  enabled: boolean

): Promise<{ ok: boolean; name: string; enabled: boolean }> {

  return window.clawkDesktop.api<{ ok: boolean; name: string; enabled: boolean }>({

    path: `/api/tools/toolsets/${encodeURIComponent(name)}`,

    method: 'PUT',

    body: { enabled }

  })

}



export function getToolsetConfig(name: string): Promise<ToolsetConfig> {

  return window.clawkDesktop.api<ToolsetConfig>({

    path: `/api/tools/toolsets/${encodeURIComponent(name)}/config`

  })

}



export function selectToolsetProvider(

  name: string,

  provider: string

): Promise<{ ok: boolean; name: string; provider: string }> {

  return window.clawkDesktop.api<{ ok: boolean; name: string; provider: string }>({

    path: `/api/tools/toolsets/${encodeURIComponent(name)}/provider`,

    method: 'PUT',

    body: { provider }

  })

}



// Spawn a toolset provider's post-setup install hook (npm / pip / binary) as a
// background action, returning the spawned action's handle. `ok:false` means
// the spawn itself failed (unknown key, server-side launch error) — the caller
// then skips polling. The returned `name` is the action id to tail via
// `getActionStatus`; `key` echoes the post-setup hook that ran.
export function runToolsetPostSetup(
  name: string,
  key: string
): Promise<{ ok: boolean; pid: number; name: string; key?: string }> {

  return window.clawkDesktop.api<{ ok: boolean; pid: number; name: string; key?: string }>({

    path: `/api/tools/toolsets/${encodeURIComponent(name)}/post-setup`,

    method: 'POST',

    body: { key }

  })

}



export function getMessagingPlatforms(): Promise<MessagingPlatformsResponse> {

  return window.clawkDesktop.api<MessagingPlatformsResponse>({

    path: '/api/messaging/platforms'

  })

}



export function updateMessagingPlatform(

  platformId: string,

  body: MessagingPlatformUpdate

): Promise<{ ok: boolean; platform: string }> {

  return window.clawkDesktop.api<{ ok: boolean; platform: string }>({

    path: `/api/messaging/platforms/${encodeURIComponent(platformId)}`,

    method: 'PUT',

    body

  })

}



export function testMessagingPlatform(platformId: string): Promise<MessagingPlatformTestResponse> {

  return window.clawkDesktop.api<MessagingPlatformTestResponse>({

    path: `/api/messaging/platforms/${encodeURIComponent(platformId)}/test`,

    method: 'POST'

  })

}



export function getCronJobs(): Promise<CronJob[]> {

  return window.clawkDesktop.api<CronJob[]>({

    path: '/api/cron/jobs'

  })

}



export function getCronJob(jobId: string): Promise<CronJob> {

  return window.clawkDesktop.api<CronJob>({

    path: `/api/cron/jobs/${encodeURIComponent(jobId)}`

  })

}



// Recent run sessions for a cron job, newest first. Each run is a normal
// session (the agent's execution of that scheduled prompt), so the result is a
// `SessionInfo[]` the run lists can render with the same row components as the
// sidebar. `limit` caps how many the peek lists pull.
export function getCronJobRuns(jobId: string, limit?: number): Promise<SessionInfo[]> {

  const suffix = typeof limit === 'number' ? `?limit=${Math.max(1, Math.floor(limit))}` : ''

  return window.clawkDesktop.api<SessionInfo[]>({

    path: `/api/cron/jobs/${encodeURIComponent(jobId)}/runs${suffix}`

  })

}



export function createCronJob(body: CronJobCreatePayload): Promise<CronJob> {

  return window.clawkDesktop.api<CronJob>({

    path: '/api/cron/jobs',

    method: 'POST',

    body

  })

}



export function updateCronJob(jobId: string, updates: CronJobUpdates): Promise<CronJob> {

  return window.clawkDesktop.api<CronJob>({

    path: `/api/cron/jobs/${encodeURIComponent(jobId)}`,

    method: 'PUT',

    body: { updates }

  })

}



export function pauseCronJob(jobId: string): Promise<CronJob> {

  return window.clawkDesktop.api<CronJob>({

    path: `/api/cron/jobs/${encodeURIComponent(jobId)}/pause`,

    method: 'POST'

  })

}



export function resumeCronJob(jobId: string): Promise<CronJob> {

  return window.clawkDesktop.api<CronJob>({

    path: `/api/cron/jobs/${encodeURIComponent(jobId)}/resume`,

    method: 'POST'

  })

}



export function triggerCronJob(jobId: string): Promise<CronJob> {

  return window.clawkDesktop.api<CronJob>({

    path: `/api/cron/jobs/${encodeURIComponent(jobId)}/trigger`,

    method: 'POST'

  })

}



export function deleteCronJob(jobId: string): Promise<{ ok: boolean }> {

  return window.clawkDesktop.api<{ ok: boolean }>({

    path: `/api/cron/jobs/${encodeURIComponent(jobId)}`,

    method: 'DELETE'

  })

}



export function getProfiles(): Promise<ProfilesResponse> {

  return window.clawkDesktop.api<ProfilesResponse>({

    path: '/api/profiles'

  })

}



export function createProfile(body: ProfileCreatePayload): Promise<{ name: string; ok: boolean; path: string }> {

  return window.clawkDesktop.api<{ name: string; ok: boolean; path: string }>({

    path: '/api/profiles',

    method: 'POST',

    body

  })

}



export function renameProfile(name: string, newName: string): Promise<{ name: string; ok: boolean; path: string }> {

  return window.clawkDesktop.api<{ name: string; ok: boolean; path: string }>({

    path: `/api/profiles/${encodeURIComponent(name)}`,

    method: 'PATCH',

    body: { new_name: newName }

  })

}



export function deleteProfile(name: string): Promise<{ ok: boolean; path: string }> {

  return window.clawkDesktop.api<{ ok: boolean; path: string }>({

    path: `/api/profiles/${encodeURIComponent(name)}`,

    method: 'DELETE'

  })

}



export function getProfileSoul(name: string): Promise<ProfileSoul> {

  return window.clawkDesktop.api<ProfileSoul>({

    path: `/api/profiles/${encodeURIComponent(name)}/soul`

  })

}



export function updateProfileSoul(name: string, content: string): Promise<{ ok: boolean }> {

  return window.clawkDesktop.api<{ ok: boolean }>({

    path: `/api/profiles/${encodeURIComponent(name)}/soul`,

    method: 'PUT',

    body: { content }

  })

}



export function getProfileSetupCommand(name: string): Promise<ProfileSetupCommand> {

  return window.clawkDesktop.api<ProfileSetupCommand>({

    path: `/api/profiles/${encodeURIComponent(name)}/setup-command`

  })

}



export function getUsageAnalytics(days = 30): Promise<AnalyticsResponse> {

  return window.clawkDesktop.api<AnalyticsResponse>({

    path: `/api/analytics/usage?days=${Math.max(1, Math.floor(days))}`

  })

}



export function getGlobalModelOptions(): Promise<ModelOptionsResponse> {

  return window.clawkDesktop.api<ModelOptionsResponse>({

    path: '/api/model/options'

  })

}



export interface RecommendedDefaultModel {

  provider: string

  model: string

  /** True/false for Nous (free vs paid tier); null for other providers. */

  free_tier: boolean | null

}



// Recommended default model for a freshly-authenticated provider. Mirrors the

// curation `clawk model` does — for Nous it honors the free/paid tier so a

// free user gets a free model instead of a paid default.

export function getRecommendedDefaultModel(provider: string): Promise<RecommendedDefaultModel> {

  return window.clawkDesktop.api<RecommendedDefaultModel>({

    path: `/api/model/recommended-default?provider=${encodeURIComponent(provider)}`

  })

}



export function setGlobalModel(

  provider: string,

  model: string

): Promise<{ ok: boolean; provider: string; model: string }> {

  return window.clawkDesktop.api<{ ok: boolean; provider: string; model: string }>({

    path: '/api/model/set',

    method: 'POST',

    body: {

      scope: 'main',

      provider,

      model

    }

  })

}



export function getAuxiliaryModels(): Promise<AuxiliaryModelsResponse> {

  return window.clawkDesktop.api<AuxiliaryModelsResponse>({

    path: '/api/model/auxiliary'

  })

}



export function setModelAssignment(body: ModelAssignmentRequest): Promise<ModelAssignmentResponse> {

  return window.clawkDesktop.api<ModelAssignmentResponse>({

    path: '/api/model/set',

    method: 'POST',

    body

  })

}



export function restartGateway(): Promise<ActionResponse> {

  return window.clawkDesktop.api<ActionResponse>({

    path: '/api/gateway/restart',

    method: 'POST'

  })

}



export function updateClawksis(): Promise<ActionResponse> {

  return window.clawkDesktop.api<ActionResponse>({

    path: '/api/clawksis/update',

    method: 'POST'

  })

}



// The backend's own update state (install method, distance from upstream,
// whether it can self-apply). Drives the remote update overlay so the *backend*
// version — not the Electron client clone — decides "what's changed + Install"
// in remote mode. `refresh` forces a fresh upstream check instead of a cached
// answer.
export function checkClawksisUpdate(refresh?: boolean): Promise<BackendUpdateCheckResponse> {

  const suffix = refresh ? '?refresh=1' : ''

  return window.clawkDesktop.api<BackendUpdateCheckResponse>({

    path: `/api/clawksis/update/check${suffix}`

  })

}



export function getActionStatus(name: string, lines = 200): Promise<ActionStatusResponse> {

  return window.clawkDesktop.api<ActionStatusResponse>({

    path: `/api/actions/${encodeURIComponent(name)}/status?lines=${Math.max(1, lines)}`

  })

}



export function transcribeAudio(dataUrl: string, mimeType?: string): Promise<AudioTranscriptionResponse> {

  return window.clawkDesktop.api<AudioTranscriptionResponse>({

    path: '/api/audio/transcribe',

    method: 'POST',

    body: {

      data_url: dataUrl,

      mime_type: mimeType

    }

  })

}



export function speakText(text: string): Promise<AudioSpeakResponse> {

  return window.clawkDesktop.api<AudioSpeakResponse>({

    path: '/api/audio/speak',

    method: 'POST',

    body: { text }

  })

}



export function getElevenLabsVoices(): Promise<ElevenLabsVoicesResponse> {

  return window.clawkDesktop.api<ElevenLabsVoicesResponse>({

    path: '/api/audio/elevenlabs/voices'

  })

}

