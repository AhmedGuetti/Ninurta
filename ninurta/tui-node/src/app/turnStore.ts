// Ninurta turnStore — mirrors hermes-agent ui-tui/src/app/turnStore.ts (nanostores).
import { atom } from 'nanostores'
import { useSyncExternalStore } from 'react'

export interface Msg {
  role: 'user' | 'assistant' | 'system'
  text: string
}

export interface TurnState {
  messages: Msg[]
  streaming: string
  step: string
  busy: boolean
}

export const $turnState = atom<TurnState>({
  messages: [],
  streaming: '',
  step: '',
  busy: false
})

export const getTurnState = (): TurnState => $turnState.get()

const subscribeTurn = (cb: () => void) => $turnState.listen(() => cb())

/** React binding — same shape as hermes `useTurnSelector`. */
export const useTurnState = (): TurnState =>
  useSyncExternalStore(
    subscribeTurn,
    () => getTurnState(),
    () => getTurnState()
  )

export const patchTurnState = (next: Partial<TurnState>) =>
  $turnState.set({ ...getTurnState(), ...next })

export const addMessage = (msg: Msg) =>
  patchTurnState({ messages: [...getTurnState().messages, msg] })

export const setStep = (step: string) => patchTurnState({ step })

export const appendStream = (text: string) =>
  patchTurnState({ streaming: getTurnState().streaming + text })

export const endTurn = (text?: string, error?: string) => {
  const { streaming } = getTurnState()
  const finalText = error ? `⚠ ${error}` : text ?? streaming
  patchTurnState({
    messages: [...getTurnState().messages, { role: 'assistant', text: finalText }],
    streaming: '',
    step: '',
    busy: false
  })
}

export const clearTurn = () =>
  patchTurnState({ messages: [], streaming: '', step: '', busy: false })
