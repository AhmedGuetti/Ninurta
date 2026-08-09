// Bottom input prompt with ❯ prefix.
// Manages its own text buffer via useInput hook.

import React, { useState } from "react";
import { Box, Text } from "ink";
import { useInput } from "ink";
import { ACCENT, TEXT } from "../lib/palette.js";

export default function InputPrompt({ onSubmit }) {
  const [value, setValue] = useState("");

  useInput((input, key) => {
    if (key.return) {
      const text = value.trim();
      if (text) onSubmit(text);
      setValue("");
      return;
    }
    if (key.backspace || key.delete) {
      setValue((prev) => prev.slice(0, -1));
      return;
    }
    // Ignore other special keys, only handle printable input
    if (
      !key.ctrl &&
      !key.meta &&
      !key.tab &&
      !key.upArrow &&
      !key.downArrow &&
      !key.leftArrow &&
      !key.rightArrow &&
      !key.pageUp &&
      !key.pageDown &&
      !key.escape
    ) {
      setValue((prev) => prev + input);
    }
  });

  return (
    <Box>
      <Text bold color={ACCENT}>❯ </Text>
      <Text color={TEXT}>{value}</Text>
      {/* Blinking cursor */}
      <Text color={ACCENT}>█</Text>
    </Box>
  );
}
