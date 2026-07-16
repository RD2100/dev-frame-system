package workspaceissues

import (
	"context"
	"strings"
)

func (s Service) ListTopics(ctx context.Context, workspaceID string) (TopicList, error) {
	store, err := s.store()
	if err != nil {
		return TopicList{}, err
	}
	workspaceID = strings.TrimSpace(workspaceID)
	if workspaceID == "" {
		return TopicList{}, ErrInvalidArgument
	}
	return store.ListTopics(ctx, workspaceID)
}

func (s Service) CreateTopic(ctx context.Context, input CreateTopicInput) (Topic, error) {
	store, err := s.store()
	if err != nil {
		return Topic{}, err
	}
	workspaceID := strings.TrimSpace(input.WorkspaceID)
	actorUserID := strings.TrimSpace(input.ActorUserID)
	title := strings.TrimSpace(input.Title)
	if workspaceID == "" || actorUserID == "" || title == "" {
		return Topic{}, ErrInvalidArgument
	}
	now := s.nowUnixMS()
	topic := Topic{
		TopicID:              s.resolveID(IDKindTopic, input.TopicID),
		WorkspaceID:          workspaceID,
		Title:                title,
		Summary:              strings.TrimSpace(input.Summary),
		LastActivityAtUnixMS: now,
		CreatedAtUnixMS:      now,
		UpdatedAtUnixMS:      now,
	}
	if topic.TopicID == "" {
		return Topic{}, ErrInvalidArgument
	}
	return store.CreateTopic(ctx, topic)
}

func (s Service) UpdateTopic(ctx context.Context, input UpdateTopicInput) (Topic, error) {
	store, err := s.store()
	if err != nil {
		return Topic{}, err
	}
	workspaceID := strings.TrimSpace(input.WorkspaceID)
	topicID := strings.TrimSpace(input.TopicID)
	if workspaceID == "" || topicID == "" || strings.TrimSpace(input.ActorUserID) == "" {
		return Topic{}, ErrInvalidArgument
	}
	topic, err := store.GetTopic(ctx, workspaceID, topicID)
	if err != nil {
		return Topic{}, err
	}
	if input.HasTitle {
		title := strings.TrimSpace(input.Title)
		if title == "" {
			return Topic{}, ErrInvalidArgument
		}
		topic.Title = title
	}
	if input.HasSummary {
		topic.Summary = strings.TrimSpace(input.Summary)
	}
	if input.HasPinned {
		if input.Pinned && topic.PinnedAtUnixMS == 0 {
			topic.PinnedAtUnixMS = s.nowUnixMS()
		}
		if !input.Pinned {
			topic.PinnedAtUnixMS = 0
		}
	}
	topic.UpdatedAtUnixMS = s.nowUnixMS()
	return store.UpdateTopic(ctx, topic)
}

func (s Service) DeleteTopic(ctx context.Context, workspaceID string, topicID string, actorUserID string) (bool, error) {
	store, err := s.store()
	if err != nil {
		return false, err
	}
	workspaceID = strings.TrimSpace(workspaceID)
	topicID = strings.TrimSpace(topicID)
	if workspaceID == "" || topicID == "" || strings.TrimSpace(actorUserID) == "" {
		return false, ErrInvalidArgument
	}
	topic, err := store.GetTopic(ctx, workspaceID, topicID)
	if err != nil {
		return false, err
	}
	if topic.IsDefault || topic.TopicID == DefaultTopicID {
		return false, ErrInvalidArgument
	}
	issues, err := store.ListIssues(ctx, IssueListFilter{
		WorkspaceID: workspaceID,
		TopicID:     topicID,
		PageSize:    1,
	})
	if err != nil {
		return false, err
	}
	if issues.TotalCount > 0 {
		return false, ErrTopicNotEmpty
	}
	return store.DeleteTopic(ctx, workspaceID, topicID)
}
