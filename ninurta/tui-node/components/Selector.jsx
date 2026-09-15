// Interactive inline selector — arrow-key navigation, Enter to pick, Esc to cancel.
// Driven entirely by the $selector nanostore atom.  Any slash command can
// populate $selector to show a pick list without coupling to this component.
//
// Renders inline between ChatArea and InputPrompt.  When active, InputPrompt
// receives active=false so all keys route here.

import React, { useState, useEffect } from 'react'
import { Box, Text, useInput } from '@hermes/ink'
import { useStore } from '@nanostores/react'
import { $selector, clearSelector } from '../src/app/turnStore.js'
import { ACCENT, PINK, MUTED, TEXT } from '../lib/palette.js'

export default function Selector({ width }) {
  const sel = useStore($selector)
  const [cursor, setCursor] = useState(0)

  // Reset cursor when items change (new step)
  useEffect(() => {
    setCursor(0)
  }, [sel.items])

  const clamp = (n) => Math.max(0, Math.min(n, sel.items.length - 1))

  useInput((_input, key) => {
    if (key.upArrow)   setCursor((c) => clamp(c - 1))
    if (key.downArrow) setCursor((c) => clamp(c + 1))
    if (key.return) {
      const item = sel.items[cursor]
      if (item) sel.onSelect(item.id)
    }
    if (key.escape) {
      clearSelector()
      sel.onCancel()
    }
  }, { isActive: sel.active && sel.items.length > 0 })

  // Guard: nothing to render when selector is inactive
  if (!sel.active || sel.items.length === 0) return null

  return (
    <Box flexDirection="row" width={width} marginBottom={1}>
      <Text>{'  '}</Text>
      <Box
        flexDirection="column"
        borderStyle="round"
        borderColor={PINK}
        paddingX={1}
        width={Math.min(width - 4, 50)}
      >
        <Box marginBottom={1} borderBottom={false}>
          <Text bold color={PINK}>
            {sel.title}
          </Text>
        </Box>
        {sel.items.map((item, i) => {
          const isFocused = i === cursor
          const suffix = item.current ? ' ← current' : ''
          return (
            <Text key={item.id} color={isFocused ? ACCENT : TEXT} bold={isFocused}>
              {isFocused ? '❯' : ' '} {i + 1}. {item.label}
              <Text color={MUTED}>{suffix}</Text>
            </Text>
          )
        })}
        <Box marginTop={1}>
          <Text color={MUTED} dim>
            ↑↓ navigate · Enter select · Esc cancel
          </Text>
        </Box>
      </Box>
    </Box>
  )
}
