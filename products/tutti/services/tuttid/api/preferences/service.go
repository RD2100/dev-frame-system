package preferences

import (
	"context"

	preferencesbiz "github.com/tutti-os/tutti/services/tuttid/biz/preferences"
	preferencesservice "github.com/tutti-os/tutti/services/tuttid/service/preferences"
)

type Service interface {
	Get(context.Context) (preferencesbiz.DesktopPreferences, error)
	Put(context.Context, preferencesservice.PutInput) (preferencesbiz.DesktopPreferences, error)
}
