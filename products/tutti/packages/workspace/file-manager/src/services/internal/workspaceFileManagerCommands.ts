import type {
  WorkspaceFileManagerHostFallbackAction,
  WorkspaceFileManagerHostActionResult
} from "../workspaceFileManagerHostTypes.ts";
import type {
  WorkspaceFileEntry,
  WorkspaceFileLocationSection,
  WorkspaceFileManagerContextMenuState,
  WorkspaceFileManagerPersistedState,
  WorkspaceFileOpenWithApplication
} from "../workspaceFileManagerTypes.ts";
import type { WorkspaceFileManagerI18nRuntime } from "../../i18n/workspaceFileManagerI18n.ts";

export interface WorkspaceFileManagerCommands {
  applyRevealIntent(
    intent: {
      mode?: "reveal" | "open-directory";
      path: string;
      requestID: string;
    } | null
  ): Promise<void>;
  closeContextMenu(): void;
  closeCreateDialog(): void;
  closeDeleteDialog(): void;
  cancelInlineRename(): void;
  closeTransientUi(): void;
  closeUnsupportedDialog(): void;
  closeImportConflictDialog(): void;
  confirmCreateDialog(): Promise<void>;
  confirmDeleteDialog(): Promise<void>;
  clearInlineRenameValidation(): void;
  confirmInlineRename(newName: string): Promise<boolean>;
  copyToClipboard(entry: WorkspaceFileEntry): Promise<void>;
  confirmImportConflict(): Promise<void>;
  createDirectory(path: string): Promise<void>;
  createFile(path: string): Promise<void>;
  deleteSelected(): Promise<void>;
  decrementDragDepth(): void;
  goBack(): Promise<void>;
  goForward(): Promise<void>;
  getPersistedState(): WorkspaceFileManagerPersistedState;
  handleActivationFallbackAction(
    action: WorkspaceFileManagerHostFallbackAction
  ): Promise<void>;
  incrementDragDepth(): void;
  initialize(): Promise<void>;
  loadDirectory(path?: string): Promise<void>;
  openContextMenu(input: WorkspaceFileManagerContextMenuState): void;
  openCreateDirectoryDialog(): void;
  openCreateFileDialog(): void;
  openDeleteDialog(entry: WorkspaceFileEntry): void;
  startInlineRename(entry: WorkspaceFileEntry): void;
  toggleDirectoryExpanded(entry: WorkspaceFileEntry): Promise<void>;
  getCachedOpenWithApplications(
    entry: WorkspaceFileEntry
  ): WorkspaceFileOpenWithApplication[] | null;
  listOpenWithApplications(
    entry: WorkspaceFileEntry
  ): Promise<WorkspaceFileOpenWithApplication[]>;
  openEntry(entry: WorkspaceFileEntry): Promise<void>;
  openFileWithApplication(
    entry: WorkspaceFileEntry,
    applicationPath: string
  ): Promise<void>;
  openFileInAppBrowser(entry: WorkspaceFileEntry): Promise<void>;
  openFileInDefaultBrowser(entry: WorkspaceFileEntry): Promise<void>;
  openFileInFileViewer(entry: WorkspaceFileEntry): Promise<void>;
  openFileInSystemDefault(entry: WorkspaceFileEntry): Promise<void>;
  openFileWithOtherApplication(entry: WorkspaceFileEntry): Promise<void>;
  revealEntry(entry: WorkspaceFileEntry): Promise<void>;
  exportEntry(
    entry: WorkspaceFileEntry
  ): Promise<WorkspaceFileManagerHostActionResult>;
  importDroppedFiles(
    dataTransfer: Pick<DataTransfer, "files" | "items">,
    targetDirectoryPath: string
  ): Promise<WorkspaceFileManagerHostActionResult>;
  importFiles(
    targetDirectoryPath: string
  ): Promise<WorkspaceFileManagerHostActionResult>;
  moveEntry(
    entry: WorkspaceFileEntry,
    targetDirectoryPath: string
  ): Promise<void>;
  refresh(): Promise<void>;
  revealPath(path: string): Promise<void>;
  resetDragDepth(): void;
  search(query: string): Promise<void>;
  select(path: string | null): void;
  selectLocation(locationId: string): Promise<void>;
  setActive(active: boolean): void;
  setI18nRuntime(copy: WorkspaceFileManagerI18nRuntime): void;
  setLocations(input: {
    defaultLocationId?: string | null;
    sections: WorkspaceFileLocationSection[];
  }): Promise<void>;
  updateCreateDialogName(name: string): void;
}
