import type { AgentEnvDetectedParams } from "../agent-env-detected/types.ts";

// The consent-gated "report problem" payload: the privacy-safe summary plus the
// more revealing diagnostic detail (paths, endpoints, proxy address). Sent only
// after the user agrees; still omits the account email.
export interface AgentEnvIssueReportedParams extends AgentEnvDetectedParams {
  consentGiven: boolean;
  cliPath: string;
  adapterTarget: string;
  accountPresent: boolean;
  registryEndpoint: string;
  apiEndpoint: string;
  proxyUrl: string;
}
