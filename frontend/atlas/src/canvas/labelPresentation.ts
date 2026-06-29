const MAX_CANVAS_LABEL_CHARS = 44;
const MAX_CANVAS_LABEL_LINE_LENGTH = 20;
const MAX_CANVAS_LABEL_LINES = 2;

export function presentRegionCanvasTitle(title: string): string {
  const normalized = normalizeLabel(title);
  const compact = compactTechnicalLabel(normalized);
  return wrapLabel(compact, MAX_CANVAS_LABEL_LINE_LENGTH, MAX_CANVAS_LABEL_LINES);
}

function compactTechnicalLabel(title: string): string {
  let compact = title;
  let truncated = false;

  if (/[\\/]/.test(compact)) {
    const parts = compact.split(/[\\/]/).filter(Boolean);
    compact = parts.at(-1) ?? compact;
  }

  compact = compact.replace(/^python\d?(?:\.\d+)?\s+/i, "");
  compact = compact.replace(/\.[a-z0-9]+$/i, "");
  compact = compact.replace(/[_-]+/g, " ");
  compact = compact.replace(/\s+/g, " ").trim();

  if (compact.length <= MAX_CANVAS_LABEL_CHARS) {
    return compact;
  }

  const words = compact.split(" ");
  if (words.length > 2) {
    compact = words.slice(0, 4).join(" ");
    truncated = words.length > 4;
  }

  if (compact.length > MAX_CANVAS_LABEL_CHARS) {
    compact = `${compact.slice(0, MAX_CANVAS_LABEL_CHARS - 1).trimEnd()}…`;
    truncated = false;
  }

  if (truncated) {
    compact = appendEllipsis(compact, MAX_CANVAS_LABEL_CHARS);
  }

  return compact;
}

function wrapLabel(text: string, lineLength: number, maxLines: number): string {
    if (text.length <= lineLength) {
      return text;
    }

  const words = text.split(" ").filter(Boolean);
  const lines: string[] = [];
  let index = 0;
  let currentLine = "";

  while (index < words.length) {
    const word = clampWord(words[index], lineLength);
    const candidate = currentLine ? `${currentLine} ${word}` : word;

    if (candidate.length <= lineLength) {
      currentLine = candidate;
      index += 1;
      continue;
    }

    if (currentLine) {
      lines.push(currentLine);
      currentLine = "";
      if (lines.length === maxLines) {
        break;
      }
      continue;
    }

    lines.push(word);
    index += 1;
    if (lines.length === maxLines) {
      break;
    }
  }

  if (currentLine && lines.length < maxLines) {
    lines.push(currentLine);
  }

  if (index < words.length && lines.length > 0) {
    lines[lines.length - 1] = appendEllipsis(lines[lines.length - 1], lineLength);
  }

  return lines.slice(0, maxLines).join("\n");
}

function normalizeLabel(title: string): string {
  const normalized = title.trim().replace(/\s+/g, " ");
  return normalized || "Untitled region";
}


function clampWord(word: string, lineLength: number): string {
  if (word.length <= lineLength) {
    return word;
  }
  return `${word.slice(0, lineLength - 1)}…`;
}


function appendEllipsis(line: string, lineLength: number): string {
  if (line.endsWith("…")) {
    return line;
  }
  if (line.length >= lineLength) {
    return `${line.slice(0, lineLength - 1).trimEnd()}…`;
  }
  return `${line}…`;
}
