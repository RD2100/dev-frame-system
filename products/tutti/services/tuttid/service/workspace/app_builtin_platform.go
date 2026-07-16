package workspace

import (
	"fmt"

	builtinapps "github.com/tutti-os/tutti/services/tuttid/builtin-apps"
)

func isBuiltinSupportedOnPlatform(dist builtinapps.Distribution, goos string, goarch string) bool {
	if len(dist.Platforms) == 0 {
		return true
	}
	target := fmt.Sprintf("%s/%s", goos, goarch)
	for _, p := range dist.Platforms {
		if p == target {
			return true
		}
	}
	return false
}
