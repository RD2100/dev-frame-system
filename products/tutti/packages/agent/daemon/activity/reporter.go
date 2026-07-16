package agentsessionstore

import "context"

type ActivityReporter interface {
	Report(ctx context.Context, input ReportActivityInput) error
}

type SessionActivityReporter interface {
	ReportSessionState(context.Context, ReportSessionStateInput) (ReportSessionStateReply, error)
	ReportSessionMessages(context.Context, ReportSessionMessagesInput) (ReportSessionMessagesReply, error)
}
