// Ninurta useMainApp — mirrors hermes-agent ui-tui/src/app/useMainApp.ts.
import { useCallback, useEffect, useRef, useState } from 'react'

import { GatewayClient } from '../gateway/gatewayClient.js'
import { addMessage, clearTurn, endTurn, setStep, setBusy, appendStream, getTurnState, $modelId, activateSelector, clearSelector } from './turnStore.js'

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
    gw.on('pipeline.progress', (params: { step: string; message?: string }) => {
      setStep(params?.step ?? 'working…', params?.message ?? '')
    })
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
        // Interactive selector flow:
        //   1. /model → show providers, arrow-key pick
        //   2. pick provider → show its models, arrow-key pick
        //   3. pick model → switch, done
        const gw = gwRef.current
        if (!gw) return

        // Fetch the full provider→models map once
        setStep('reading models…')
        try {
          const list = (await gw.request('model.list', {})) as {
            providers?: Record<string, string[]>
            current_provider?: string
            current_model?: string
          }
          const providers = list?.providers ?? {}
          const curP = list?.current_provider ?? ''
          const curM = list?.current_model ?? ''
          const entries = Object.entries(providers)
          if (entries.length === 0) {
            endTurn('no providers configured — add llm.providers to config.yaml')
            return
          }

          // ── Step 1: pick a provider ──────────────────────────────────
          activateSelector(
            'Pick a provider',
            entries.map(([prov]) => ({
              id: prov,
              label: prov,
              current: prov === curP,
            })),
            // onSelect: user chose a provider → list its models
            (provId: string) => {
              const models = providers[provId] ?? []
              activateSelector(
                `${provId} models`,
                models.map((m) => ({
                  id: m,
                  label: m,
                  current: provId === curP && m === curM,
                })),
                // onSelect: user chose a model → switch
                async (modelId: string) => {
                  clearSelector()
                  setStep('switching model…')
                  try {
                    const res = (await gw.request('model.set', { provider: provId, model: modelId })) as { model?: string }
                    const newModel = res?.model ?? `${provId}:${modelId}`
                    $modelId.set(newModel)
                    endTurn(`switched to ${newModel}`)
                  } catch (e) {
                    endTurn(undefined, e instanceof Error ? e.message : String(e))
                  }
                },
                // onCancel: back to provider selection
                () => {
                  activateSelector(
                    'Pick a provider',
                    entries.map(([prov]) => ({
                      id: prov,
                      label: prov,
                      current: prov === curP,
                    })),
                    (provId2: string) => {
                      const models2 = providers[provId2] ?? []
                      activateSelector(
                        `${provId2} models`,
                        models2.map((m) => ({
                          id: m,
                          label: m,
                          current: provId2 === curP && m === curM,
                        })),
                        async (modelId2: string) => {
                          clearSelector()
                          setStep('switching model…')
                          try {
                            const res2 = (await gw.request('model.set', { provider: provId2, model: modelId2 })) as { model?: string }
                            const newModel2 = res2?.model ?? `${provId2}:${modelId2}`
                            $modelId.set(newModel2)
                            endTurn(`switched to ${newModel2}`)
                          } catch (e2) {
                            endTurn(undefined, e2 instanceof Error ? e2.message : String(e2))
                          }
                        },
                        clearSelector,
                      )
                    },
                    clearSelector,
                  )
                },
              )
            },
            // onCancel: dismiss
            clearSelector,
          )
        } catch (e) {
          endTurn(undefined, e instanceof Error ? e.message : String(e))
        }
        return
      }
      case 'db': {
        // /db                  → summary of all tables
        // /db resumes|jobs|reports → list rows
        // /db resume|job|report <id> → detail for a row
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
        if (['resumes', 'jobs', 'reports'].includes(sub)) {
          setStep(`listing ${sub}…`)
          try {
            const res = (await gw.request('db.inspect', { table: sub })) as { text?: string }
            endTurn(res?.text ?? 'no rows')
          } catch (e) {
            endTurn(undefined, e instanceof Error ? e.message : String(e))
          }
          return
        }
        if (['resume', 'job', 'report'].includes(sub) && idArg) {
          setStep(`fetching ${sub} ${idArg}…`)
          try {
            const res = (await gw.request('db.inspect', { table: sub, id: parseInt(idArg, 10) })) as { text?: string }
            endTurn(res?.text ?? 'not found')
          } catch (e) {
            endTurn(undefined, e instanceof Error ? e.message : String(e))
          }
          return
        }
        addMessage({ role: 'system', text: 'usage: /db | /db resumes|jobs|reports | /db resume|job|report <id>' })
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
