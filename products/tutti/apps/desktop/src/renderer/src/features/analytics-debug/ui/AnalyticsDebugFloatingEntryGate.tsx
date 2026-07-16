import { AnalyticsDebugFloatingEntry } from "./AnalyticsDebugFloatingEntry";
import { useAnalyticsDebugPreferenceService } from "./useAnalyticsDebugPreferenceService";

export function AnalyticsDebugFloatingEntryGate() {
  const { state } = useAnalyticsDebugPreferenceService();

  if (!state.available || !state.enabled) {
    return null;
  }

  return <AnalyticsDebugFloatingEntry />;
}
