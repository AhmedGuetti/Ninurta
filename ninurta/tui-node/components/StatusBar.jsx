// Fixed status bar at the bottom — full width, live gateway state, colorful.
// When busy, shows an animated braille spinner + elapsed seconds.

import React, { useEffect, useRef, useState } from 'react'
import { Box, Text } from '@hermes/ink'
import { STATUS_READY, STATUS_BUSY, MUTED, TAGLINE, PINK, TEXT, ACCENT } from '../lib/palette.js'

const SPINNER = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷']
const WORKING_COLOR = '#fbbf24'  // amber-400

export default function StatusBar({ modelId, cwd, width, ready, busy, step, stepMsg }) {
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

  // Compact cwd so the bar stays ONE line at any width: the bar must never
  // wrap (a wrapped 2-row status bar bleeds below the completion overlay and
  // overlaps the input prompt).
  const parts = cwd.split('/').filter(Boolean)
  const shortCwd = parts.length > 2 ? `…/${parts.slice(-2).join('/')}` : cwd

  return (
    <Box width={width}>
      <Text bold color={statusColor}>
        {statusLabel}{' '}
      </Text>
      <Text color={MUTED}>│ </Text>
      <Text color={TAGLINE}>{shortModel}</Text>
      <Text color={MUTED}> │ </Text>
      {busy ? (
        <Text color={PINK} italic>
          {stepMsg || step || 'pipeline running'}
        </Text>
      ) : (
        <Text color={MUTED}>idle</Text>
      )}
      <Text color={MUTED}> │ </Text>
      <Text color={ACCENT}>~</Text>
      <Text color={MUTED}> {shortCwd}</Text>
      <Text> </Text>
      <Text color={MUTED} dim>
        [Tab·Ctrl+C·Ctrl+G]
      </Text>
    </Box>
  )
}
