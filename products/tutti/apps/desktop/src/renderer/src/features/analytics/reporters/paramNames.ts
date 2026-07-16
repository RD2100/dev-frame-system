export function toAnalyticsParamName(name: string): string {
  return name.replace(/[A-Z]/g, (match) => `_${match.toLowerCase()}`);
}
