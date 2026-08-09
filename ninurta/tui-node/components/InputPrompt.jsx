// Bottom input prompt — hermes-ink native (no ink-text-input; that package
// binds to plain `ink`'s input system, which never fires under @hermes/ink).
// Chars, backspace, Enter submit, ArrowUp/Down history — all via useInput.

import React, { useState } from 'react'
import { Box, Text, useInput } from '@hermes/ink'
import { ACCENT } from '../lib/palette.js'

const HISTORY_MAX = 50

export default function InputPrompt({ onSubmit, width }) {
  const [value, setValue] = useState('')
  const [history, setHistory] = useState([])
  const [histIdx, setHistIdx] = useState(-1)

  const submit = (text) => {
    const trimmed = text.trim()
    if (trimmed) {
      onSubmit(trimmed)
      setHistory((prev) => [trimmed, ...prev].slice(0, HISTORY_MAX))
    }
    setValue('')
    setHistIdx(-1)
  }

  useInput((input, key) => {
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
    // History navigation
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

  return (
    <Box width={width}>
      <Text bold color={ACCENT}>
        ❯{' '}
      </Text>
      <Text>{value}</Text>
      {/* Blinking-block-style cursor */}
      <Text color={ACCENT}>█</Text>
    </Box>
  )
}
