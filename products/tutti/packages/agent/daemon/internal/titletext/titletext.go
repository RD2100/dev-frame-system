package titletext

import (
	"regexp"
	"strings"
)

var markdownLinkPattern = regexp.MustCompile(`\[([^\]]+)\]\([^)]+\)`)

func Normalize(value string) string {
	humanized := markdownLinkPattern.ReplaceAllString(value, "$1")
	return strings.Join(strings.Fields(strings.TrimSpace(humanized)), " ")
}
