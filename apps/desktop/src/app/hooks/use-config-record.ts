import { useQuery } from '@tanstack/react-query'

import { getClawksisConfigRecord } from '@/clawk'
import { queryClient, writeCache } from '@/lib/query-client'
import type { ClawksisConfigRecord } from '@/types/clawk'

// One shared cache for the whole profile config record (`GET /api/config`).
// Every settings surface (MCP, model, config) reads and writes through this key
// so a save in one shows in the others, and revisiting a tab paints the cache
// instead of blanking on a fresh fetch.
//
// Distinct from session/hooks/use-clawk-config.ts, which is side-effecting —
// it pushes personality/cwd/voice/… into the session stores for live chat.
export const CLAWK_CONFIG_KEY = ['clawk-config-record'] as const

// staleTime 0 → serve cache instantly, background-revalidate on every mount.
export const useClawksisConfigRecord = () =>
  useQuery({ queryKey: CLAWK_CONFIG_KEY, queryFn: getClawksisConfigRecord, staleTime: 0 })

export const setClawksisConfigCache = writeCache<ClawksisConfigRecord>(CLAWK_CONFIG_KEY)

export const invalidateClawksisConfig = () => queryClient.invalidateQueries({ queryKey: CLAWK_CONFIG_KEY })
