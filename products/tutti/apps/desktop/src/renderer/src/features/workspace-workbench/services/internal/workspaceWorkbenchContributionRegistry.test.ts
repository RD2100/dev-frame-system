import assert from "node:assert/strict";
import test from "node:test";
import type {
  DesktopWorkbenchContributionContext,
  DesktopWorkbenchContributionFactory
} from "./workspaceWorkbenchContributionFactory";
import { createWorkspaceWorkbenchContributionRegistryResult } from "./workspaceWorkbenchContributionRegistry.ts";

test("workbench contribution registry sorts factories and skips unavailable entries", () => {
  const registry = createWorkspaceWorkbenchContributionRegistryResult({
    context: {} as DesktopWorkbenchContributionContext,
    factories: [
      createFactory({ id: "terminal", order: 40 }),
      createFactory({ id: "files", order: 10 }),
      createFactory({ id: "browser", order: 20, unavailable: true })
    ]
  });

  assert.deepEqual(
    registry.contributions.map((contribution) => contribution.id),
    ["files", "terminal"]
  );
});

function createFactory(input: {
  id: string;
  order: number;
  unavailable?: boolean;
}): DesktopWorkbenchContributionFactory {
  return {
    id: input.id,
    order: input.order,
    create() {
      if (input.unavailable) {
        return null;
      }

      return {
        id: input.id
      };
    }
  };
}
