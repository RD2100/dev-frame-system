import colorsSource from "./colors.json" with { type: "json" };
import metricsSource from "./metrics.json" with { type: "json" };
import overviewSource from "./overview.json" with { type: "json" };
import typographySource from "./typography.json" with { type: "json" };

type FoundationSectionBase = {
  id: string;
  label: string;
  title: string;
  summary: string;
  description: string;
};

export type OverviewContent = FoundationSectionBase & {
  cards: Array<{
    title: string;
    items: Array<{
      keyword: string;
      desc: string;
    }>;
  }>;
};

export type ColorsContent = FoundationSectionBase & {
  groups: Array<{
    title: string;
    description: string;
    tokens: Array<{
      label: string;
      usage: string;
      dark: string;
      light: string;
    }>;
  }>;
};

export type TypographyContent = FoundationSectionBase & {
  characterRoles: {
    title: string;
    description: string;
    rows: Array<{
      label: string;
      stack: string;
      note: string;
    }>;
  };
  cssTokens: {
    title: string;
    description: string;
    rows: Array<{
      label: string;
      sample: string;
      value: string;
    }>;
  };
  weightRules: {
    title: string;
    description: string;
    items: Array<{
      label: string;
      className: string;
      sample: string;
    }>;
  };
  typeScale: {
    title: string;
    description: string;
    items: Array<{
      name: string;
      className: string;
      meta: string;
      english: string;
      chinese: string;
      sample: string;
    }>;
  };
  rules: {
    title: string;
    description: string;
    items: string[];
  };
};

export type MetricsContent = FoundationSectionBase & {
  spacing: {
    title: string;
    description: string;
    tokens: string[];
  };
  radius: {
    title: string;
    description: string;
    tokens: Array<{
      label: string;
      value: string;
      usage: string;
    }>;
  };
  motion: {
    title: string;
    description: string;
    tokens: Array<{
      label: string;
      value: string;
    }>;
  };
};

