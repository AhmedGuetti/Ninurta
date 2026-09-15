// Running line — replaces the input prompt while a pipeline is processing.
// Shows WHAT is running (node step) + a dynamic one-line description of what
// the LLM is doing right now (reasoning… / response received), with an
// animated braille spinner and a "Ctrl+C to stop" hint.  The input is locked:
// keys are ignored until the turn ends.

import React, { useEffect, useState } from 'react'
import { Box, Text } from '@hermes/ink'
import { ACCENT, MUTED, PINK, TEXT, TAGLINE } from '../lib/palette.js'

const SPINNER = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷']

// Node step → human label (shown before the dynamic message).
const STEP_LABELS = {
  extractor: 'extracting JD',
  dedup: 'dedup check',
  loading_resume: 'loading resume',
  matcher: 'scoring match',
  llm: 'LLM',
  completed: 'done',
  sending: 'sending',
}

export default function RunningLine({ width, step, stepMsg, modelId }) {
  const [frame, setFrame] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setFrame((f) => (f + 1) % SPINNER.length), 120)
    return () => clearInterval(id)
  }, [])

  const label = STEP_LABELS[step] ?? (step || 'working')
  const desc = stepMsg || 'working…'

  return (
    <Box width={width}>
      <Text bold color={ACCENT}>
        {SPINNER[frame]}{' '}
      </Text>
      <Text bold color={PINK}>
        {label}
      </Text>
      <Text color={TEXT}> · </Text>
      <Text color={TEXT} italic>
        {desc}
      </Text>
      <Text color={MUTED}> │ </Text>
      <Text color={TAGLINE}>{modelId}</Text>
      <Text color={MUTED}> │ </Text>
      <Text color={MUTED} dim>
        Ctrl+C to stop
      </Text>
    </Box>
  )
}
