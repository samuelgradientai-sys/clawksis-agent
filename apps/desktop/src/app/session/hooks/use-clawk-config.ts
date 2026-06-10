import { type MutableRefObject, useCallback, useState } from 'react'



import { getClawksisConfig, getClawksisConfigDefaults } from '@/clawk'

import { BUILTIN_PERSONALITIES, normalizePersonalityValue, personalityNamesFromConfig } from '@/lib/chat-runtime'

import {

  $currentCwd,

  setAvailablePersonalities,

  setCurrentCwd,

  setCurrentFastMode,

  setCurrentPersonality,

  setCurrentReasoningEffort,

  setCurrentServiceTier,

  setIntroPersonality

} from '@/store/session'



const DEFAULT_VOICE_SECONDS = 120

const FAST_TIERS = new Set(['fast', 'priority', 'on'])



function recordingLimit(value: unknown) {

  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : DEFAULT_VOICE_SECONDS

}



interface ClawksisConfigOptions {

  activeSessionIdRef: MutableRefObject<string | null>

  refreshProjectBranch: (cwd: string) => Promise<void>

}



export function useClawksisConfig({ activeSessionIdRef, refreshProjectBranch }: ClawksisConfigOptions) {

  const [voiceMaxRecordingSeconds, setVoiceMaxRecordingSeconds] = useState(DEFAULT_VOICE_SECONDS)

  const [sttEnabled, setSttEnabled] = useState(true)



  const refreshClawksisConfig = useCallback(async () => {

    try {

      const [config, defaults] = await Promise.all([getClawksisConfig(), getClawksisConfigDefaults().catch(() => ({}))])



      const personality = normalizePersonalityValue(

        typeof config.display?.personality === 'string' ? config.display.personality : ''

      )



      setIntroPersonality(personality)

      // Active sessions keep their per-session value; standalone falls back to config.

      setCurrentPersonality(prev => (activeSessionIdRef.current ? prev || personality : personality))

      setAvailablePersonalities([

        ...new Set([

          'none',

          ...BUILTIN_PERSONALITIES,

          ...personalityNamesFromConfig(defaults),

          ...personalityNamesFromConfig(config)

        ])

      ])



      const cwd = (config.terminal?.cwd ?? '').trim()



      if (cwd && cwd !== '.') {

        setCurrentCwd(prev => prev || cwd)

        void refreshProjectBranch($currentCwd.get() || cwd)

      }



      const reasoning = (config.agent?.reasoning_effort ?? '').trim()

      const tier = (config.agent?.service_tier ?? '').trim()



      setCurrentReasoningEffort(prev => (activeSessionIdRef.current ? prev : reasoning))

      setCurrentServiceTier(prev => (activeSessionIdRef.current ? prev : tier))

      setCurrentFastMode(prev => (activeSessionIdRef.current ? prev : FAST_TIERS.has(tier.toLowerCase())))



      setVoiceMaxRecordingSeconds(recordingLimit(config.voice?.max_recording_seconds))

      setSttEnabled(config.stt?.enabled !== false)

    } catch {

      // Config is nice-to-have; chat still works without it.

    }

  }, [activeSessionIdRef, refreshProjectBranch])



  return { refreshClawksisConfig, sttEnabled, voiceMaxRecordingSeconds }

}

