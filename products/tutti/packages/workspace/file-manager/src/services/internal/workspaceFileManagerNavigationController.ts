import {
  normalizeWorkspaceFilePath,
  sortWorkspaceEntries,
  workspaceFileDirectory,
  workspaceFilePathHasHiddenSegment
} from "../workspaceFileManagerModel.ts";
import type { WorkspaceFileManagerHost } from "../workspaceFileManagerHost.interface.ts";
import type { WorkspaceFileManagerState } from "../workspaceFileManagerTypes.ts";

export interface WorkspaceFileManagerNavigationControllerInput {
  host: WorkspaceFileManagerHost;
  resolveErrorMessage: (error: unknown) => string;
  store: WorkspaceFileManagerState;
}

export class WorkspaceFileManagerNavigationController {
  private readonly host: WorkspaceFileManagerHost;
  private readonly resolveErrorMessage: (error: unknown) => string;
  private readonly store: WorkspaceFileManagerState;
  private requestSeq = 0;

  constructor(input: WorkspaceFileManagerNavigationControllerInput) {
    this.host = input.host;
    this.resolveErrorMessage = input.resolveErrorMessage;
    this.store = input.store;
  }

  async goBack(): Promise<void> {
    const previous = this.store.navigationBackStack.pop();
    if (!previous) {
      return;
    }
    this.store.navigationForwardStack.push(this.store.currentDirectoryPath);
    await this.replaceDirectory(previous);
  }

  async goForward(): Promise<void> {
    const next = this.store.navigationForwardStack.pop();
    if (!next) {
      return;
    }
    this.store.navigationBackStack.push(this.store.currentDirectoryPath);
    await this.replaceDirectory(next);
  }

  async loadDirectory(path = this.store.currentDirectoryPath): Promise<void> {
    const normalizedPath = normalizeWorkspaceFilePath(path, this.store.root);
    const requestID = ++this.requestSeq;
    this.store.isLoading = true;
    this.store.error = null;

    try {
      const listing = await this.host.listDirectory({
        includeHidden: workspaceFilePathHasHiddenSegment(normalizedPath),
        path: this.resolveRequestPath(normalizedPath),
        workspaceID: this.store.workspaceID
      });
      if (requestID !== this.requestSeq) {
        return;
      }

      const previousDirectoryPath = this.store.currentDirectoryPath;
      if (
        previousDirectoryPath !== listing.directoryPath &&
        previousDirectoryPath !== "/"
      ) {
        this.store.navigationBackStack.push(this.store.currentDirectoryPath);
        this.store.navigationForwardStack = [];
      }
      this.store.root = normalizeWorkspaceFilePath(listing.root);
      this.store.currentDirectoryPath = listing.directoryPath;
      this.store.entries = sortWorkspaceEntries(listing.entries);
      this.store.directoryExpansionByPath = {};
      this.store.expandedDirectoryPaths = {};
      this.store.selectedPath = null;
    } catch (error) {
      if (requestID === this.requestSeq) {
        this.store.error = this.resolveErrorMessage(error);
      }
    } finally {
      if (requestID === this.requestSeq) {
        this.store.isLoading = false;
      }
    }
  }

  async refresh(): Promise<void> {
    await this.loadDirectory(this.store.currentDirectoryPath);
  }

  async revealPath(path: string): Promise<void> {
    const normalizedPath = normalizeWorkspaceFilePath(path, this.store.root);
    const directoryPath = workspaceFileDirectory(
      normalizedPath,
      this.store.root
    );
    const requestID = ++this.requestSeq;
    this.store.isLoading = true;
    this.store.error = null;

    try {
      const listing = await this.host.listDirectory({
        includeHidden: workspaceFilePathHasHiddenSegment(normalizedPath),
        path: this.resolveRequestPath(directoryPath),
        workspaceID: this.store.workspaceID
      });
      if (requestID !== this.requestSeq) {
        return;
      }

      const previousDirectoryPath = this.store.currentDirectoryPath;
      if (
        previousDirectoryPath !== listing.directoryPath &&
        previousDirectoryPath !== "/"
      ) {
        this.store.navigationBackStack.push(this.store.currentDirectoryPath);
        this.store.navigationForwardStack = [];
      }
      this.store.root = normalizeWorkspaceFilePath(listing.root);
      this.store.currentDirectoryPath = listing.directoryPath;
      this.store.entries = sortWorkspaceEntries(listing.entries);
      this.store.directoryExpansionByPath = {};
      this.store.expandedDirectoryPaths = {};
      this.store.selectedPath = normalizedPath;
    } catch (error) {
      if (requestID === this.requestSeq) {
        this.store.error = this.resolveErrorMessage(error);
      }
    } finally {
      if (requestID === this.requestSeq) {
        this.store.isLoading = false;
      }
    }
  }

  private async replaceDirectory(path: string): Promise<void> {
    const normalizedPath = normalizeWorkspaceFilePath(path, this.store.root);
    const requestID = ++this.requestSeq;
    this.store.isLoading = true;
    this.store.error = null;
    try {
      const listing = await this.host.listDirectory({
        includeHidden: workspaceFilePathHasHiddenSegment(normalizedPath),
        path: this.resolveRequestPath(normalizedPath),
        workspaceID: this.store.workspaceID
      });
      if (requestID !== this.requestSeq) {
        return;
      }
      this.store.root = normalizeWorkspaceFilePath(listing.root);
      this.store.currentDirectoryPath = listing.directoryPath;
      this.store.entries = sortWorkspaceEntries(listing.entries);
      this.store.directoryExpansionByPath = {};
      this.store.expandedDirectoryPaths = {};
      this.store.selectedPath = null;
    } catch (error) {
      if (requestID === this.requestSeq) {
        this.store.error = this.resolveErrorMessage(error);
      }
    } finally {
      if (requestID === this.requestSeq) {
        this.store.isLoading = false;
      }
    }
  }

  private resolveRequestPath(path: string): string {
    if (this.store.root === "/" && path === "/") {
      return "";
    }
    return path;
  }
}
