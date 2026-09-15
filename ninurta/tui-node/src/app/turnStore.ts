// Ninurta turnStore — mirrors hermes-agent ui-tui/src/app/turnStore.ts (nanostores).
import { atom } from 'nanostores'
import type { SlashCompletion } from './slashCommands.js'

export interface Msg {
  role: 'user' | 'assistant' | 'system'
  text: string
}

export interface TurnState {
  messages: Msg[]
  streaming: string
  /** Short step name — which node is running (extractor, matcher, llm, …). */
  step: string
  /** Dynamic one-line description of what's happening right now. */
  stepMsg: string
  busy: boolean
}

export const $turnState = atom<TurnState>({
  messages: [],
  streaming: '',
  step: '',
  stepMsg: '',
  busy: false
})

/** Reactive model ID — updated by /model command, read by StatusBar + InfoBox. */
export const $modelId = atom<string>('gemini-3.6-flash')

// ── Interactive Selector ──────────────────────────────────────────────────────
// Modular: any slash command can populate this atom to show an inline selector.
// The <Selector /> component reads $selector and renders arrow-key navigation.
// When the user picks an item, onSelect fires; Esc / empty callback clears it.

export interface SelectorItem {
  id: string
  label: string
  current?: boolean   // shown as "← current"
}

export interface SelectorState {
  active: boolean
  title: string
  items: SelectorItem[]
  onSelect: (id: string) => void
  onCancel: () => void
}

const EMPTY_SELECTOR: SelectorState = {
  active: false,
  title: '',
  items: [],
  onSelect: () => {},
  onCancel: () => {},
}

export const $selector = atom<SelectorState>(EMPTY_SELECTOR)

/** Activate the selector (clears any previous state first). */
export const activateSelector = (title: string, items: SelectorItem[], onSelect: (id: string) => void, onCancel?: () => void) => {
  $selector.set({ active: true, title, items, onSelect, onCancel: onCancel ?? (() => $selector.set(EMPTY_SELECTOR)) })
}

/** Deactivate the selector (clears back to empty). */
export const clearSelector = () => $selector.set(EMPTY_SELECTOR)

// ── Slash completion ────────────────────────────────────────────────────────
// Live dropdown state for the input prompt: when the user types `/`, the
// InputPrompt computes matching commands (see slashCommands.ts) and publishes
// them here so App.tsx can steer Tab (complete vs. cycle focus) and the
// dropdown row renders above the prompt.

export interface CompletionState {
  /** Set while the slash-completion dropdown is visible. */
  active: boolean
  items: SlashCompletion[]
  /** Currently highlighted row index. */
  idx: number
}

const EMPTY_COMPLETION: CompletionState = { active: false, items: [], idx: 0 }

export const $completion = atom<CompletionState>(EMPTY_COMPLETION)

export const setCompletion = (state: Partial<CompletionState>) =>
  $completion.set({ ...$completion.get(), ...state })

export const clearCompletion = () => $completion.set(EMPTY_COMPLETION)

export const getTurnState = (): TurnState => $turnState.get()

export const patchTurnState = (next: Partial<TurnState>) =>
  $turnState.set({ ...getTurnState(), ...next })

export const addMessage = (msg: Msg) =>
  patchTurnState({ messages: [...getTurnState().messages, msg] })

export const setStep = (step: string, stepMsg = '') =>
  patchTurnState({ step, stepMsg })

export const setBusy = (busy: boolean) => patchTurnState({ busy })

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
