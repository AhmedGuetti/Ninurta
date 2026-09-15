// Bottom input prompt — hermes-ink native (no ink-text-input; that package
// binds to plain `ink`'s input system, which never fires under @hermes/ink).
// Chars, backspace, Enter submit, ArrowUp/Down history — all via useInput.
// `active=false` (Tab focused a section) → input ignores all keys and dims.
//
// SLASH COMPLETION: typing `/` opens a live dropdown above the prompt listing
// every command whose usage matches the typed prefix, with descriptions
// (mirrors hermes-agent's complete.slash UX, but client-side & deterministic —
// Ninurta's command set lives in slashCommands.ts). ↑↓ navigate, Tab accepts
// the highlighted row, Enter accepts-and-submits when the row would change
// the input, Esc dismisses the dropdown.
//
// Cursor: useDeclaredCursor parks the TERMINAL cursor on the input line
// (right after the typed text) so CJK IME preedit and a11y tools work.
// When active=false, the declaration is cleared and the cursor drops to
// wherever Ink places it (no typing in that state anyway).

import React, { useEffect, useMemo, useState } from 'react'
import { Box, Text, useInput, useDeclaredCursor } from '@hermes/ink'
import { ACCENT, MUTED, TEXT } from '../lib/palette.js'
import { completeSlash, applyCompletion } from '../src/app/slashCommands.js'
import { clearCompletion, setCompletion } from '../src/app/turnStore.js'
import RunningLine from './RunningLine.jsx'

const HISTORY_MAX = 50

export default function InputPrompt({ onSubmit, width, active = true, busy = false, step = '', stepMsg = '', modelId = '', selectorActive = false }) {
  const [value, setValue] = useState('')
  const [history, setHistory] = useState([])
  const [histIdx, setHistIdx] = useState(-1)
  const [compIdx, setCompIdx] = useState(0)
  // Esc dismisses the dropdown; suppress stays on until the input changes
  // (otherwise the next render re-publishes the same matches).
  const [suppress, setSuppress] = useState(false)

  const completions = useMemo(() => completeSlash(value), [value])
  const completionActive = active && !busy && !selectorActive && completions.length > 0 && !suppress

  // Fixed-height dropdown window — the window/truncation is now computed in
  // <CompletionOverlay /> (an absolute overlay in App.tsx); InputPrompt only
  // publishes the full match list + highlight index to $completion so the
  // overlay can render it without being in the height-clamped flex flow.
  useEffect(() => {
    if (completionActive) setCompletion({ active: true, items: completions, idx: compIdx })
    else clearCompletion()
  }, [completionActive, completions, compIdx])

  // Reset the highlight + Esc-suppression whenever the input changes.
  useEffect(() => {
    setCompIdx(0)
    setSuppress(false)
  }, [value])

  const accept = (row) => {
    setValue(applyCompletion(value, row.text, 1))
    clearCompletion()
  }

  const submit = (text) => {
    const trimmed = text.trim()
    if (trimmed) {
      onSubmit(trimmed)
      setHistory((prev) => [trimmed, ...prev].slice(0, HISTORY_MAX))
    }
    setValue('')
    setHistIdx(-1)
    setCompIdx(0)
  }

  useInput((input, key) => {
    if (!active) return // focus is on a section header — don't consume keys
    if (busy || selectorActive) return // locked: RunningLine shows, Ctrl+C handled by App

    // ── Completion mode: ↑↓ navigate, Tab accept, Enter accept-or-submit ──
    if (completionActive) {
      if (key.upArrow) {
        setCompIdx((i) => (i - 1 + completions.length) % completions.length)
        return
      }
      if (key.downArrow) {
        setCompIdx((i) => (i + 1) % completions.length)
        return
      }
      if (key.tab) {
        accept(completions[compIdx])
        return
      }
      if (key.escape) {
        clearCompletion()
        setSuppress(true)
        return
      }
      if (key.return) {
        const row = completions[compIdx]
        const next = applyCompletion(value, row.text, 1)
        // Accept only when the row changes the command token (a row that
        // merely appends trailing whitespace is already complete → submit).
        if (next !== value && next.trimEnd() !== value.trimEnd()) {
          accept(row)
        } else {
          submit(value)
        }
        return
      }
      // fall through: typing / backspace / delete keep filtering live
    }

    // Enter → submit
    if (key.return) {
      submit(value)
      return
    }
    // Backspace / Delete → drop last char
    if (key.backspace || key.delete) {
      setValue((prev) => prev.slice(0, -1))
      return
    }
    // History navigation (only when no completion dropdown is up)
    if (key.upArrow) {
      setHistIdx((idx) => {
        const next = Math.min(idx + 1, history.length - 1)
        if (next >= 0) setValue(history[next])
        return next
      })
      return
    }
    if (key.downArrow) {
      setHistIdx((idx) => {
        const next = idx - 1
        if (next < 0) {
          setValue('')
          return -1
        }
        setValue(history[next])
        return next
      })
      return
    }
    // Ignore other special keys; only printable chars append
    if (
      !key.ctrl &&
      !key.meta &&
      !key.tab &&
      !key.leftArrow &&
      !key.rightArrow &&
      !key.pageUp &&
      !key.pageDown &&
      !key.escape
    ) {
      setValue((prev) => prev + input)
    }
  })

  // Park the terminal cursor at the end of the typed text on the input line.
  // `❯ ` is 2 characters wide.
  const setNode = useDeclaredCursor({
    line: 0,
    column: 2 + value.length,
    active: active && !busy && !selectorActive,
  })

  // Selector is up (e.g. /model picker) → the input line is REMOVED entirely.
  if (selectorActive) return null

  // Pipeline is processing → replace the prompt with the live running line.
  // The component stays mounted so input history survives the busy period.
  if (busy) {
    return <RunningLine width={width} step={step} stepMsg={stepMsg} modelId={modelId} />
  }

  // The completion dropdown itself is rendered by <CompletionOverlay /> in
  // App.tsx (absolute overlay) — NOT here. Rendering it in-flow below made it
  // change the frame height inside the anti-scroll clamp and corrupt the
  // layout. This component just publishes $completion and shows the prompt.
  return (
    <Box width={width} ref={setNode}>
      <Text bold color={active ? ACCENT : MUTED}>
        ❯{' '}
      </Text>
      <Text color={active ? TEXT : MUTED}>{value}</Text>
    </Box>
  )
}
