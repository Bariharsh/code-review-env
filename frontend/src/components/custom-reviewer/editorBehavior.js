const OPENING_PAIRS = {
  "(": ")",
  "[": "]",
  "{": "}",
  "\"": "\"",
  "'": "'",
  "`": "`",
};

const COMMENT_PREFIX = {
  python: "# ",
  javascript: "// ",
  typescript: "// ",
  react: "// ",
  java: "// ",
  go: "// ",
  sql: "-- ",
};

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function getLineBounds(value, start, end = start) {
  const safeStart = clamp(start, 0, value.length);
  const safeEnd = clamp(end, safeStart, value.length);
  const lineStart = value.lastIndexOf("\n", safeStart - 1) + 1;
  const normalizedEnd = safeEnd > safeStart && value[safeEnd - 1] === "\n" ? safeEnd - 1 : safeEnd;
  const nextBreak = value.indexOf("\n", normalizedEnd);
  const lineEnd = nextBreak === -1 ? value.length : nextBreak;

  return {
    safeStart,
    safeEnd,
    lineStart,
    lineEnd,
    text: value.slice(lineStart, lineEnd),
  };
}

function getLeadingIndent(line) {
  return line.match(/^[\t ]*/)?.[0] ?? "";
}

function removeIndent(line, indentUnit) {
  if (!line) return { line, removed: 0 };
  if (line.startsWith("\t")) return { line: line.slice(1), removed: 1 };
  if (line.startsWith(indentUnit)) {
    return { line: line.slice(indentUnit.length), removed: indentUnit.length };
  }

  const leadingSpaces = line.match(/^ +/)?.[0].length ?? 0;
  const removable = Math.min(leadingSpaces, indentUnit.length);
  return {
    line: line.slice(removable),
    removed: removable,
  };
}

function shouldAutoPairQuote(value, start, key) {
  const previousChar = value[start - 1] ?? "";
  const nextChar = value[start] ?? "";

  if (previousChar === "\\") return false;
  if (!nextChar) return true;
  if (nextChar === key) return false;

  return /[\s)\]}>,.;:]/.test(nextChar);
}

export function getIndentUnit(language = "auto") {
  if (language === "python") return "    ";
  if (language === "java") return "    ";
  return "  ";
}

export function getCursorMeta(value = "", start = 0, end = start) {
  const safeStart = clamp(start, 0, value.length);
  const safeEnd = clamp(end, safeStart, value.length);
  const beforeCursor = value.slice(0, safeStart);
  const line = beforeCursor.split("\n").length;
  const lineStart = beforeCursor.lastIndexOf("\n") + 1;
  const column = safeStart - lineStart + 1;
  const selectedText = value.slice(safeStart, safeEnd);

  return {
    line,
    column,
    selectedChars: safeEnd - safeStart,
    selectedLines: selectedText ? selectedText.split("\n").length : 0,
  };
}

export function applyTabBehavior({ value, start, end, language = "auto", shiftKey = false }) {
  const indentUnit = getIndentUnit(language);

  if (start === end && !shiftKey) {
    const nextValue = `${value.slice(0, start)}${indentUnit}${value.slice(end)}`;
    const nextCursor = start + indentUnit.length;
    return { value: nextValue, start: nextCursor, end: nextCursor };
  }

  const { lineStart, lineEnd, safeStart, safeEnd } = getLineBounds(value, start, end);
  const block = value.slice(lineStart, lineEnd);
  const lines = block.split("\n");

  if (safeStart === safeEnd && shiftKey) {
    const line = lines[0] ?? "";
    const { line: nextLine, removed } = removeIndent(line, indentUnit);
    const nextValue = `${value.slice(0, lineStart)}${nextLine}${value.slice(lineEnd)}`;
    const nextCursor = Math.max(lineStart, safeStart - removed);
    return { value: nextValue, start: nextCursor, end: nextCursor };
  }

  if (!block.includes("\n") && !shiftKey) {
    const nextValue = `${value.slice(0, safeStart)}${indentUnit}${value.slice(safeEnd)}`;
    const nextCursor = safeStart + indentUnit.length;
    return { value: nextValue, start: nextCursor, end: nextCursor };
  }

  let totalDelta = 0;
  let firstLineDelta = 0;
  const nextLines = lines.map((line, index) => {
    if (shiftKey) {
      const { line: nextLine, removed } = removeIndent(line, indentUnit);
      totalDelta -= removed;
      if (index === 0) firstLineDelta = -removed;
      return nextLine;
    }

    totalDelta += indentUnit.length;
    if (index === 0) firstLineDelta = indentUnit.length;
    return `${indentUnit}${line}`;
  });

  const nextBlock = nextLines.join("\n");
  const nextValue = `${value.slice(0, lineStart)}${nextBlock}${value.slice(lineEnd)}`;

  return {
    value: nextValue,
    start: Math.max(lineStart, safeStart + firstLineDelta),
    end: safeEnd + totalDelta,
  };
}

