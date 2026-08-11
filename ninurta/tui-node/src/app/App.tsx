// Ninurta App — Hermes-style full-width INLINE layout (no alternate screen:
// the host terminal's native scrollback and transparency must keep working).
import React, { useCallback, useEffect, useState } from 'react'
import { Box, Text, useInput, useStdout } from '@hermes/ink'
import { useStore } from '@nanostores/react'

import Banner from '../../components/Banner.jsx'
import InfoBox from '../../components/InfoBox.jsx'
import ChatArea from '../../components/ChatArea.jsx'
import StatusBar from '../../components/StatusBar.jsx'
import InputPrompt from '../../components/InputPrompt.jsx'
import { useMainApp } from './useMainApp.js'
import { $turnState, $modelId } from './turnStore.js'

const ACCENT = '#d946ef'
const MUTED = '#a78bfa'
const TEXT = '#fdf4ff'

type FocusZone = 'input' | 'pipelines' | 'commands'

export function App({ cwd, version }: { cwd: string; version: string }) {
  const { stdout } = useStdout()
  const cols: number = stdout?.columns ?? 80
  // Tab: cycle focus  input → pipelines → commands → input
  // Enter: toggle focused section (returns focus to input)
  // Esc:   back to input
  // Ctrl+C: cancel running pipeline · Ctrl+D: exit · Ctrl+G: gateway log
  const { ready, error, stderrLog, sendMessage, runSlash, cancel } = useMainApp()
  const turn = useStore($turnState)
  const modelId = useStore($modelId)  // reactive — updated by /model
  const [showGatewayLog, setShowGatewayLog] = useState(false)
  const [focus, setFocus] = useState<FocusZone>('input')
  const [pipesOpen, setPipesOpen] = useState(true)
  const [cmdsOpen, setCmdsOpen] = useState(true)

  // Tab: cycle focus  input → pipelines → commands → input
  // Enter: toggle focused section (returns focus to input)
  // Esc:   back to input
  // Ctrl+C: cancel running pipeline · Ctrl+D: exit · Ctrl+G: gateway log
  useInput((input: string, key: { ctrl?: boolean; tab?: boolean; return?: boolean; escape?: boolean }) => {
    if (key.ctrl && input === 'c') { cancel(); return }
    if (key.ctrl && input === 'd') process.exit(0)
    if (key.ctrl && input === 'g') setShowGatewayLog((v) => !v)
    if (key.tab) {
      setFocus((f) => (f === 'input' ? 'pipelines' : f === 'pipelines' ? 'commands' : 'input'))
      return
    }
    if (key.escape) {
      setFocus('input')
      return
    }
    if (key.return && focus !== 'input') {
      if (focus === 'pipelines') setPipesOpen((v) => !v)
      else setCmdsOpen((v) => !v)
      setFocus('input')
    }
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

  // Update terminal tab / window title based on pipeline state
  useEffect(() => {
    const title = turn.busy ? '⚡ Ninurta — working...' : '⚡ Ninurta'
    process.stdout.write(`\x1b]0;${title}\x07`)
  }, [turn.busy])

  // Hermes INLINE_MODE: no AlternateScreen wrapper → native scrollback lives.
  return (
    <Box flexDirection="column" width={cols} flexGrow={1}>
      <Banner width={cols} />
      <InfoBox
        modelId={modelId}
        cwd={cwd}
        version={version}
        width={cols}
        focus={focus}
        pipesOpen={pipesOpen}
        cmdsOpen={cmdsOpen}
      />
      <Box flexGrow={1} flexShrink={1} minHeight={2}>
        <ChatArea messages={turn.messages} streaming={turn.streaming} step={turn.step} width={cols} />
      </Box>

      {!ready && !error && (
        <Text color={MUTED} dim>
          connecting to gateway…
        </Text>
      )}
      {error && (
        <Text color="#fb7185">
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
        <InputPrompt onSubmit={handleSubmit} width={cols} active={focus === 'input'} />
      </Box>
    </Box>
  )
}
