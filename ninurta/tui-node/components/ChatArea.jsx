// Scrollable chat log area — full width, streaming assistant line.
// Mirrors hermes StreamingAssistant: last turn streams inline.

import React from 'react'
import { Box, Text } from '@hermes/ink'
import { ACCENT_LIGHT, TEXT, MUTED } from '../lib/palette.js'

export default function ChatArea({ messages, streaming, step, width }) {
  return (
    <Box flexDirection="column" width={width}>
      {messages.map((msg, i) => {
        const isUser = msg.role === 'user'
        return (
          <Text key={i} color={isUser ? '#f0abfc' : ACCENT_LIGHT} wrap="wrap">
            {isUser ? (
              <Text bold color="#f0abfc">
                you: {' '}
              </Text>
            ) : (
              <Text color={ACCENT_LIGHT}>
                ninurta: {' '}
              </Text>
            )}
            <Text color={TEXT}>{msg.text}</Text>
          </Text>
        )
      })}
      {streaming && (
        <Text color={ACCENT_LIGHT} wrap="wrap">
          <Text color={ACCENT_LIGHT}>ninurta: </Text>
          <Text color={TEXT}>{streaming}</Text>
        </Text>
      )}
      {step && !streaming && (
        <Text color={MUTED} dim>
          {step}
        </Text>
      )}
    </Box>
  )
}
