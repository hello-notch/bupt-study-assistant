import DOMPurify from "dompurify";
import katex from "katex";
import { marked } from "marked";

interface ProtectedToken {
  marker: string;
  value: string;
}

marked.setOptions({
  breaks: true,
  gfm: true,
});

export function renderAssistantContent(source: string): string {
  const codeTokens: ProtectedToken[] = [];
  const mathTokens: ProtectedToken[] = [];
  let prepared = protect(source, /```[\s\S]*?```|`[^`\n]+`/g, "CODE", codeTokens);
  prepared = protectMath(prepared, mathTokens);
  prepared = restore(prepared, codeTokens);

  let html = marked.parse(prepared, { async: false }) as string;
  html = restore(html, mathTokens);
  return DOMPurify.sanitize(html, { USE_PROFILES: { html: true, svg: true, mathMl: true } });
}

function protect(source: string, pattern: RegExp, prefix: string, tokens: ProtectedToken[]): string {
  return source.replace(pattern, (value) => {
    const marker = `YOUXUEBAN${prefix}TOKEN${tokens.length}END`;
    tokens.push({ marker, value });
    return marker;
  });
}

function protectMath(source: string, tokens: ProtectedToken[]): string {
  const patterns: Array<{ pattern: RegExp; displayMode: boolean; contentIndex: number }> = [
    { pattern: /\$\$([\s\S]+?)\$\$/g, displayMode: true, contentIndex: 1 },
    { pattern: /\\\[([\s\S]+?)\\\]/g, displayMode: true, contentIndex: 1 },
    { pattern: /\\\((.+?)\\\)/g, displayMode: false, contentIndex: 1 },
    { pattern: /(^|[^\\$])\$([^$\n]+?)\$/g, displayMode: false, contentIndex: 2 },
  ];
  let result = source;
  for (const { pattern, displayMode, contentIndex } of patterns) {
    result = result.replace(pattern, (...match: string[]) => {
      const prefix = contentIndex === 2 ? match[1] ?? "" : "";
      const formula = match[contentIndex] ?? "";
      const marker = `YOUXUEBANMATHTOKEN${tokens.length}END`;
      let value: string;
      try {
        value = katex.renderToString(formula, { displayMode, throwOnError: false, strict: "ignore" });
      } catch {
        value = `<code class="math-error">${escapeHtml(formula)}</code>`;
      }
      tokens.push({ marker, value });
      return `${prefix}${marker}`;
    });
  }
  return result;
}

function restore(source: string, tokens: ProtectedToken[]): string {
  return tokens.reduce((result, token) => result.replaceAll(token.marker, token.value), source);
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]!);
}
