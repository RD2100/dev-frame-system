package workspace

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"strings"
)

const appServerTokenPrefix = "tutti-app-v1."

func AppServerToken(accessToken string, workspaceID string, appID string) string {
	secret := strings.TrimSpace(accessToken)
	workspaceID = strings.TrimSpace(workspaceID)
	appID = strings.TrimSpace(appID)
	if secret == "" || workspaceID == "" || appID == "" {
		return ""
	}
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(workspaceID))
	mac.Write([]byte{0})
	mac.Write([]byte(appID))
	sum := mac.Sum(nil)
	return appServerTokenPrefix + base64.RawURLEncoding.EncodeToString(sum)
}
