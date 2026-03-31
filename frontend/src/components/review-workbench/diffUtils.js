function normalizeCode(code) {
  return (code ?? "").replace(/\r\n/g, "\n");
}

export function splitCodeLines(code) {
  const normalized = normalizeCode(code);
  if (!normalized) {
    return [];
  }

  const lines = normalized.split("\n");
  if (lines.length > 0 && lines[lines.length - 1] === "") {
    lines.pop();
  }
  return lines;
}

export function buildLineDiffRows(beforeCode, afterCode) {
  const beforeLines = splitCodeLines(beforeCode);
  const afterLines = splitCodeLines(afterCode);
  const dp = Array.from({ length: beforeLines.length + 1 }, () => Array(afterLines.length + 1).fill(0));

  for (let beforeIndex = beforeLines.length - 1; beforeIndex >= 0; beforeIndex -= 1) {
    for (let afterIndex = afterLines.length - 1; afterIndex >= 0; afterIndex -= 1) {
      if (beforeLines[beforeIndex] === afterLines[afterIndex]) {
        dp[beforeIndex][afterIndex] = dp[beforeIndex + 1][afterIndex + 1] + 1;
      } else {
        dp[beforeIndex][afterIndex] = Math.max(dp[beforeIndex + 1][afterIndex], dp[beforeIndex][afterIndex + 1]);
      }
    }
  }

  const rows = [];
  let beforeIndex = 0;
  let afterIndex = 0;
  let beforeLineNumber = 1;
  let afterLineNumber = 1;

  while (beforeIndex < beforeLines.length && afterIndex < afterLines.length) {
    if (beforeLines[beforeIndex] === afterLines[afterIndex]) {
      rows.push({
        type: "same",
        content: beforeLines[beforeIndex],
        beforeLineNumber,
        afterLineNumber,
      });
      beforeIndex += 1;
      afterIndex += 1;
      beforeLineNumber += 1;
      afterLineNumber += 1;
      continue;
    }

    if (dp[beforeIndex + 1][afterIndex] >= dp[beforeIndex][afterIndex + 1]) {
      rows.push({
        type: "remove",
        content: beforeLines[beforeIndex],
        beforeLineNumber,
        afterLineNumber: null,
      });
      beforeIndex += 1;
      beforeLineNumber += 1;
      continue;
    }

    rows.push({
      type: "add",
      content: afterLines[afterIndex],
      beforeLineNumber: null,
      afterLineNumber,
    });
    afterIndex += 1;
    afterLineNumber += 1;
  }

  while (beforeIndex < beforeLines.length) {
    rows.push({
      type: "remove",
      content: beforeLines[beforeIndex],
      beforeLineNumber,
      afterLineNumber: null,
    });
    beforeIndex += 1;
    beforeLineNumber += 1;
  }

  while (afterIndex < afterLines.length) {
    rows.push({
      type: "add",
      content: afterLines[afterIndex],
      beforeLineNumber: null,
      afterLineNumber,
    });
    afterIndex += 1;
    afterLineNumber += 1;
  }

  return rows;
}

export function summarizeDiff(rows) {
  return rows.reduce(
    (summary, row) => {
      if (row.type === "add") {
        summary.added += 1;
      } else if (row.type === "remove") {
        summary.removed += 1;
      } else {
        summary.unchanged += 1;
      }

      summary.changed = summary.added + summary.removed;
      return summary;
    },
    { added: 0, removed: 0, unchanged: 0, changed: 0 },
  );
}
