import type {
  IssueManagerAddContextRefsInput,
  IssueManagerContextRef,
  IssueManagerRemoveContextRefInput
} from "./index.ts";

const issueContextRef: IssueManagerContextRef = {
  contextRefId: "context-ref-1",
  workspaceId: "workspace-1",
  issueId: "issue-1",
  parentKind: "issue",
  refType: "file",
  path: "/workspace/issue.md",
  displayName: "issue.md"
};

const taskContextRef: IssueManagerContextRef = {
  contextRefId: "context-ref-2",
  workspaceId: "workspace-1",
  issueId: "issue-1",
  taskId: "task-1",
  parentKind: "task",
  refType: "file",
  path: "/workspace/task.md",
  displayName: "task.md"
};

const issueRemoveInput: IssueManagerRemoveContextRefInput = {
  workspaceId: "workspace-1",
  issueId: "issue-1",
  contextRefId: "context-ref-1",
  parentKind: "issue"
};

const taskRemoveInput: IssueManagerRemoveContextRefInput = {
  workspaceId: "workspace-1",
  issueId: "issue-1",
  taskId: "task-1",
  contextRefId: "context-ref-2",
  parentKind: "task"
};

const issueAddInput: IssueManagerAddContextRefsInput = {
  workspaceId: "workspace-1",
  issueId: "issue-1",
  parentKind: "issue",
  refs: []
};

const taskAddInput: IssueManagerAddContextRefsInput = {
  workspaceId: "workspace-1",
  issueId: "issue-1",
  taskId: "task-1",
  parentKind: "task",
  refs: []
};

const invalidIssueContextRef: IssueManagerContextRef = {
  contextRefId: "context-ref-3",
  workspaceId: "workspace-1",
  issueId: "issue-1",
  parentKind: "issue",
  refType: "file",
  path: "/workspace/issue.md",
  displayName: "issue.md",
  // @ts-expect-error issue-scoped refs do not carry a task id.
  taskId: "task-1"
};

const invalidTaskRemoveInput: IssueManagerRemoveContextRefInput = {
  workspaceId: "workspace-1",
  issueId: "issue-1",
  contextRefId: "context-ref-4",
  parentKind: "task",
  // @ts-expect-error task-scoped refs require a concrete task id.
  taskId: undefined
};

const invalidTaskAddInput: IssueManagerAddContextRefsInput = {
  workspaceId: "workspace-1",
  issueId: "issue-1",
  parentKind: "task",
  refs: [],
  // @ts-expect-error task-scoped refs require a concrete task id.
  taskId: undefined
};

void [
  issueContextRef,
  taskContextRef,
  issueRemoveInput,
  taskRemoveInput,
  issueAddInput,
  taskAddInput,
  invalidIssueContextRef,
  invalidTaskRemoveInput,
  invalidTaskAddInput
];
