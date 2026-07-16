import { Button, Input } from "@tutti-os/ui-system/components";

import type { ComponentExample } from "../registry/componentRegistry";

export const primitiveExamples: Record<string, ComponentExample> = {
  Button: {
    title: "Button",
    description: "Primary, secondary, outline, ghost, and destructive actions.",
    render: () => (
      <div className="flex flex-wrap items-center gap-2">
        <Button>Save changes</Button>
        <Button variant="secondary">Sync</Button>
        <Button variant="outline">Preview</Button>
        <Button variant="ghost">Cancel</Button>
        <Button variant="destructive">Delete</Button>
      </div>
    )
  },
  Input: {
    title: "Input",
    description:
      "Default, focused-adjacent, disabled, and invalid text fields.",
    render: () => (
      <div className="grid max-w-3xl gap-3 sm:grid-cols-2">
        <label className="grid gap-1.5 text-[11px] font-medium text-muted-foreground">
          Workspace name
          <Input defaultValue="Tutti Design System" />
        </label>
        <label className="grid gap-1.5 text-[11px] font-medium text-muted-foreground">
          Search token
          <Input placeholder="component, hook, token..." />
        </label>
        <label className="grid gap-1.5 text-[11px] font-medium text-muted-foreground">
          Disabled
          <Input disabled defaultValue="Locked by policy" />
        </label>
        <label className="grid gap-1.5 text-[11px] font-medium text-muted-foreground">
          Invalid
          <Input aria-invalid defaultValue="invalid#value" />
        </label>
      </div>
    )
  }
};
