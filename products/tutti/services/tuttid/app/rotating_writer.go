package app

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

const logDayLayout = "2006-01-02"

type RotatingFileWriterOptions struct {
	MaxSizeBytes  int64
	MaxBackups    int
	MaxAgeDays    int
	MaxTotalBytes int64
	Now           func() time.Time
}

type RotatingFileWriter struct {
	mu            sync.Mutex
	activePath    string
	dir           string
	rotatedPrefix string
	rotatedSuffix string
	file          *os.File
	currentDay    string
	currentSize   int64
	maxSizeBytes  int64
	maxBackups    int
	maxAgeDays    int
	maxTotalBytes int64
	now           func() time.Time
}

type rotatedLogFile struct {
	path    string
	day     string
	idx     int
	size    int64
	modTime time.Time
}

func NewRotatingFileWriter(path string, opts RotatingFileWriterOptions) (*RotatingFileWriter, error) {
	trimmedPath := strings.TrimSpace(path)
	if trimmedPath == "" {
		return nil, fmt.Errorf("log file path is required")
	}

	absolutePath, err := filepath.Abs(trimmedPath)
	if err != nil {
		return nil, fmt.Errorf("resolve log file path %q: %w", trimmedPath, err)
	}

	dir := filepath.Dir(absolutePath)
	base := filepath.Base(absolutePath)
	prefix, suffix := splitRotatedName(base)

	writer := &RotatingFileWriter{
		activePath:    absolutePath,
		dir:           dir,
		rotatedPrefix: prefix,
		rotatedSuffix: suffix,
		maxSizeBytes:  opts.MaxSizeBytes,
		maxBackups:    opts.MaxBackups,
		maxAgeDays:    opts.MaxAgeDays,
		maxTotalBytes: opts.MaxTotalBytes,
		now:           opts.Now,
	}
	if writer.now == nil {
		writer.now = time.Now
	}

	if err := writer.openActiveLocked(); err != nil {
		return nil, err
	}
	writer.cleanupLocked(dayString(writer.now()))
	return writer, nil
}

func (w *RotatingFileWriter) Write(p []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()

	today := dayString(w.now())
	if err := w.ensureReadyLocked(today, len(p)); err != nil {
		return 0, err
	}

	n, err := w.file.Write(p)
	w.currentSize += int64(n)
	return n, err
}

func (w *RotatingFileWriter) Close() error {
	w.mu.Lock()
	defer w.mu.Unlock()

	if w.file == nil {
		return nil
	}

	err := w.file.Close()
	w.file = nil
	w.currentDay = ""
	w.currentSize = 0
	return err
}

func (w *RotatingFileWriter) Path() string {
	return w.activePath
}

func (w *RotatingFileWriter) ensureReadyLocked(today string, writeLen int) error {
	if w.file == nil {
		if err := w.openActiveLocked(); err != nil {
			return err
		}
	}

	if w.currentSize > 0 && w.currentDay != "" && w.currentDay != today {
		if err := w.rotateActiveLocked(w.currentDay); err != nil {
			return err
		}
	}

	if w.maxSizeBytes > 0 && w.currentSize > 0 && w.currentSize+int64(writeLen) > w.maxSizeBytes {
		if err := w.rotateActiveLocked(today); err != nil {
			return err
		}
	}

	return nil
}

func (w *RotatingFileWriter) rotateActiveLocked(day string) error {
	if w.file != nil {
		if err := w.file.Close(); err != nil {
			return fmt.Errorf("close active log file %q: %w", w.activePath, err)
		}
		w.file = nil
	}

	if w.currentSize > 0 {
		rotatedPath, err := w.nextRotatedPathLocked(day)
		if err != nil {
			return err
		}
		if err := os.Rename(w.activePath, rotatedPath); err != nil {
			if !os.IsNotExist(err) {
				return fmt.Errorf("rotate log file %q to %q: %w", w.activePath, rotatedPath, err)
			}
		}
	}

	if err := w.openActiveLocked(); err != nil {
		return err
	}
	w.cleanupLocked(day)
	return nil
}

func (w *RotatingFileWriter) openActiveLocked() error {
	if err := os.MkdirAll(w.dir, 0o755); err != nil {
		return fmt.Errorf("create log directory %q: %w", w.dir, err)
	}

	file, err := os.OpenFile(w.activePath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return fmt.Errorf("open log file %q: %w", w.activePath, err)
	}

	info, err := file.Stat()
	if err != nil {
		_ = file.Close()
		return fmt.Errorf("stat log file %q: %w", w.activePath, err)
	}

	w.file = file
	w.currentSize = info.Size()
	w.currentDay = dayString(info.ModTime())
	if w.currentSize == 0 {
		w.currentDay = dayString(w.now())
	}

	return nil
}

func (w *RotatingFileWriter) nextRotatedPathLocked(day string) (string, error) {
	entries, err := os.ReadDir(w.dir)
	if err != nil {
		if os.IsNotExist(err) {
			return filepath.Join(w.dir, w.rotatedFileName(day, 0)), nil
		}
		return "", fmt.Errorf("list log directory %q: %w", w.dir, err)
	}

	used := map[int]bool{}
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}

		parsedDay, idx, ok := w.parseRotatedName(entry.Name())
		if ok && parsedDay == day {
			used[idx] = true
		}
	}

	for idx := 0; ; idx++ {
		if !used[idx] {
			return filepath.Join(w.dir, w.rotatedFileName(day, idx)), nil
		}
	}
}

