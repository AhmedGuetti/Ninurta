// Fixed status bar at the bottom.

import React from "react";
import { Box, Text } from "ink";
import { STATUS_READY, MUTED } from "../lib/palette.js";

export default function StatusBar({ modelId, cwd }) {
  const shortModel = modelId.replace("gemini:", "");
  return (
    <Box>
      <Text bold color={STATUS_READY}>– ready </Text>
      <Text color={MUTED}>| {shortModel} | 0s | voice off | 1 session</Text>
      <Text>                    </Text>
      <Text color={MUTED}>~ {cwd}</Text>
    </Box>
  );
}
