package account

import (
	"crypto/sha256"
	"encoding/hex"
	"strings"
)

func accountLogHash(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return ""
	}
	sum := sha256.Sum256([]byte(value))
	return hex.EncodeToString(sum[:])[:12]
}
