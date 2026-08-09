// Fixed status bar at the bottom — full width, live gateway state.

import React from 'react'
import { Box, Text } from '@hermes/ink'
import { STATUS_READY, MUTED } from '../lib/palette.js'

export default function StatusBar({ modelId, cwd, width, ready, busy, step }) {
  const shortModel = modelId.replace('gemini:', '')
  const status = ready ? (busy ? 'busy' : 'ready') : 'connecting…'
  return (
    <Box width={width}>
      <Text bold color={ready ? STATUS_READY : MUTED}>
        – {status}{' '}
      </Text>
      <Text color={MUTED}>| {shortModel} | {step || 'idle'} | voice off | 1 session</Text>
      <Text> </Text>
      <Text color={MUTED}>~ {cwd}</Text>
      <Text> </Text>
      <Text color={MUTED} dim>
        [Ctrl+G: gateway log]
      </Text>
    </Box>
  )
}
