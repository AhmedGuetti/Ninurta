// Bordered info box: bow art (left) + system info (right).
// Pipelines / Commands sections are expandable — Tab focuses them, Enter toggles.
// Spans the FULL terminal width; content clamped defensively on narrow screens.

import React from 'react'
import { Box, Text } from '@hermes/ink'
import {
  ACCENT, ACCENT_LIGHT, PINK, FUCHSIA, MUTED, TEXT, TAGLINE,
} from '../lib/palette.js'
import { loadBowArt } from '../lib/art.js'
import { SLASH_COMMANDS } from '../src/app/slashCommands.js'

export default function InfoBox({
  modelId, cwd, version, width,
  focus, pipesOpen, cmdsOpen,
}) {
  const bow = loadBowArt()

  // ── Left column: bow art + identity ────────────────────────────────────
  const left = [
    ...(bow ? bow.split('\n').map((l) => ({ text: l, color: ACCENT_LIGHT })) : []),
    { text: '', color: TEXT },
    { text: `${modelId} · Nous Research`, color: PINK, bold: true },
    { text: cwd, color: TEXT },
    { text: `Session: ${version}`, color: MUTED },
  ]

  // ── Right column: pipelines + commands (expandable) ────────────────────
  const sectionHeader = (title, open, focused) => ({
    text: `${open ? '▼' : '▶'} ${title}`,
    color: focused ? TAGLINE : PINK,
    bold: true,
  })

  const right = [
    { text: `Ninurta v${version}`, color: FUCHSIA, bold: true },
    { text: '', color: TEXT },
    sectionHeader('Pipelines', pipesOpen, focus === 'pipelines'),
    ...(pipesOpen
      ? [
          { text: '  extract → extractor', color: TEXT },
          { text: '  resume  → reader · validator · reviewer · saver', color: TEXT },
          { text: '  match   → extractor · matcher (score resume vs JD)', color: TEXT },
        ]
      : []),
    { text: '', color: TEXT },
    sectionHeader('Commands', cmdsOpen, focus === 'commands'),
    ...(cmdsOpen
      ? [
          { text: '  paste a JD   → extract + load resume + score', color: TEXT },
          // Derive from the same registry the completion dropdown uses —
          // help text and autocomplete can never drift apart.
          ...SLASH_COMMANDS.map((c) => ({
            text: `  ${c.usage.padEnd(16)}${c.description}`,
            color: TEXT,
          })),
          { text: '  Ctrl+C cancel · Ctrl+D quit', color: TEXT },
        ]
      : []),
  ]

  // ── Geometry: box stretches to full width, columns keep content size ───
  const clamp = (s) => (width && s.length > width - 2 ? s.slice(0, width - 2) : s)
  const boxW = Math.max(8, width)
  const innerW = boxW - 4
  const gap = 4
  const rightW = Math.min(Math.max(...right.map((r) => r.text.length), 0), Math.max(4, innerW - gap - 16))
  const leftW = Math.min(Math.max(...left.map((r) => r.text.length), 0), Math.max(4, innerW - gap - rightW))
  const filler = Math.max(0, innerW - leftW - gap - rightW)

  const maxRows = Math.max(left.length, right.length)
  while (left.length < maxRows) left.push({ text: '', color: TEXT })
  while (right.length < maxRows) right.push({ text: '', color: TEXT })

  const title = ` NINURTA v${version} `
  const topPad = Math.max(0, boxW - 2 - title.length)

  return (
    <Box flexDirection="column" width={boxW}>
      <Text color={ACCENT}>
        {'╭'}{title}{'─'.repeat(topPad)}{'╮'}
      </Text>

      {left.map((l, i) => (
        <Box key={i} flexDirection="row" width={boxW}>
          <Text color={ACCENT}>│ </Text>
          <Text color={l.color} bold={l.bold}>
            {clamp(l.text).padEnd(leftW)}
          </Text>
          <Text>{' '.repeat(gap)}</Text>
          <Text color={right[i].color} bold={right[i].bold}>
            {clamp(right[i].text).padEnd(rightW)}
          </Text>
          <Text>{' '.repeat(filler)}</Text>
          <Text color={ACCENT}> │</Text>
        </Box>
      ))}

      <Text color={ACCENT}>
        {'╰'}{'─'.repeat(Math.max(0, boxW - 2))}{'╯'}
      </Text>
      <Text> </Text>
      <Text color={MUTED}>
        Tab: focus sections · Enter: toggle · type & Enter: send · Ctrl+D: quit
      </Text>
      <Text> </Text>
    </Box>
  )
}
