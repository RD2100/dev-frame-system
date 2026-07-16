package workspaceissues

import "errors"

var (
	ErrContextRefAlreadyExists = errors.New("issue context reference already exists")
	ErrContextRefNotFound      = errors.New("issue context reference not found")
	ErrInvalidArgument         = errors.New("issue manager argument is invalid")
	ErrIssueAlreadyExists      = errors.New("issue already exists")
	ErrIssueNotFound           = errors.New("issue not found")
	ErrRunAlreadyExists        = errors.New("issue task run already exists")
	ErrRunNotFound             = errors.New("issue task run not found")
	ErrStoreNotConfigured      = errors.New("issue manager store is not configured")
	ErrTaskAlreadyExists       = errors.New("issue task already exists")
	ErrTaskNotFound            = errors.New("issue task not found")
	ErrTopicAlreadyExists      = errors.New("issue topic already exists")
	ErrTopicNotEmpty           = errors.New("issue topic is not empty")
	ErrTopicNotFound           = errors.New("issue topic not found")
	ErrWorkspaceNotFound       = errors.New("workspace not found")
)
