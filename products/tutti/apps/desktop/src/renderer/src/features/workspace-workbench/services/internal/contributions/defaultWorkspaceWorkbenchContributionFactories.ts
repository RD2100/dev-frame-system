import type { DesktopWorkbenchContributionFactory } from "../workspaceWorkbenchContributionFactory";
import { agentGuiWorkbenchContributionFactory } from "./agentGuiWorkbenchContributionFactory.ts";
import { appCenterWorkbenchContributionFactory } from "./appCenterWorkbenchContributionFactory.ts";
import { browserWorkbenchContributionFactory } from "./browserWorkbenchContributionFactory.ts";
import { filePreviewWorkbenchContributionFactory } from "./filePreviewWorkbenchContributionFactory.ts";
import { filesWorkbenchContributionFactory } from "./filesWorkbenchContributionFactory.ts";
import { issueManagerWorkbenchContributionFactory } from "./issueManagerWorkbenchContributionFactory.ts";
import { terminalWorkbenchContributionFactory } from "./terminalWorkbenchContributionFactory.ts";

export const defaultWorkspaceWorkbenchContributionFactories: readonly DesktopWorkbenchContributionFactory[] =
  [
    filesWorkbenchContributionFactory,
    filePreviewWorkbenchContributionFactory,
    appCenterWorkbenchContributionFactory,
    browserWorkbenchContributionFactory,
    agentGuiWorkbenchContributionFactory,
    issueManagerWorkbenchContributionFactory,
    terminalWorkbenchContributionFactory
  ];