function assertRecord(
  value: unknown,
  label: string
): asserts value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object.`);
  }
}

function readString(
  record: Record<string, unknown>,
  key: string,
  label: string
): string {
  const value = record[key];
  if (typeof value !== "string") {
    throw new Error(`${label}.${key} must be a string.`);
  }
  return value;
}

function readArray(
  record: Record<string, unknown>,
  key: string,
  label: string
): unknown[] {
  const value = record[key];
  if (!Array.isArray(value)) {
    throw new Error(`${label}.${key} must be an array.`);
  }
  return value;
}

function readBaseSection(
  source: unknown,
  label: string
): FoundationSectionBase & Record<string, unknown> {
  assertRecord(source, label);
  return {
    ...source,
    id: readString(source, "id", label),
    label: readString(source, "label", label),
    title: readString(source, "title", label),
    summary: readString(source, "summary", label),
    description: readString(source, "description", label)
  };
}

function parseOverviewContent(source: unknown): OverviewContent {
  const section = readBaseSection(source, "overview");
  const cards = readArray(section, "cards", "overview").map((card, index) => {
    const cardLabel = `overview.cards[${index}]`;
    assertRecord(card, cardLabel);
    return {
      title: readString(card, "title", cardLabel),
      items: readArray(card, "items", cardLabel).map((item, itemIndex) => {
        const itemLabel = `${cardLabel}.items[${itemIndex}]`;
        assertRecord(item, itemLabel);
        return {
          keyword: readString(item, "keyword", itemLabel),
          desc: readString(item, "desc", itemLabel)
        };
      })
    };
  });

  return { ...section, cards };
}

function parseColorsContent(source: unknown): ColorsContent {
  const section = readBaseSection(source, "colors");
  const groups = readArray(section, "groups", "colors").map((group, index) => {
    const groupLabel = `colors.groups[${index}]`;
    assertRecord(group, groupLabel);
    return {
      title: readString(group, "title", groupLabel),
      description: readString(group, "description", groupLabel),
      tokens: readArray(group, "tokens", groupLabel).map(
        (token, tokenIndex) => {
          const tokenLabel = `${groupLabel}.tokens[${tokenIndex}]`;
          assertRecord(token, tokenLabel);
          return {
            label: readString(token, "label", tokenLabel),
            usage: readString(token, "usage", tokenLabel),
            dark: readString(token, "dark", tokenLabel),
            light: readString(token, "light", tokenLabel)
          };
        }
      )
    };
  });

  return { ...section, groups };
}

function parseTypographyContent(source: unknown): TypographyContent {
  const section = readBaseSection(source, "typography");

  const characterRolesSource = section.characterRoles;
  assertRecord(characterRolesSource, "typography.characterRoles");

  const cssTokensSource = section.cssTokens;
  assertRecord(cssTokensSource, "typography.cssTokens");

  const weightRulesSource = section.weightRules;
  assertRecord(weightRulesSource, "typography.weightRules");

  const typeScaleSource = section.typeScale;
  assertRecord(typeScaleSource, "typography.typeScale");

  const rulesSource = section.rules;
  assertRecord(rulesSource, "typography.rules");

  return {
    ...section,
    characterRoles: {
      title: readString(
        characterRolesSource,
        "title",
        "typography.characterRoles"
      ),
      description: readString(
        characterRolesSource,
        "description",
        "typography.characterRoles"
      ),
      rows: readArray(
        characterRolesSource,
        "rows",
        "typography.characterRoles"
      ).map((row, index) => {
        const rowLabel = `typography.characterRoles.rows[${index}]`;
        assertRecord(row, rowLabel);
        return {
          label: readString(row, "label", rowLabel),
          stack: readString(row, "stack", rowLabel),
          note: readString(row, "note", rowLabel)
        };
      })
    },
    cssTokens: {
      title: readString(cssTokensSource, "title", "typography.cssTokens"),
      description: readString(
        cssTokensSource,
        "description",
        "typography.cssTokens"
      ),
      rows: readArray(cssTokensSource, "rows", "typography.cssTokens").map(
        (row, index) => {
          const rowLabel = `typography.cssTokens.rows[${index}]`;
          assertRecord(row, rowLabel);
          return {
            label: readString(row, "label", rowLabel),
            sample: readString(row, "sample", rowLabel),
            value: readString(row, "value", rowLabel)
          };
        }
      )
    },
    weightRules: {
      title: readString(weightRulesSource, "title", "typography.weightRules"),
      description: readString(
        weightRulesSource,
        "description",
        "typography.weightRules"
      ),
      items: readArray(
        weightRulesSource,
        "items",
        "typography.weightRules"
      ).map((item, index) => {
        const itemLabel = `typography.weightRules.items[${index}]`;
        assertRecord(item, itemLabel);
        return {
          label: readString(item, "label", itemLabel),
          className: readString(item, "className", itemLabel),
          sample: readString(item, "sample", itemLabel)
        };
      })
    },
    typeScale: {
      title: readString(typeScaleSource, "title", "typography.typeScale"),
      description: readString(
        typeScaleSource,
        "description",
        "typography.typeScale"
      ),
      items: readArray(typeScaleSource, "items", "typography.typeScale").map(
        (item, index) => {
          const itemLabel = `typography.typeScale.items[${index}]`;
          assertRecord(item, itemLabel);
          return {
            name: readString(item, "name", itemLabel),
            className: readString(item, "className", itemLabel),
            meta: readString(item, "meta", itemLabel),
            english: readString(item, "english", itemLabel),
            chinese: readString(item, "chinese", itemLabel),
            sample: readString(item, "sample", itemLabel)
          };
        }
      )
    },
    rules: {
      title: readString(rulesSource, "title", "typography.rules"),
      description: readString(rulesSource, "description", "typography.rules"),
      items: readArray(rulesSource, "items", "typography.rules").map(
        (item, index) => {
          if (typeof item !== "string") {
            throw new Error(
              `typography.rules.items[${index}] must be a string.`
            );
          }
          return item;
        }
      )
    }
  };
}

function parseMetricsContent(source: unknown): MetricsContent {
  const section = readBaseSection(source, "metrics");

  const spacingSource = section.spacing;
  assertRecord(spacingSource, "metrics.spacing");

  const radiusSource = section.radius;
  assertRecord(radiusSource, "metrics.radius");

  const motionSource = section.motion;
  assertRecord(motionSource, "metrics.motion");

  return {
    ...section,
    spacing: {
      title: readString(spacingSource, "title", "metrics.spacing"),
      description: readString(spacingSource, "description", "metrics.spacing"),
      tokens: readArray(spacingSource, "tokens", "metrics.spacing").map(
        (token, index) => {
          if (typeof token !== "string") {
            throw new Error(
              `metrics.spacing.tokens[${index}] must be a string.`
            );
          }
          return token;
        }
      )
    },
    radius: {
      title: readString(radiusSource, "title", "metrics.radius"),
      description: readString(radiusSource, "description", "metrics.radius"),
      tokens: readArray(radiusSource, "tokens", "metrics.radius").map(
        (token, index) => {
          const tokenLabel = `metrics.radius.tokens[${index}]`;
          assertRecord(token, tokenLabel);
          return {
            label: readString(token, "label", tokenLabel),
            value: readString(token, "value", tokenLabel),
            usage: readString(token, "usage", tokenLabel)
          };
        }
      )
    },
    motion: {
      title: readString(motionSource, "title", "metrics.motion"),
      description: readString(motionSource, "description", "metrics.motion"),
      tokens: readArray(motionSource, "tokens", "metrics.motion").map(
        (token, index) => {
          const tokenLabel = `metrics.motion.tokens[${index}]`;
          assertRecord(token, tokenLabel);
          return {
            label: readString(token, "label", tokenLabel),
            value: readString(token, "value", tokenLabel)
          };
        }
      )
    }
  };
}

export const overviewContent = parseOverviewContent(overviewSource);
export const colorsContent = parseColorsContent(colorsSource);
export const typographyContent = parseTypographyContent(typographySource);
export const metricsContent = parseMetricsContent(metricsSource);

export const foundationSections = [
  overviewContent,
  colorsContent,
  typographyContent,
  metricsContent
] as const;

export const foundationNavigationSections = foundationSections.map(
  ({ id, label, summary }) => ({
    id,
    label,
    layer: "foundation" as const,
    summary
  })
);
