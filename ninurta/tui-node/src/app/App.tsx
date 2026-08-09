// Ninurta App — Hermes-style full-width INLINE layout (no alternate screen:
// the host terminal's native scrollback and transparency must keep working).
import React, { useCallback, useState } from 'react'
import { Box, Text, useInput, useStdout } from '@hermes/ink'
import { useStore } from '@nanostores/react'

import Banner from '../../components/Banner.jsx'
import InfoBox from '../../components/InfoBox.jsx'
import ChatArea from '../../components/ChatArea.jsx'
import StatusBar from '../../components/StatusBar.jsx'
import InputPrompt from '../../components/InputPrompt.jsx'
import { useMainApp } from './useMainApp.js'
import { $turnState } from './turnStore.js'

const ACCENT = '#d946ef'
const MUTED = '#a78bfa'
const TEXT = '#fdf4ff'

export function App({ modelId, cwd, version }: { modelId: string; cwd: string; version: string }) {
  const { stdout } = useStdout()
  const cols: number = stdout?.columns ?? 80
  const { ready, error, stderrLog, sendMessage, runSlash } = useMainApp()
  const turn = useStore($turnState)
  const [showGatewayLog, setShowGatewayLog] = useState(false)

  // Ctrl+C / Ctrl+D → exit; Ctrl+G → toggle gateway stderr log (hermes pattern).
  useInput((input: string, key: { ctrl?: boolean }) => {
    if (key.ctrl && (input === 'c' || input === 'd')) process.exit(0)
    if (key.ctrl && input === 'g') setShowGatewayLog((v) => !v)
  })

  const handleSubmit = useCallback(
    (text: string) => {
      const low = text.trim().toLowerCase()
      if (['quit', 'exit', 'q', '/exit', '/quit'].includes(low)) {
        process.exit(0)
        return
      }
      if (text.startsWith('/')) {
        const [cmd, ...args] = text.slice(1).split(' ')
        void runSlash(cmd, args)
      } else {
        void sendMessage(text)
      }
    },
    [runSlash, sendMessage]
  )

  // Hermes INLINE_MODE: no AlternateScreen wrapper → native scrollback lives.
  return (
    <Box flexDirection="column" width={cols} flexGrow={1}>
        <Banner width={cols} />
        <InfoBox modelId={modelId} cwd={cwd} version={version} width={cols} />
        <Box flexGrow={1} flexShrink={1} minHeight={2}>
          <ChatArea messages={turn.messages} streaming={turn.streaming} step={turn.step} width={cols} />
        </Box>

        {!ready && !error && (
          <Text color={MUTED} dim>
            connecting to gateway…
          </Text>
        )}
        {error && (
          <Text color="#f87171">
            gateway error: {error} — Ctrl+G to inspect stderr
          </Text>
        )}

        <StatusBar
          modelId={modelId}
          cwd={cwd}
          width={cols}
          ready={ready}
          busy={turn.busy}
          step={turn.step}
        />

        {showGatewayLog && (
          <Box flexDirection="column" borderStyle="round" borderColor={MUTED} width={cols}>
            <Text color={ACCENT} bold>
              gateway stderr (last 200)
            </Text>
            {stderrLog.map((l, i) => (
              <Text key={i} color={MUTED} dim>
                {l}
              </Text>
            ))}
          </Box>
        )}

        <Box width={cols}>
          <InputPrompt onSubmit={handleSubmit} width={cols} />
        </Box>
    </Box>
  )
}
