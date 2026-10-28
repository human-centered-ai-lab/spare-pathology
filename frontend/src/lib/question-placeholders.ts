import type { SchemaQuestion } from "@/types";

type AttributeValue = string | number | boolean;

export type QuestionAttributeMap = Record<string, AttributeValue>;

const PLACEHOLDER_PATTERN = /{{\s*([^{}]+?)\s*}}/g;

function formatQuestionAttributeValue(value: AttributeValue) {
  if (typeof value === "string") {
    return value.replace(/_/g, " ");
  }

  return String(value);
}

export function formatAttributePlaceholder(name: string) {
  return `{{${name}}}`;
}

export function extractQuestionPlaceholderNames(
  ...texts: Array<string | null | undefined>
) {
  const seen = new Set<string>();
  const names: string[] = [];

  for (const text of texts) {
    if (!text) continue;

    for (const match of text.matchAll(PLACEHOLDER_PATTERN)) {
      const name = match[1]?.trim();
      if (!name || seen.has(name)) continue;
      seen.add(name);
      names.push(name);
    }
  }

  return names;
}

export function extractSchemaQuestionPlaceholderNames(
  questions: SchemaQuestion[],
) {
  return extractQuestionPlaceholderNames(
    ...questions.flatMap((question) => [question.name, question.description]),
  );
}

export function renderQuestionTemplate(
  template: string | null | undefined,
  attributes?: QuestionAttributeMap,
) {
  if (!template) return "";

  return template.replace(PLACEHOLDER_PATTERN, (match, rawName: string) => {
    const name = rawName.trim();
    if (!name) return match;

    const value = attributes?.[name];
    if (value === undefined || value === null) {
      return match;
    }

    return formatQuestionAttributeValue(value);
  });
}
