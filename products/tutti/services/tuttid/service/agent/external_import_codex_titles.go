package agent

import (
	"context"
	"database/sql"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

// codexThreadTitles reads the Codex app-server state database and returns a map
// of thread id (the rollout session id) to its generated conversation title.
//
// Codex keeps the human-readable title in `state_<n>.sqlite` (table `threads`,
// column `title`) rather than in the rollout transcript, so importing the title
// requires reading that DB. The schema is versioned and undocumented, so every
// failure path degrades gracefully to an empty map and the caller falls back to
// the message-derived title.
func codexThreadTitles(codexHome string) map[string]string {
	titles := map[string]string{}
	codexHome = strings.TrimSpace(codexHome)
	if codexHome == "" {
		return titles
	}
	dbPath := codexStateDBPath(codexHome)
	if dbPath == "" {
		return titles
	}

	// Open read-only with a short busy timeout so a live Codex process holding
	// the write lock never blocks the import scan. Build the file: URI via
	// url.URL so paths containing spaces or other reserved characters are
	// percent-encoded rather than corrupting the DSN.
	dsn := (&url.URL{Scheme: "file", Path: dbPath, RawQuery: "mode=ro&_pragma=busy_timeout(2000)"}).String()
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return titles
	}
	defer db.Close()
	db.SetMaxOpenConns(1)

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	rows, err := db.QueryContext(ctx, "SELECT id, title FROM threads WHERE title IS NOT NULL AND title != ''")
	if err != nil {
		return titles
	}
	defer rows.Close()
	for rows.Next() {
		var id, title string
		if err := rows.Scan(&id, &title); err != nil {
			continue
		}
		id = strings.TrimSpace(id)
		title = strings.TrimSpace(title)
		if id != "" && title != "" {
			titles[id] = title
		}
	}
	return titles
}

// codexStateDBPath returns the highest-versioned state_<n>.sqlite under codexHome.
func codexStateDBPath(codexHome string) string {
	matches, err := filepath.Glob(filepath.Join(codexHome, "state_*.sqlite"))
	if err != nil {
		return ""
	}
	best := ""
	bestVersion := -1
	for _, match := range matches {
		if info, err := os.Stat(match); err != nil || info.IsDir() {
			continue
		}
		name := strings.TrimSuffix(strings.TrimPrefix(filepath.Base(match), "state_"), ".sqlite")
		version, err := strconv.Atoi(name)
		if err != nil {
			continue
		}
		if version > bestVersion {
			bestVersion = version
			best = match
		}
	}
	return best
}
