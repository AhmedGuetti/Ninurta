// Scrollable chat log area.
// Renders all messages; scroll offset controlled by PageUp/PageDown.

import React from "react";
import { Box, Text } from "ink";
import { TAGLINE, ACCENT_LIGHT, TEXT } from "../lib/palette.js";

export default function ChatArea({ messages }) {
  if (messages.length === 0) return null;

  return (
    <Box flexDirection="column">
      {messages.map((msg, i) => {
        const isUser = msg.role === "you";
        return (
          <Text key={i} color={isUser ? TAGLINE : ACCENT_LIGHT}>
            {isUser ? (
              <Text bold color={TAGLINE}>you: </Text>
            ) : (
              <Text color={ACCENT_LIGHT}>ninurta: </Text>
            )}
            <Text color={TEXT}>{msg.text}</Text>
          </Text>
        );
      })}
    </Box>
  );
}