export function applyEnterBehavior({ value, start, end, language = "auto" }) {
  const indentUnit = getIndentUnit(language);
  const before = value.slice(0, start);
  const after = value.slice(end);
  const currentLine = before.slice(before.lastIndexOf("\n") + 1);
  const currentIndent = getLeadingIndent(currentLine);
  const previousChar = value[start - 1] ?? "";
  const nextChar = value[end] ?? "";
  const shouldExpandPair = start === end && OPENING_PAIRS[previousChar] === nextChar;
  const shouldIncreaseIndent =
    /[:([{]$/.test(currentLine.trimEnd()) ||
    (language === "python" && currentLine.trimEnd().endsWith(":"));

  if (shouldExpandPair) {
    const insert = `\n${currentIndent}${indentUnit}\n${currentIndent}`;
    const nextValue = `${before}${insert}${after}`;
    const nextCursor = start + 1 + currentIndent.length + indentUnit.length;
    return { value: nextValue, start: nextCursor, end: nextCursor };
  }

  const insert = `\n${currentIndent}${shouldIncreaseIndent ? indentUnit : ""}`;
  const nextCursor = start + insert.length;
  return {
    value: `${before}${insert}${after}`,
    start: nextCursor,
    end: nextCursor,
  };
}

export function applyPairBehavior({ value, start, end, key }) {
  const closingPair = OPENING_PAIRS[key];

  if (Object.values(OPENING_PAIRS).includes(key) && start === end && value[end] === key) {
    const nextCursor = end + 1;
    return { value, start: nextCursor, end: nextCursor };
  }

  if (closingPair) {
    const isQuote = key === "\"" || key === "'" || key === "`";
    if (isQuote && !shouldAutoPairQuote(value, start, key)) return null;

    if (start !== end) {
      const selected = value.slice(start, end);
      const nextValue = `${value.slice(0, start)}${key}${selected}${closingPair}${value.slice(end)}`;
      return { value: nextValue, start: start + 1, end: end + 1 };
    }

    const nextValue = `${value.slice(0, start)}${key}${closingPair}${value.slice(end)}`;
    const nextCursor = start + 1;
    return { value: nextValue, start: nextCursor, end: nextCursor };
  }

  return null;
}

export function applyBackspaceBehavior({ value, start, end }) {
  if (start !== end || start === 0) return null;

  const previousChar = value[start - 1];
  const nextChar = value[end];

  if (OPENING_PAIRS[previousChar] === nextChar) {
    const nextValue = `${value.slice(0, start - 1)}${value.slice(end + 1)}`;
    const nextCursor = start - 1;
    return { value: nextValue, start: nextCursor, end: nextCursor };
  }

  return null;
}

export function applyCommentToggle({ value, start, end, language = "auto" }) {
  const prefix = COMMENT_PREFIX[language];
  if (!prefix) return null;

  const { lineStart, lineEnd } = getLineBounds(value, start, end);
  const block = value.slice(lineStart, lineEnd);
  const lines = block.split("\n");
  const nonEmptyLines = lines.filter((line) => line.trim());

  if (!nonEmptyLines.length) return null;

  const isCommented = nonEmptyLines.every((line) => {
    const trimmed = line.trimStart();
    return trimmed.startsWith(prefix.trim());
  });

  const nextBlock = lines
    .map((line) => {
      if (!line.trim()) return line;

      const indent = getLeadingIndent(line);
      const content = line.slice(indent.length);

      if (isCommented && content.startsWith(prefix)) {
        return `${indent}${content.slice(prefix.length)}`;
      }

      if (isCommented && content.startsWith(prefix.trim())) {
        return `${indent}${content.slice(prefix.trim().length).replace(/^ /, "")}`;
      }

      return `${indent}${prefix}${content}`;
    })
    .join("\n");

  const nextValue = `${value.slice(0, lineStart)}${nextBlock}${value.slice(lineEnd)}`;
  return {
    value: nextValue,
    start: lineStart,
    end: lineStart + nextBlock.length,
  };
}
