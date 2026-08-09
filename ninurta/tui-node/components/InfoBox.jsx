// Bordered info box with bow art (left) + system info (right).
// Spans the FULL terminal width; content clamped defensively on narrow screens.

import React from 'react'
import { Box, Text } from '@hermes/ink'
import { ACCENT, ACCENT_LIGHT, MUTED, TEXT } from '../lib/palette.js'
import { loadBowArt } from '../lib/art.js'

export default function InfoBox({ modelId, cwd, version, width }) {
  const bow = loadBowArt()
  const leftLines = []
  if (bow) {
    leftLines.push(...bow.split('\n'))
  }
  leftLines.push('')
  leftLines.push(`${modelId} · Nous Research`)
  leftLines.push(cwd)
  leftLines.push(`Session: ${version}`)

  const rightLines = []
  rightLines.push(`Ninurta v${version}`)
  rightLines.push('')
  rightLines.push('▼ Pipelines')
  rightLines.push('  extract → extractor')
  rightLines.push('  resume  → reader · validator · reviewer · saver')
  rightLines.push('')
  rightLines.push('▼ Commands')
  rightLines.push('  /extract <url>   run job extraction')
  rightLines.push('  /resume          resume stats from SQLite')
  rightLines.push('  /search <q>      run matching graph')
  rightLines.push('  /clear           reset transcript')
  rightLines.push('  quit / Ctrl+C    exit')

  // Defensive clamp: never exceed the terminal.
  const clamp = (s) => (width && s.length > width - 2 ? s.slice(0, width - 2) : s)

  // The box STRETCHES to the full terminal width; columns keep content size
  // and extra space is absorbed by the row filler.
  const boxW = Math.max(8, width)
  const innerW = boxW - 4
  const gap = 4
  const rightMax = Math.max(4, innerW - gap - 16)
  const rightW = Math.min(Math.max(...rightLines.map((l) => l.length), 0), rightMax)
  const leftW = Math.min(Math.max(...leftLines.map((l) => l.length), 0), innerW - gap - rightW)

  const maxRows = Math.max(leftLines.length, rightLines.length)
  while (leftLines.length < maxRows) leftLines.push('')
  while (rightLines.length < maxRows) rightLines.push('')

  const title = ` NINURTA v${version} `
  const topPad = Math.max(0, boxW - 2 - title.length)

  const bowLineCount = bow ? bow.split('\n').length : 0

  return (
    <Box flexDirection="column" width={boxW}>
      <Text color={ACCENT}>
        {'╭'}{title}{'─'.repeat(topPad)}{'╮'}
      </Text>
      {leftLines.map((_, i) => {
        const lPadded = clamp(leftLines[i]).padEnd(leftW)
        const rPadded = clamp(rightLines[i]).padEnd(rightW)
        const row = `${lPadded}${' '.repeat(gap)}${rPadded}`.padEnd(innerW).slice(0, innerW)
        return (
          <Text key={i} color={i < bowLineCount ? ACCENT_LIGHT : TEXT}>
            {'│ '}{row}{' │'}
          </Text>
        )
      })}
      <Text color={ACCENT}>
        {'╰'}{'─'.repeat(Math.max(0, boxW - 2))}{'╯'}
      </Text>
      <Text> </Text>
      <Text color={MUTED}>
        Type below and press Enter — gateway streams the answer back. quit / Ctrl+C to exit.
      </Text>
      <Text> </Text>
    </Box>
  )
}
