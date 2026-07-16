import type {
  IssueManagerIssueDetail,
  IssueManagerPriority,
  IssueManagerStatusCounts,
  IssueManagerTaskDetail
} from "../../contracts/index.ts";

export interface IssueDraft {
  content: string;
  title: string;
}

export interface TaskDraft {
  content: string;
  priority: IssueManagerPriority;
  title: string;
}

export interface AsyncCollectionState<TValue> {
  error: string | null;
  hasResolved?: boolean;
  isLoading: boolean;
  statusCounts?: IssueManagerStatusCounts;
  value: TValue;
}

export type IssueManagerNotificationTone = "default" | "destructive";

export interface IssueManagerNotificationState {
  id: number;
  title: string;
  tone: IssueManagerNotificationTone;
}

export interface IssueManagerDetailCollections {
  issueDetail: AsyncCollectionState<IssueManagerIssueDetail | null>;
  taskDetail: AsyncCollectionState<IssueManagerTaskDetail | null>;
}
