import type { TuttidClient } from "@tutti-os/client-tuttid-ts";
import type {
  IssueManagerFileAdapter,
  IssueManagerFileReference
} from "@tutti-os/workspace-issue-manager/contracts";
import type { DesktopHostFilesApi } from "@preload/types";
import {
  createDesktopWorkspaceFileReferenceAdapter,
  mapDesktopWorkspaceFileReferenceEntry
} from "../../../workspace-file-manager/services/createDesktopWorkspaceFileReferenceAdapter.ts";

export function createDesktopIssueManagerFileAdapter(input: {
  hostFilesApi: DesktopHostFilesApi;
  tuttidClient: TuttidClient;
  openWorkspaceFileManager?: (
    reference: IssueManagerFileReference
  ) => Promise<boolean> | boolean;
  workspaceId: string;
}): IssueManagerFileAdapter {
  const { hostFilesApi, tuttidClient } = input;
  const fileReferenceAdapter =
    createDesktopWorkspaceFileReferenceAdapter(input);

  return {
    ...fileReferenceAdapter,
    async openReference(reference) {
      const trimmedPath = reference.path.trim();
      if (
        trimmedPath &&
        !isTerminalReferencePath(trimmedPath) &&
        input.openWorkspaceFileManager
      ) {
        const opened = await input.openWorkspaceFileManager({
          ...reference,
          path: trimmedPath
        });
        if (opened) {
          return;
        }
      }

      if (isLocalAbsolutePath(trimmedPath)) {
        await hostFilesApi.openTerminalLink({
          path: trimmedPath,
          workspaceID: input.workspaceId
        });
        return;
      }

      await fileReferenceAdapter.openReference?.(reference);
    },
    async requestUpload({ mode, targetDirectoryPath, workspaceId }) {
      const sourcePaths =
        mode === "folder"
          ? await pickDirectoryPaths(hostFilesApi)
          : await hostFilesApi.selectUploadFiles();
      if (sourcePaths.length === 0) {
        return [];
      }

      const preflight = await tuttidClient.preflightUploadWorkspaceFiles(
        workspaceId,
        {
          sourcePaths,
          targetDirectoryPath
        }
      );
      if (
        preflight.conflicts.some(
          (conflict) => conflict.kind === "type_mismatch"
        )
      ) {
        throw new Error("issue_manager.upload_type_conflict");
      }

      const response = await tuttidClient.uploadWorkspaceFiles(workspaceId, {
        overwrite: preflight.conflicts.length > 0 ? true : undefined,
        sourcePaths,
        targetDirectoryPath
      });
      return response.entries.map((entry) =>
        mapDesktopWorkspaceFileReferenceEntry(entry)
      );
    }
  };
}

async function pickDirectoryPaths(
  hostFilesApi: DesktopHostFilesApi
): Promise<string[]> {
  const selection = await hostFilesApi.selectDirectory();
  return selection ? [selection] : [];
}

function isTerminalReferencePath(path: string): boolean {
  return path === "~" || path.startsWith("~/");
}

function isLocalAbsolutePath(path: string): boolean {
  const normalized = path.replaceAll("\\", "/");
  const isWorkspaceLogicalPath =
    normalized === "/workspace" || normalized.startsWith("/workspace/");
  return (
    !isWorkspaceLogicalPath &&
    (normalized.startsWith("/") || /^[A-Za-z]:\//.test(normalized))
  );
}
