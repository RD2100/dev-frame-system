import { useState } from "react";

export interface TerminalFindRuntime {
  findNext(
    query: string,
    options: {
      caseSensitive: boolean;
      incremental?: boolean;
      regex: boolean;
    }
  ): void;
  findPrevious(
    query: string,
    options: {
      caseSensitive: boolean;
      regex: boolean;
    }
  ): void;
}

export interface TerminalFindController {
  actions: {
    close(): void;
    findNext(): void;
    findPrevious(): void;
    open(): void;
    onQueryChange(query: string): void;
    onSubmit(): void;
    toggleCaseSensitive(): void;
    toggleOpen(): void;
    toggleRegex(): void;
  };
  state: {
    caseSensitive: boolean;
    open: boolean;
    query: string;
    regex: boolean;
  };
}

export function useTerminalFindController(input: {
  getRuntime: () => TerminalFindRuntime | null;
}): TerminalFindController {
  const [open, setOpen] = useState(false);
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [query, setQuery] = useState("");
  const [regex, setRegex] = useState(false);

  const resolveFindOptions = () => ({
    caseSensitive,
    regex
  });

  return {
    actions: {
      close() {
        setOpen(false);
      },
      findNext() {
        input.getRuntime()?.findNext(query, resolveFindOptions());
      },
      findPrevious() {
        input.getRuntime()?.findPrevious(query, resolveFindOptions());
      },
      open() {
        setOpen(true);
      },
      onQueryChange(nextQuery) {
        setQuery(nextQuery);
        if (!nextQuery) {
          return;
        }
        input.getRuntime()?.findNext(nextQuery, {
          ...resolveFindOptions(),
          incremental: true
        });
      },
      onSubmit() {
        input.getRuntime()?.findNext(query, resolveFindOptions());
      },
      toggleCaseSensitive() {
        setCaseSensitive((enabled) => !enabled);
      },
      toggleOpen() {
        setOpen((enabled) => !enabled);
      },
      toggleRegex() {
        setRegex((enabled) => !enabled);
      }
    },
    state: {
      caseSensitive,
      open,
      query,
      regex
    }
  };
}
