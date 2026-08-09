// Violet-gradient NINURTA banner — full terminal width, art clipped defensively.
// Robust to ANY bow_art.txt content (any width/height) the user edits live.

import React from 'react'
import { Box, Text } from '@hermes/ink'
import { VIOLET_GRADIENT, TAGLINE } from '../lib/palette.js'
import { loadBanner } from '../lib/art.js'

/** @param {{ width?: number }} props terminal columns */
export default function Banner({ width }) {
  const art = loadBanner()
  const lines = art.split('\n')

  return (
    <Box flexDirection="column" width={width}>
      {lines.map((line, i) => {
        const step = Math.min(
          Math.floor((i / Math.max(lines.length, 1)) * VIOLET_GRADIENT.length),
          VIOLET_GRADIENT.length - 1,
        )
        // Defensive clip: never exceed terminal width, never overflow.
        const safe = line.length > width ? line.slice(0, Math.max(width - 1, 1)) : line
        return (
          <Text key={i} bold color={VIOLET_GRADIENT[step]}>
            {safe}
          </Text>
        )
      })}
      <Text bold color={TAGLINE}>
        § Ninurta · God of War and the Hunt — Lord of the Bow
      </Text>
      <Text> </Text>
    </Box>
  )
}
