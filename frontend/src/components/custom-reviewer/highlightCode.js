import hljs from "highlight.js/lib/core";
import go from "highlight.js/lib/languages/go";
import java from "highlight.js/lib/languages/java";
import javascript from "highlight.js/lib/languages/javascript";
import python from "highlight.js/lib/languages/python";
import sql from "highlight.js/lib/languages/sql";
import typescript from "highlight.js/lib/languages/typescript";
import xml from "highlight.js/lib/languages/xml";

let didRegisterLanguages = false;

function ensureLanguagesRegistered() {
  if (didRegisterLanguages) return;

  hljs.registerLanguage("python", python);
  hljs.registerLanguage("sql", sql);
  hljs.registerLanguage("javascript", javascript);
  hljs.registerLanguage("typescript", typescript);
  hljs.registerLanguage("xml", xml);
  hljs.registerLanguage("go", go);
  hljs.registerLanguage("java", java);

  didRegisterLanguages = true;
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function mapLanguage(language) {
  if (language === "html") return "xml";
  if (language === "react") return "javascript";
  if (language === "auto" || language === "text") return "";
  return language;
}

export function highlightReviewerCode(code, language = "auto") {
  ensureLanguagesRegistered();

  const normalized = (code || "").replace(/\r\n/g, "\n");
  if (!normalized) return "";

  try {
    const mappedLanguage = mapLanguage(language);

    if (mappedLanguage && hljs.getLanguage(mappedLanguage)) {
      return hljs.highlight(normalized, {
        language: mappedLanguage,
        ignoreIllegals: true,
      }).value;
    }

    return hljs.highlightAuto(normalized, [
      "python",
      "sql",
      "javascript",
      "typescript",
      "xml",
      "go",
      "java",
    ]).value;
  } catch (error) {
    return escapeHtml(normalized);
  }
}
