package workbenchservice

import "errors"

var ErrInvalidWorkbenchSnapshot = errors.New("invalid workbench snapshot")
var ErrWorkbenchStoreNotConfigured = errors.New("workbench store is not configured")
var ErrWorkbenchSnapshotNotFound = errors.New("workbench snapshot not found")
