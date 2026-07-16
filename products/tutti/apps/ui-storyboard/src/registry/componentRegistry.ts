import type { ReactNode } from "react";

import { primitiveExamples } from "../examples/primitives";

export interface ComponentExample {
  title: string;
  description: string;
  render: () => ReactNode;
}

export const componentExampleRegistry: Record<string, ComponentExample> = {
  ...primitiveExamples
};