func (w *RotatingFileWriter) cleanupLocked(today string) {
	files := w.collectCleanupCandidatesLocked()
	if len(files) == 0 {
		return
	}

	removePaths := map[string]bool{}
	if w.maxAgeDays > 0 {
		cutoff := cutoffDay(w.now(), w.maxAgeDays)
		for _, file := range files {
			if file.day != today && file.day < cutoff {
				removePaths[file.path] = true
			}
		}
	}

	if w.maxBackups >= 0 {
		remaining := make([]rotatedLogFile, 0, len(files))
		for _, file := range files {
			if !removePaths[file.path] {
				remaining = append(remaining, file)
			}
		}
		sort.Slice(remaining, func(i, j int) bool {
			if remaining[i].day != remaining[j].day {
				return remaining[i].day > remaining[j].day
			}
			return remaining[i].idx > remaining[j].idx
		})
		for i := w.maxBackups; i < len(remaining); i++ {
			removePaths[remaining[i].path] = true
		}
	}

	for path := range removePaths {
		_ = os.Remove(path)
	}

	w.pruneDirectoryBudgetLocked()
}

func (w *RotatingFileWriter) collectCleanupCandidatesLocked() []rotatedLogFile {
	entries, err := os.ReadDir(w.dir)
	if err != nil {
		return nil
	}

	files := make([]rotatedLogFile, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}

		day, idx, ok := w.parseRotatedName(entry.Name())
		if !ok {
			continue
		}

		info, err := entry.Info()
		if err != nil {
			continue
		}
		files = append(files, rotatedLogFile{
			path:    filepath.Join(w.dir, entry.Name()),
			day:     day,
			idx:     idx,
			size:    info.Size(),
			modTime: info.ModTime(),
		})
	}

	return files
}

func (w *RotatingFileWriter) pruneDirectoryBudgetLocked() {
	if w.maxTotalBytes <= 0 {
		return
	}

	entries, err := os.ReadDir(w.dir)
	if err != nil {
		return
	}

	type logFile struct {
		path      string
		size      int64
		modTime   time.Time
		rotatable bool
	}

	files := make([]logFile, 0, len(entries))
	var total int64
	for _, entry := range entries {
		if entry.IsDir() || !isManagedLogFileName(entry.Name()) {
			continue
		}

		info, err := entry.Info()
		if err != nil {
			continue
		}

		path := filepath.Join(w.dir, entry.Name())
		total += info.Size()
		files = append(files, logFile{
			path:      path,
			size:      info.Size(),
			modTime:   info.ModTime(),
			rotatable: isDateIndexedLogFileName(entry.Name()),
		})
	}

	if total <= w.maxTotalBytes {
		return
	}

	sort.Slice(files, func(i, j int) bool {
		return files[i].modTime.Before(files[j].modTime)
	})
	for _, file := range files {
		if !file.rotatable {
			continue
		}
		if err := os.Remove(file.path); err == nil {
			total -= file.size
		}
		if total <= w.maxTotalBytes {
			return
		}
	}
}

func (w *RotatingFileWriter) rotatedFileName(day string, idx int) string {
	if idx <= 0 {
		return fmt.Sprintf("%s.%s%s", w.rotatedPrefix, day, w.rotatedSuffix)
	}
	return fmt.Sprintf("%s.%s.%d%s", w.rotatedPrefix, day, idx, w.rotatedSuffix)
}

func (w *RotatingFileWriter) parseRotatedName(name string) (string, int, bool) {
	if !strings.HasPrefix(name, w.rotatedPrefix+".") || !strings.HasSuffix(name, w.rotatedSuffix) {
		return "", 0, false
	}

	trimmed := strings.TrimSuffix(strings.TrimPrefix(name, w.rotatedPrefix+"."), w.rotatedSuffix)
	parts := strings.Split(trimmed, ".")
	if len(parts) == 0 || len(parts) > 2 {
		return "", 0, false
	}

	day := parts[0]
	if _, err := time.Parse(logDayLayout, day); err != nil {
		return "", 0, false
	}

	if len(parts) == 1 {
		return day, 0, true
	}

	idx, err := strconv.Atoi(parts[1])
	if err != nil || idx < 1 {
		return "", 0, false
	}

	return day, idx, true
}

func splitRotatedName(base string) (string, string) {
	ext := filepath.Ext(base)
	if ext == "" {
		return base, ""
	}
	return strings.TrimSuffix(base, ext), ext
}

func dayString(t time.Time) string {
	return t.Format(logDayLayout)
}

func cutoffDay(now time.Time, maxAgeDays int) string {
	if maxAgeDays <= 0 {
		return dayString(now)
	}
	return dayString(now.AddDate(0, 0, -maxAgeDays))
}

func isManagedLogFileName(name string) bool {
	return strings.HasSuffix(name, ".log")
}

func isDateIndexedLogFileName(name string) bool {
	base := strings.TrimSuffix(name, ".log")
	lastDot := strings.LastIndex(base, ".")
	if lastDot < 0 {
		return false
	}

	maybeDate := base[lastDot+1:]
	if _, err := time.Parse(logDayLayout, maybeDate); err == nil {
		return true
	}

	secondLastDot := strings.LastIndex(base[:lastDot], ".")
	if secondLastDot < 0 {
		return false
	}

	maybeDate = base[secondLastDot+1 : lastDot]
	if _, err := time.Parse(logDayLayout, maybeDate); err != nil {
		return false
	}

	_, err := strconv.Atoi(base[lastDot+1:])
	return err == nil
}
