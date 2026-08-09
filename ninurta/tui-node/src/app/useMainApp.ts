// Ninurta useMainApp — mirrors hermes-agent ui-tui/src/app/useMainApp.ts.
import { useCallback, useEffect, useRef, useState } from 'react'

import { GatewayClient } from '../gateway/gatewayClient.js'
import { addMessage, clearTurn, endTurn, setStep, appendStream, getTurnState } from './turnStore.js'

export interface MainAppApi {
  gateway: GatewayClient
  ready: boolean
  error: string | null
  stderrLog: string[]
  sendMessage: (text: string) => Promise<void>
  runSlash: (cmd: string, args: string[]) => Promise<void>
}

export function useMainApp(): MainAppApi {
  const gwRef = useRef<GatewayClient | null>(null)
  const [ready, setReady] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [, force] = useState(0)

  const stderrLog = gwRef.current?.stderrLog ?? []

  useEffect(() => {
    const gw = new GatewayClient()
    gwRef.current = gw

    // Wire gateway push events into the store (hermes event-dispatcher pattern).
    gw.on('turn.delta', (params: { text?: string }) => {
      if (params?.text) appendStream(params.text)
    })
    gw.on('turn.end', (params: { text?: string; error?: string }) => {
      endTurn(params?.text, params?.error)
    })
    gw.on('pipeline.progress', (params: { step: string }) => {
      setStep(params?.step ?? 'working…')
    })
    gw.on('tool.start', (params: { name: string }) => {
      setStep(`⚙ ${params?.name ?? 'tool'}`)
    })
    gw.on('tool.end', () => setStep(''))

    // Re-render the stderr log pane when new lines arrive (ring buffer).
    gw.on('log', () => force((v) => v + 1))

    gw.start()
    gw.waitReady()
      .then(() => setReady(true))
      .catch((e: Error) => setError(e.message))

    return () => {
      gw.removeAllListeners()
      // Let the child exit via stdin EOF.
      gwRef.current = null
    }
  }, [])

  const sendMessage = useCallback(async (text: string) => {
    const gw = gwRef.current
    if (!gw) return
    addMessage({ role: 'user', text })
    setStep('sending…')
    try {
      await gw.request('session.send', { message: text })
    } catch (e) {
      endTurn(undefined, e instanceof Error ? e.message : String(e))
    }
  }, [])

  const runSlash = useCallback(async (cmd: string, args: string[]) => {
    const gw = gwRef.current
    if (!gw) return
    addMessage({ role: 'user', text: `/${cmd} ${args.join(' ')}`.trim() })

    switch (cmd) {
      case 'clear':
        clearTurn()
        return
      case 'extract': {
        const url = args[0]
        if (!url) {
          addMessage({ role: 'system', text: 'usage: /extract <job-url>' })
          return
        }
        setStep('extracting…')
        try {
          const res = (await gw.request('job.extract', { url })) as { status?: string; url?: string }
          endTurn(`extracted ${res?.url ?? url}`)
        } catch (e) {
          endTurn(undefined, e instanceof Error ? e.message : String(e))
        }
        return
      }
      case 'resume':
        setStep('reading resume…')
        try {
          const res = (await gw.request('resume.stats', {})) as { summary?: string }
          endTurn(res?.summary ?? 'no resume parsed')
        } catch (e) {
          endTurn(undefined, e instanceof Error ? e.message : String(e))
        }
        return
      case 'search':
        setStep('running matching graph…')
        try {
          await gw.request('search.run', { query: args.join(' ') || undefined })
        } catch (e) {
          endTurn(undefined, e instanceof Error ? e.message : String(e))
        }
        return
      default:
        addMessage({ role: 'system', text: `unknown command: /${cmd}` })
    }
  }, [])

  return { gateway: gwRef.current as GatewayClient, ready, error, stderrLog, sendMessage, runSlash }
}
