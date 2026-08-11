// Ninurta useMainApp — mirrors hermes-agent ui-tui/src/app/useMainApp.ts.
import { useCallback, useEffect, useRef, useState } from 'react'

import { GatewayClient } from '../gateway/gatewayClient.js'
import { addMessage, clearTurn, endTurn, setStep, setBusy, appendStream, getTurnState, $modelId } from './turnStore.js'

export interface MainAppApi {
  gateway: GatewayClient
  ready: boolean
  error: string | null
  stderrLog: string[]
  sendMessage: (text: string) => Promise<void>
  runSlash: (cmd: string, args: string[]) => Promise<void>
  cancel: () => void
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
    setBusy(true)
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
      case 'model': {
        // /model                → show current model
        // /model <model-id>     → switch model (e.g. /model gemini-3.6-flash)
        // /model <provider:name> → switch provider + model
        const modelId = args[0]
        if (!modelId) {
          setStep('reading model…')
          try {
            const res = (await gw.request('model.get', {})) as { full?: string }
            endTurn(res?.full ?? 'unknown model')
          } catch (e) {
            endTurn(undefined, e instanceof Error ? e.message : String(e))
          }
          return
        }
        setStep('switching model…')
        try {
          const res = (await gw.request('model.set', { model_id: modelId })) as { model?: string; status?: string }
          const newModel = res?.model ?? modelId
          $modelId.set(newModel)  // update status bar + info box reactively
          endTurn(`model switched to ${newModel}`)
        } catch (e) {
          endTurn(undefined, e instanceof Error ? e.message : String(e))
        }
        return
      }
      case 'db': {
        // /db                  → summary of all tables
        // /db resumes          → list resumes
        // /db jobs             → list jobs
        // /db resume <id>      → detail for resume row
        // /db job <id>         → detail for job row
        const sub = args[0]
        if (!sub) {
          setStep('reading db…')
          try {
            const res = (await gw.request('db.inspect', {})) as { text?: string }
            endTurn(res?.text ?? 'db empty')
          } catch (e) {
            endTurn(undefined, e instanceof Error ? e.message : String(e))
          }
          return
        }
        const idArg = args[1]
        if (sub === 'resumes' || sub === 'jobs') {
          setStep(`listing ${sub}…`)
          try {
            const res = (await gw.request('db.inspect', { table: sub })) as { text?: string }
            endTurn(res?.text ?? 'no rows')
          } catch (e) {
            endTurn(undefined, e instanceof Error ? e.message : String(e))
          }
          return
        }
        if ((sub === 'resume' || sub === 'job') && idArg) {
          setStep(`fetching ${sub} ${idArg}…`)
          try {
            const res = (await gw.request('db.inspect', { table: sub, id: parseInt(idArg, 10) })) as { text?: string }
            endTurn(res?.text ?? 'not found')
          } catch (e) {
            endTurn(undefined, e instanceof Error ? e.message : String(e))
          }
          return
        }
        addMessage({ role: 'system', text: 'usage: /db | /db resumes|jobs | /db resume|job <id>' })
        return
      }
      default:
        addMessage({ role: 'system', text: `unknown command: /${cmd}` })
    }
  }, [])

  const cancel = useCallback(() => {
    const gw = gwRef.current
    if (!gw) return
    setStep('cancelling…')
    void gw.request('pipeline.cancel', {}).catch(() => {})
  }, [])

  return { gateway: gwRef.current as GatewayClient, ready, error, stderrLog, sendMessage, runSlash, cancel }
}
