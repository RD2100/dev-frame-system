import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import test from "node:test";

const issueSectionsSource = readFileSync(
  new URL("./IssueManagerIssueSections.tsx", import.meta.url),
  "utf8"
);
const subtaskBoardSource = readFileSync(
  new URL("./IssueManagerSubtaskBoard.tsx", import.meta.url),
  "utf8"
);

test("subtask board accepts same-column ordering and allowed status moves", () => {
  assert.match(issueSectionsSource, /onMoveTask=\{onMoveTask\}/);
  assert.match(
    subtaskBoardSource,
    /sourceStatus: IssueManagerSubtaskBoardStatus/
  );
  assert.match(
    subtaskBoardSource,
    /input\.sourceStatus === input\.targetStatus/
  );
  assert.match(
    subtaskBoardSource,
    /function canIssueManagerCrossColumnDropTaskStatus/
  );
  assert.match(
    subtaskBoardSource,
    /targetStatus === "not_started" \|\|[\s\S]*targetStatus === "completed"/
  );
  assert.match(
    subtaskBoardSource,
    /targetStatus === "not_started" \|\|[\s\S]*targetStatus === "pending_acceptance"/
  );
  assert.match(subtaskBoardSource, /draggable/);
  assert.match(subtaskBoardSource, /data-issue-manager-board-card-task-id/);
  assert.match(subtaskBoardSource, /dataset\.issueManagerBoardCardTaskId/);
  assert.match(subtaskBoardSource, /data-task-status-drop-target/);
  assert.match(subtaskBoardSource, /void onMoveTask\(\{/);
  assert.match(subtaskBoardSource, /targetIndex/);
  assert.match(subtaskBoardSource, /targetStatus: status/);
  assert.doesNotMatch(subtaskBoardSource, /hasIssueManagerTaskStatusDragData/);
});

test("subtask board keeps the source card mounted during same-column preview", () => {
  assert.match(
    subtaskBoardSource,
    /function orderIssueManagerTasksForSameColumnDropPreview/
  );
  assert.match(subtaskBoardSource, /const movingTask/);
  assert.match(subtaskBoardSource, /const nextTasks/);
  assert.match(
    subtaskBoardSource,
    /nextTasks\.splice\(targetIndex, 0, movingTask\)/
  );
  assert.match(subtaskBoardSource, /const renderTasks/);
  assert.match(subtaskBoardSource, /isSameColumnDropPreview/);
  assert.match(subtaskBoardSource, /activeDropPreviewDragState/);
  assert.match(subtaskBoardSource, /\{renderTasks\.map\(\(task, index\) =>/);
  assert.doesNotMatch(
    subtaskBoardSource,
    /tasks\.filter\(\(task\) => task\.taskId !== dragState\.taskId\)/
  );
});

test("subtask board keeps drop preview stable during fast in-column drags", () => {
  assert.match(subtaskBoardSource, /function isLeavingIssueManagerBoardColumn/);
  assert.match(
    subtaskBoardSource,
    /event\.currentTarget\.getBoundingClientRect\(\)/
  );
  assert.match(subtaskBoardSource, /event\.clientX >= rect\.left/);
  assert.match(subtaskBoardSource, /event\.clientY <= rect\.bottom/);
});

test("subtask board keeps dropped cards in the target column while status refreshes", () => {
  assert.match(subtaskBoardSource, /type IssueManagerSubtaskOptimisticDrop/);
  assert.match(
    subtaskBoardSource,
    /groupIssueManagerSubtasksByStatus\(tasks, optimisticDrop\)/
  );
  assert.match(subtaskBoardSource, /setOptimisticDrop\(null\)/);
  assert.match(subtaskBoardSource, /onOptimisticDropChange\(\{/);
  assert.match(subtaskBoardSource, /isIssueManagerOptimisticDropSettled/);
  assert.match(subtaskBoardSource, /const optimisticTask = tasks\.find/);
  assert.match(
    subtaskBoardSource,
    /resolveIssueManagerSubtaskBoardStatus\(optimisticTask\.status\) !==[\s\S]*optimisticDrop\.status/
  );
  assert.match(subtaskBoardSource, /return false/);
  assert.match(subtaskBoardSource, /onMoveTask\(\{[\s\S]*\}\)\.catch/);
});

test("subtask board animates pushed cards with reduced-motion support", () => {
  assert.match(subtaskBoardSource, /useIssueManagerBoardLayoutAnimation/);
  assert.match(
    subtaskBoardSource,
    /issueManagerBoardLayoutAnimationDurationMs = 180/
  );
  assert.match(subtaskBoardSource, /getBoundingClientRect/);
  assert.match(subtaskBoardSource, /element\.animate/);
  assert.match(subtaskBoardSource, /didScrollSinceLastLayout/);
  assert.match(subtaskBoardSource, /activeVisualTopByKey/);
  assert.match(subtaskBoardSource, /animation\.cancel\(\)/);
  assert.match(
    subtaskBoardSource,
    /activeVisualTopByKey\.get\(key\) \?\? previousRect\.top/
  );
  assert.match(subtaskBoardSource, /translate3d\(0, \$\{deltaY\}px, 0\)/);
  assert.match(subtaskBoardSource, /prefers-reduced-motion: reduce/);
  assert.match(
    subtaskBoardSource,
    /data-issue-manager-board-layout-item=\{`task:\$\{status\}:\$\{task\.taskId\}`\}/
  );
  assert.doesNotMatch(
    subtaskBoardSource,
    /data-issue-manager-board-layout-item=\{`task:\$\{task\.taskId\}`\}/
  );
});
