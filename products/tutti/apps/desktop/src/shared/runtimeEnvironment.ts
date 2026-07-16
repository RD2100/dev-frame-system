export interface DesktopRuntimeEnvironmentInput {
  tuttiEnv?: string | null;
  nodeEnv?: string | null;
}

export function isDesktopDevelopmentRuntime({
  tuttiEnv,
  nodeEnv
}: DesktopRuntimeEnvironmentInput): boolean {
  const normalizedTuttiEnv = tuttiEnv?.trim();
  if (normalizedTuttiEnv) {
    return /^(dev|development|local)$/i.test(normalizedTuttiEnv);
  }

  return nodeEnv === "development";
}
