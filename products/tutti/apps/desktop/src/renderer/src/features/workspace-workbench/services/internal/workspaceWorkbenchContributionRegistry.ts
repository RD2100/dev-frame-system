import type { WorkbenchContribution } from "@tutti-os/workbench-surface";
import type {
  DesktopWorkbenchContributionContext,
  DesktopWorkbenchContributionFactory
} from "./workspaceWorkbenchContributionFactory";

export interface WorkspaceWorkbenchContributionRegistryResult {
  contributions: WorkbenchContribution[];
}

export function createWorkspaceWorkbenchContributionRegistryResult(input: {
  context: DesktopWorkbenchContributionContext;
  factories: readonly DesktopWorkbenchContributionFactory[];
}): WorkspaceWorkbenchContributionRegistryResult {
  const results = [...input.factories]
    .sort(compareDesktopWorkbenchContributionFactories)
    .map((factory) => factory.create(input.context))
    .filter((result): result is WorkbenchContribution => Boolean(result));

  return {
    contributions: results
  };
}

function compareDesktopWorkbenchContributionFactories(
  left: DesktopWorkbenchContributionFactory,
  right: DesktopWorkbenchContributionFactory
): number {
  return left.order - right.order || left.id.localeCompare(right.id);
}
