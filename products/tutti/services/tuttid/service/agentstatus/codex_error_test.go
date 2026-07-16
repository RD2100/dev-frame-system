package agentstatus

import "testing"

func TestClassifyCodexRuntimeError(t *testing.T) {
	cases := []struct {
		name string
		msg  string
		want CodexErrorCode
		ok   bool
	}{
		{
			name: "server rejects old version",
			msg:  `{"type":"error","status":400,"error":{"type":"invalid_request_error","message":"The 'gpt-5.5' model requires a newer version of Codex. Please upgrade to the latest app or CLI and try again."}}`,
			want: CodexErrVersionTooOld,
			ok:   true,
		},
		{
			name: "spawn enoent in platform subpackage",
			msg:  "Error: spawn /Users/didi/.nvm/versions/node/v22.22.0/lib/node_modules/@openai/codex/node_modules/@openai/codex-darwin-arm64/codex ENOENT",
			want: CodexErrPlatformPkgIncomplete,
			ok:   true,
		},
		{
			name: "spawn enoent bare codex not on path",
			msg:  "Error: spawn codex ENOENT",
			want: CodexErrCLIMissing,
			ok:   true,
		},
		{
			name: "not logged in",
			msg:  "Not logged in · Please run /login",
			want: CodexErrAuthRequired,
			ok:   true,
		},
		{
			name: "network timeout",
			msg:  "request to https://registry.npmjs.org failed, reason: ETIMEDOUT",
			want: CodexErrNetwork,
			ok:   true,
		},
		{
			name: "unknown",
			msg:  "something entirely unexpected happened",
			want: "",
			ok:   false,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, ok := classifyCodexRuntimeError(tc.msg)
			if ok != tc.ok || got != tc.want {
				t.Fatalf("classifyCodexRuntimeError(%q)=(%q,%v), want (%q,%v)", tc.msg, got, ok, tc.want, tc.ok)
			}
		})
	}
}
