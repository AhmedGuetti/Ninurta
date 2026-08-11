// Fixed status bar at the bottom — full width, live gateway state, colorful.
// When busy, shows an animated braille spinner + elapsed seconds.

import React, { useEffect, useRef, useState } from 'react'
import { Box, Text } from '@hermes/ink'
import { STATUS_READY, STATUS_BUSY, MUTED, TAGLINE, PINK, TEXT, ACCENT } from '../lib/palette.js'

const SPINNER = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷']
const WORKING_COLOR = '#fbbf24'  // amber-400

export default function StatusBar({ modelId, cwd, width, ready, busy, step }) {
  const shortModel = modelId.replace('gemini:', '')
  const statusColor = !ready ? MUTED : busy ? WORKING_COLOR : STATUS_READY

  // Spinner + elapsed clock — only ticks while busy
  const [frame, setFrame]     = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const startRef              = useRef(null)

  useEffect(() => {
    if (!busy) {
      startRef.current = null
      setElapsed(0)
      setFrame(0)
      return
    }
    // Record start time on first busy frame
    if (!startRef.current) startRef.current = Date.now()
    const id = setInterval(() => {
      setFrame(f => (f + 1) % SPINNER.length)
      setElapsed(Math.floor((Date.now() - startRef.current) / 1000))
    }, 100)
    return () => clearInterval(id)
  }, [busy])

  const statusLabel = !ready
    ? 'connecting'
    : busy
      ? `${SPINNER[frame]} working... ${elapsed}s`
      : '● ready'

  return (
    <Box width={width}>
      <Text bold color={statusColor}>
        {statusLabel}{' '}
      </Text>
      <Text color={MUTED}>│ </Text>
      <Text color={TAGLINE}>{shortModel}</Text>
      <Text color={MUTED}> │ </Text>
      {step && busy ? (
        <Text color={PINK} italic>
          {step}
        </Text>
      ) : (
        <Text color={MUTED}>{busy ? 'pipeline running' : 'idle'}</Text>
      )}
      <Text color={MUTED}> │ </Text>
      <Text color={ACCENT}>~</Text>
      <Text color={MUTED}> {cwd}</Text>
      <Text> </Text>
      <Text color={MUTED} dim>
        [Tab: sections · Ctrl+G: log]
      </Text>
    </Box>
  )
}
