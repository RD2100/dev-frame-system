package workspace

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

type bootstrapResolved struct {
	path          string
	usePowerShell bool
}

func resolveBootstrapPath(packageDir string, bootstrap string) (bootstrapResolved, error) {
	return resolveBootstrapPathForPlatform(packageDir, bootstrap, runtime.GOOS)
}

func resolveBootstrapPathForPlatform(packageDir string, bootstrap string, goos string) (bootstrapResolved, error) {
	bootstrap = filepath.Clean(bootstrap)
	if bootstrap == "." || bootstrap == "" {
		return bootstrapResolved{}, fmt.Errorf("bootstrap path is empty")
	}
	if filepath.IsAbs(bootstrap) {
		return bootstrapResolved{}, fmt.Errorf("bootstrap path must be a relative package path: %q", bootstrap)
	}

	absPackageDir, absErr := filepath.Abs(packageDir)
	if absErr != nil {
		return bootstrapResolved{}, fmt.Errorf("resolve package directory: %w", absErr)
	}
	realPackageDir, evalErr := filepath.EvalSymlinks(absPackageDir)
	if evalErr != nil {
		realPackageDir = absPackageDir
	}

	candidate := filepath.Join(realPackageDir, bootstrap)
	rel, relErr := filepath.Rel(realPackageDir, candidate)
	if relErr != nil || isRelPathEscaping(rel) {
		return bootstrapResolved{}, fmt.Errorf("bootstrap path must be a relative package path: %q", bootstrap)
	}

	if goos == "windows" {
		ext := strings.ToLower(filepath.Ext(bootstrap))
		return resolveWindowsBootstrap(realPackageDir, bootstrap, candidate, ext)
	}

	info, statErr := os.Stat(candidate)
	if statErr != nil {
		return bootstrapResolved{}, fmt.Errorf("bootstrap path %q does not exist in the package: %w", bootstrap, statErr)
	}
	if !info.Mode().IsRegular() {
		return bootstrapResolved{}, fmt.Errorf("bootstrap path %q must be a regular file", bootstrap)
	}

	return resolveFinalPath(candidate, realPackageDir, false)
}

func isRelPathEscaping(rel string) bool {
	if rel == ".." {
		return true
	}
	if strings.HasPrefix(rel, ".."+string(os.PathSeparator)) {
		return true
	}
	if filepath.IsAbs(rel) {
		return true
	}
	return false
}

func resolveWindowsBootstrap(realPackageDir string, bootstrap string, candidate string, ext string) (bootstrapResolved, error) {
	switch ext {
	case ".ps1":
		return resolveFinalPath(candidate, realPackageDir, true)
	case ".exe":
		return resolveFinalPath(candidate, realPackageDir, false)
	case ".sh":
		ps1Path := candidate[:len(candidate)-len(ext)] + ".ps1"
		return resolveFinalPath(ps1Path, realPackageDir, true)
	case ".cmd", ".bat":
		return bootstrapResolved{}, fmt.Errorf(
			"windows workspace app bootstrap %q uses an unsupported extension; use a .ps1 or .exe bootstrap instead", bootstrap)
	default:
		return bootstrapResolved{}, fmt.Errorf(
			"windows workspace app bootstrap %q has an unrecognized extension; use a .ps1 or .exe bootstrap", bootstrap)
	}
}

func resolveFinalPath(path string, realPackageDir string, usePowerShell bool) (bootstrapResolved, error) {
	info, statErr := os.Stat(path)
	if statErr != nil {
		return bootstrapResolved{}, fmt.Errorf("bootstrap path %q does not exist in the package: %w", path, statErr)
	}
	if !info.Mode().IsRegular() {
		return bootstrapResolved{}, fmt.Errorf("bootstrap path %q must be a regular file", path)
	}

	realPath, evalErr := filepath.EvalSymlinks(path)
	if evalErr != nil {
		return bootstrapResolved{}, fmt.Errorf("cannot resolve bootstrap real path: %w", evalErr)
	}
	rel, relErr := filepath.Rel(realPackageDir, realPath)
	if relErr != nil || isRelPathEscaping(rel) {
		return bootstrapResolved{}, fmt.Errorf("resolved bootstrap path %q escapes package directory", realPath)
	}

	return bootstrapResolved{path: path, usePowerShell: usePowerShell}, nil
}

var errBootstrapNotExecutable = errors.New("runtime bootstrap must be executable")

func validateResolvedBootstrapExecutable(resolved bootstrapResolved, goos string) error {
	if goos == "windows" {
		return nil
	}
	info, statErr := os.Stat(resolved.path)
	if statErr != nil {
		return fmt.Errorf("stat runtime bootstrap: %w", statErr)
	}
	if info.Mode()&0o111 == 0 {
		return errBootstrapNotExecutable
	}
	return nil
}
