// Completion dropdown — rendered as an ABSOLUTE overlay anchored to the App
// root, floating just above the input prompt. It must NOT be in the normal
// flex flow: under the anti-scroll `height={rows}` clamp, a conditional
// in-flow dropdown changes the frame height when it opens/closes, and the
// flex layout then miscalculates row positions — dropping items and bleeding
// stale text between rows (e.g. "list all resumes by idounts)").
//
// Anchored with `position="absolute" bottom={1}` relative to the App root
// (the input line is the root's last row), so the popup floats directly above
// the input without shifting anything. hermes-ink clears the absolute node's
// rect before painting, so it overlays the status bar cleanly while open.

import React from 'react'
import { Box, Text } from '@hermes/ink'
import { useStore } from '@nanostores/react'
import { $completion } from '../src/app/turnStore.js'
import { ACCENT, MUTED, TEXT } from '../lib/palette.js'

const COMPLETION_WINDOW = 8

export default function CompletionOverlay({ width }) {
  const { active, items, idx } = useStore($completion)

  if (!active || items.length === 0) return null

  // Same fixed-height window as the input prompt used to render: centered on
  // the highlighted row, never more than COMPLETION_WINDOW rows.
  const windowSize = Math.min(COMPLETION_WINDOW, items.length)
  const start = Math.max(
    0,
    Math.min(idx - Math.floor(COMPLETION_WINDOW / 2), items.length - windowSize)
  )
  const visible = items.slice(start, start + windowSize)

  // Force every row onto ONE line (truncate) so the overlay height is
  // deterministic: windowSize + footer + borders. No wrapping.
  const boxW = Math.min(width - 4, 56)
  const innerW = Math.max(8, boxW - 4) // round border (2) + paddingX=1 (2)
  const nameW = Math.min(Math.max(...visible.map((c) => c.display.length), 0) + 1, 16)
  const metaW = Math.max(0, innerW - 2 - nameW) // "❯ " + name column
  const clipMeta = (m) => (m.length > metaW ? `${m.slice(0, Math.max(0, metaW - 1))}…` : m)

  return (
    <Box position="absolute" bottom={1} left={0} width={width} opaque>
      <Box flexDirection="row" width={width}>
        <Text>{'  '}</Text>
        <Box
          flexDirection="column"
          borderStyle="round"
          borderColor={MUTED}
          paddingX={1}
          width={boxW}
        >
          {visible.map((item, i) => {
            const focused = start + i === idx
            return (
              <Text key={item.display} color={focused ? ACCENT : TEXT} bold={focused} wrap="truncate">
                {focused ? '❯' : ' '} {item.display.padEnd(nameW).slice(0, nameW)}
                <Text color={MUTED} dim={!focused} wrap="truncate">
                  {clipMeta(item.meta)}
                </Text>
              </Text>
            )
          })}
          <Box marginTop={1}>
            <Text color={MUTED} dim>
              ↑↓ navigate · Tab complete · Enter run · Esc dismiss
            </Text>
          </Box>
        </Box>
      </Box>
    </Box>
  )
}
