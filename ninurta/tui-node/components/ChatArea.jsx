// Scrollable chat log area — full width, streaming assistant line.
// Mirrors hermes StreamingAssistant: last turn streams inline.
//
// Multi-line messages (e.g. `/db report 1` structured output) are split on
// `\n` and rendered as one <Text> row PER LINE — a single <Text> child with
// embedded newlines gets merged into one line by the Ink renderer.
//
// The transcript grows unboundedly (every turn appends a user + assistant
// message). To keep the chat area inside the fixed-height frame (and stop the
// inline renderer from overlapping rows when content overflows), only the most
// recent MAX_LINES lines are rendered — a bounded scrollback, like a terminal.

import React from 'react'
import { Box, Text } from '@hermes/ink'
import { ACCENT_LIGHT, PINK, FUCHSIA, TEXT, MUTED, TAGLINE } from '../lib/palette.js'

// Keep the last N rendered lines. Small enough that the chat area almost never
// overflows the frame (the info box already consumes most of the vertical
// space), large enough to show the latest match report + cost table.
const MAX_LINES = 20

// Split on newlines, keep empty lines (blank separators between sections).
const toLines = (text) => (text ?? '').split('\n')

export default function ChatArea({ messages, streaming, step, width }) {
  // Flatten every message into (role, line, isFirst) rows, then append the
  // live streaming lines, then keep only the tail.
  const rows = []
  for (const msg of messages) {
    const lines = toLines(msg.text)
    lines.forEach((line, li) => rows.push({ role: msg.role, line, first: li === 0 }))
  }
  if (streaming) {
    const lines = toLines(streaming)
    lines.forEach((line, li) => rows.push({ role: 'assistant', line, first: li === 0 }))
  }
  const visible = rows.slice(-MAX_LINES)

  return (
    <Box flexDirection="column" width={width}>
      {visible.map((row, i) => {
        if (row.role === 'user') {
          return (
            <Text key={i} color={TEXT} wrap="truncate">
              {row.first && (
                <Text bold color={PINK}>
                  you:{' '}
                </Text>
              )}
              {row.line}
            </Text>
          )
        }
        if (row.role === 'system') {
          return (
            <Text key={i} color={TAGLINE} wrap="truncate">
              {row.first && (
                <Text bold color={TAGLINE}>
                  ⚠{' '}
                </Text>
              )}
              {row.line}
            </Text>
          )
        }
        return (
          <Text key={i} color={TEXT} wrap="truncate">
            {row.first && (
              <Text bold color={FUCHSIA}>
                ninurta:{' '}
              </Text>
            )}
            {row.line}
          </Text>
        )
      })}
      {step && !streaming && (
        <Text color={TAGLINE} italic>
          {step}
        </Text>
      )}
    </Box>
  )
}
