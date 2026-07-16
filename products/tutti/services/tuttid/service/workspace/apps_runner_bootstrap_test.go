package workspace

import (
	"encoding/json"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	workspacebiz "github.com/tutti-os/tutti/services/tuttid/biz/workspace"
)

func TestResolveBootstrapPathRejectsEmpty(t *testing.T) {
	root := t.TempDir()
	_, err := resolveBootstrapPath(root, "")
	if err == nil || !strings.Contains(err.Error(), "empty") {
		t.Fatalf("expected empty-error, got %v", err)
	}
}

func TestResolveBootstrapPathRejectsAbsolutePath(t *testing.T) {
	root := t.TempDir()
	abs := filepath.Join(root, "bootstrap.sh")
	_, err := resolveBootstrapPath(root, abs)
	if err == nil || !strings.Contains(err.Error(), "relative") {
		t.Fatalf("expected relative-path-error, got %v", err)
	}
}

func TestResolveBootstrapPathRejectsPathTraversal(t *testing.T) {
	root := t.TempDir()
	_, err := resolveBootstrapPath(root, "../bootstrap.sh")
	if err == nil || !strings.Contains(err.Error(), "relative") {
		t.Fatalf("expected traversal-error, got %v", err)
	}
}

func TestResolveBootstrapPathRejectsEscapingPath(t *testing.T) {
	root := t.TempDir()
	sub := filepath.Join(root, "sub")
	if err := os.MkdirAll(sub, 0o755); err != nil {
		t.Fatal(err)
	}
	_, err := resolveBootstrapPath(sub, "../bootstrap.sh")
	if err == nil {
		t.Fatal("expected error for path traversal, got nil")
	}

	outerShell := filepath.Join(root, "outer.sh")
	if err := os.WriteFile(outerShell, []byte("echo ok"), 0o644); err != nil {
		t.Fatal(err)
	}
	_, err = resolveBootstrapPath(sub, "../outer.sh")
	if err == nil {
		t.Fatal("expected error for valid file outside sub (path traversal), got nil")
	}
	if !strings.Contains(err.Error(), "relative") && !strings.Contains(err.Error(), "escapes") {
		t.Fatalf("expected traversal/relative/escape error, got %v", err)
	}
}

func TestResolveBootstrapPathAllowsBenignDoubleDots(t *testing.T) {
	root := t.TempDir()
	filename := "some..file.sh"
	path := filepath.Join(root, filename)
	if err := os.WriteFile(path, []byte("#!/bin/sh\necho ok\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	if runtime.GOOS == "windows" {
		if err := os.WriteFile(filepath.Join(root, "some..file.ps1"), []byte("exit 0\n"), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	_, err := resolveBootstrapPath(root, filename)
	if err != nil {
		t.Fatalf("benign filename with double dots was rejected: %v", err)
	}
}

func TestResolveBootstrapPathRejectsMissingFile(t *testing.T) {
	root := t.TempDir()
	_, err := resolveBootstrapPath(root, "missing.exe")
	if err == nil || !strings.Contains(err.Error(), "does not exist") {
		t.Fatalf("expected missing-native error, got %v", err)
	}
}

func TestResolveBootstrapPathRejectsMissingShWithoutPs1Sibling(t *testing.T) {
	root := t.TempDir()
	_, err := resolveBootstrapPath(root, "missing.sh")
	if err == nil {
		t.Fatal("expected error for missing .sh without .ps1 sibling")
	}
	if runtime.GOOS == "windows" {
		if !strings.Contains(err.Error(), "does not exist") {
			t.Fatalf("expected missing error on Windows, got %v", err)
		}
	} else {
		if !strings.Contains(err.Error(), "does not exist") {
			t.Fatalf("expected missing error on Unix, got %v", err)
		}
	}
}

func TestResolveBootstrapPathRejectsDirectory(t *testing.T) {
	root := t.TempDir()
	dir := filepath.Join(root, "adir")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Join(root, "adir.ps1"), 0o755); err != nil {
		t.Fatal(err)
	}
	_, err1 := resolveBootstrapPath(root, "adir")
	_, err2 := resolveBootstrapPath(root, "adir.ps1")
	if err1 == nil {
		t.Fatal("expected error for extensionless directory")
	}
	if err2 == nil || !strings.Contains(err2.Error(), "regular file") {
		t.Fatalf("expected regular-file error for .ps1 directory, got %v", err2)
	}
}

func TestResolveBootstrapPathUnixUsesShDirectly(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Unix-specific test")
	}
	root := t.TempDir()
	bootstrapPath := filepath.Join(root, "bootstrap.sh")
	if err := os.WriteFile(bootstrapPath, []byte("#!/bin/sh\necho ok\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	resolved, err := resolveBootstrapPath(root, "bootstrap.sh")
	if err != nil {
		t.Fatalf("resolveBootstrapPath() error = %v", err)
	}
	if resolved.path != bootstrapPath {
		t.Fatalf("path = %q, want %q", resolved.path, bootstrapPath)
	}
	if resolved.usePowerShell {
		t.Fatal("unix should not use PowerShell")
	}
}

func TestResolveBootstrapPathUnixDefaultsToBootstrapSh(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Unix-specific test")
	}
	root := t.TempDir()
	bootstrapPath := filepath.Join(root, "bootstrap.sh")
	if err := os.WriteFile(bootstrapPath, []byte("#!/bin/sh\necho ok\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	resolved, err := resolveBootstrapPath(root, "bootstrap.sh")
	if err != nil {
		t.Fatalf("resolveBootstrapPath() error = %v", err)
	}
	if resolved.path != bootstrapPath {
		t.Fatalf("path = %q, want %q", resolved.path, bootstrapPath)
	}
}

func TestResolveBootstrapPathUnixPlatformInjected(t *testing.T) {
	root := t.TempDir()
	bootstrapPath := filepath.Join(root, "bootstrap.sh")
	if err := os.WriteFile(bootstrapPath, []byte("#!/bin/sh\necho ok\n"), 0o444); err != nil {
		t.Fatal(err)
	}
	resolved, err := resolveBootstrapPathForPlatform(root, "bootstrap.sh", "linux")
	if err != nil {
		t.Fatalf("resolveBootstrapPathForPlatform(linux) error = %v", err)
	}
	if resolved.path != bootstrapPath {
		t.Fatalf("path = %q, want %q", resolved.path, bootstrapPath)
	}
	if resolved.usePowerShell {
		t.Fatal("linux platform should not use PowerShell")
	}
}

func TestResolveBootstrapPathWindowsPlatformInjected(t *testing.T) {
	if _, err := exec.LookPath("powershell.exe"); err != nil {
		t.Skip("powershell.exe not found")
	}
	root := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "bootstrap.ps1"), []byte("exit 0\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	resolved, err := resolveBootstrapPathForPlatform(root, "bootstrap.ps1", "windows")
	if err != nil {
		t.Fatalf("resolveBootstrapPathForPlatform(windows) error = %v", err)
	}
	if !resolved.usePowerShell {
		t.Fatal("windows platform should use PowerShell")
	}

	// Separate root: .sh without .ps1 sibling fails
	root2 := t.TempDir()
	_, err = resolveBootstrapPathForPlatform(root2, "bootstrap.sh", "windows")
	if err == nil {
		t.Fatal("expected error for .sh without .ps1 on injected windows platform")
	}
}

func TestResolveBootstrapPathWindowsPs1Direct(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific test")
	}
	root := t.TempDir()
	ps1Path := filepath.Join(root, "bootstrap.ps1")
	if err := os.WriteFile(ps1Path, []byte("Write-Host ok"), 0o644); err != nil {
		t.Fatal(err)
	}
	resolved, err := resolveBootstrapPath(root, "bootstrap.ps1")
	if err != nil {
		t.Fatalf("resolveBootstrapPath() error = %v", err)
	}
	if resolved.path != ps1Path {
		t.Fatalf("path = %q, want %q", resolved.path, ps1Path)
	}
	if !resolved.usePowerShell {
		t.Fatal("windows .ps1 bootstrap should use PowerShell")
	}
}

func TestResolveBootstrapPathWindowsExeDirect(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific test")
	}
	root := t.TempDir()
	exePath := filepath.Join(root, "app.exe")
	if err := os.WriteFile(exePath, []byte("fake"), 0o644); err != nil {
		t.Fatal(err)
	}
	resolved, err := resolveBootstrapPath(root, "app.exe")
	if err != nil {
		t.Fatalf("resolveBootstrapPath() error = %v", err)
	}
	if resolved.path != exePath {
		t.Fatalf("path = %q, want %q", resolved.path, exePath)
	}
	if resolved.usePowerShell {
		t.Fatal("windows .exe bootstrap should NOT use PowerShell")
	}
}

func TestResolveBootstrapPathWindowsShToPs1Sibling(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific test")
	}
	root := t.TempDir()
	shPath := filepath.Join(root, "bootstrap.sh")
	ps1Path := filepath.Join(root, "bootstrap.ps1")
	if err := os.WriteFile(shPath, []byte("#!/bin/sh\necho ok\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(ps1Path, []byte("Write-Host ok"), 0o644); err != nil {
		t.Fatal(err)
	}
	resolved, err := resolveBootstrapPath(root, "bootstrap.sh")
	if err != nil {
		t.Fatalf("resolveBootstrapPath() error = %v", err)
	}
	if resolved.path != ps1Path {
		t.Fatalf("path = %q, want .ps1 sibling %q", resolved.path, ps1Path)
	}
	if !resolved.usePowerShell {
		t.Fatal("windows .ps1 sibling should use PowerShell")
	}
}

func TestResolveBootstrapPathWindowsRejectsCmd(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific test")
	}
	root := t.TempDir()
	cmdPath := filepath.Join(root, "bootstrap.cmd")
	if err := os.WriteFile(cmdPath, []byte("@echo ok"), 0o644); err != nil {
		t.Fatal(err)
	}
	_, err := resolveBootstrapPath(root, "bootstrap.cmd")
	if err == nil || !strings.Contains(strings.ToLower(err.Error()), "unsupported") {
		t.Fatalf("expected unsupported extension error for .cmd, got %v", err)
	}
}

func TestResolveBootstrapPathWindowsRejectsBat(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific test")
	}
	root := t.TempDir()
	batPath := filepath.Join(root, "bootstrap.bat")
	if err := os.WriteFile(batPath, []byte("@echo ok"), 0o644); err != nil {
		t.Fatal(err)
	}
	_, err := resolveBootstrapPath(root, "bootstrap.bat")
	if err == nil || !strings.Contains(strings.ToLower(err.Error()), "unsupported") {
		t.Fatalf("expected unsupported extension error for .bat, got %v", err)
	}
}

func TestResolveBootstrapPathWindowsRejectsUnknownExtension(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific test")
	}
	root := t.TempDir()
	unknownPath := filepath.Join(root, "bootstrap.xyz")
	if err := os.WriteFile(unknownPath, []byte("whatever"), 0o644); err != nil {
		t.Fatal(err)
	}
	_, err := resolveBootstrapPath(root, "bootstrap.xyz")
	if err == nil || !strings.Contains(strings.ToLower(err.Error()), "unrecognized") {
		t.Fatalf("expected unrecognized extension error, got %v", err)
	}
}

func TestResolveBootstrapPathWindowsRejectsSymlinkEscape(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific test")
	}
	_, err := exec.LookPath("mklink")
	hasMklink := err == nil

	root := t.TempDir()
	insideDir := filepath.Join(root, "inside")
	outsideDir := filepath.Join(root, "outside")
	for _, d := range []string{insideDir, outsideDir} {
		if err := os.MkdirAll(d, 0o755); err != nil {
			t.Fatal(err)
		}
	}
	outsideFile := filepath.Join(outsideDir, "evil.ps1")
	if err := os.WriteFile(outsideFile, []byte("Write-Host pwned"), 0o644); err != nil {
		t.Fatal(err)
	}

	linkPath := filepath.Join(insideDir, "innocent.ps1")
	if hasMklink {
		cmd := exec.Command("cmd.exe", "/c", "mklink", linkPath, outsideFile)
		if err := cmd.Run(); err != nil {
			t.Skipf("mklink failed (may need admin): %v", err)
		}
	} else {
		if err := os.Symlink(outsideFile, linkPath); err != nil {
			t.Skipf("symlink not supported: %v", err)
		}
	}

	_, err = resolveBootstrapPath(insideDir, "innocent.ps1")
	if err == nil {
		t.Fatal("expected error for symlink escaping package directory, got nil")
	}
	if !strings.Contains(err.Error(), "escapes") {
		t.Fatalf("expected escape error, got %v", err)
	}
}

func TestResolveBootstrapPathWindowsRejectsJunctionEscape(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific test")
	}

	root := t.TempDir()
	insideDir := filepath.Join(root, "inside")
	outsideDir := filepath.Join(root, "outside")
	for _, d := range []string{insideDir, outsideDir} {
		if err := os.MkdirAll(d, 0o755); err != nil {
			t.Fatal(err)
		}
	}

	evilFile := filepath.Join(outsideDir, "evil.ps1")
	if err := os.WriteFile(evilFile, []byte("Write-Host pwned"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(outsideDir, "bootstrap.ps1"), []byte("Write-Host pwned"), 0o644); err != nil {
		t.Fatal(err)
	}

	// Directory junctions (mklink /J) normally work without admin privilege
	junctionPath := filepath.Join(insideDir, "jumplink")
	cmd := exec.Command("cmd.exe", "/c", "mklink", "/J", junctionPath, outsideDir)
	output, err := cmd.CombinedOutput()
	if err != nil {
		t.Skipf("junction mklink /J failed: %v: %s", err, string(output))
	}

	_, err = resolveBootstrapPath(insideDir, "jumplink/bootstrap.ps1")
	if err == nil {
		t.Fatal("expected error for junction escaping package directory, got nil")
	}
	// Junction traversal may fail at EvalSymlinks (path-find) or at containment;
	// either is a valid rejection.
	t.Logf("junction escape correctly rejected: %v", err)
}

func TestValidateExtractedAppPackageWindowsExeAccepted(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific test")
	}

	root := t.TempDir()
	packageDir := filepath.Join(root, "package")
	if err := os.MkdirAll(packageDir, 0o755); err != nil {
		t.Fatal(err)
	}

	exePath := filepath.Join(packageDir, "app.exe")
	if err := os.WriteFile(exePath, []byte("fake"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(packageDir, "AGENTS.md"), []byte("Test.\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	manifest := workspacebiz.AppManifest{
		SchemaVersion: workspacebiz.AppManifestSchemaVersionV1,
		AppID:         "exe-test",
		Version:       "0.1.0",
		Name:          "Exe Test",
		Description:   "Test",
		Icon:          workspacebiz.AppManifestIcon{Type: "asset", Src: "icon.png"},
		Runtime: workspacebiz.AppManifestRuntime{
			Bootstrap:       "app.exe",
			HealthcheckPath: "/healthz",
		},
	}
	manifestData, _ := json.Marshal(manifest)
	if err := os.WriteFile(filepath.Join(packageDir, "tutti.app.json"), manifestData, 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(packageDir, "icon.png"), []byte{0x89, 0x50, 0x4e, 0x47}, 0o644); err != nil {
		t.Fatal(err)
	}

	err := validateExtractedAppPackage(packageDir, manifest)
	if err != nil {
		t.Fatalf("validateExtractedAppPackage() error = %v, want nil (exe with 0644 should be accepted on Windows)", err)
	}
}

func TestValidateResolvedBootstrapExecutableLinuxRejects0644(t *testing.T) {
	root := t.TempDir()
	shPath := filepath.Join(root, "bootstrap.sh")
	if err := os.WriteFile(shPath, []byte("#!/bin/sh\necho ok\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	resolved := bootstrapResolved{path: shPath, usePowerShell: false}
	err := validateResolvedBootstrapExecutable(resolved, "linux")
	if err == nil || !errors.Is(err, errBootstrapNotExecutable) {
		t.Fatalf("expected executable error for mode 0644 on linux, got %v", err)
	}
}

func TestValidateResolvedBootstrapExecutableLinuxAccepts0755(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("executable-mode test requires POSIX file permissions")
	}
	root := t.TempDir()
	shPath := filepath.Join(root, "bootstrap.sh")
	if err := os.WriteFile(shPath, []byte("#!/bin/sh\necho ok\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	resolved := bootstrapResolved{path: shPath, usePowerShell: false}
	err := validateResolvedBootstrapExecutable(resolved, "linux")
	if err != nil {
		t.Fatalf("validateResolvedBootstrapExecutable(linux, 0755) error = %v", err)
	}
}

func TestValidateResolvedBootstrapExecutableWindowsExe0644Accepted(t *testing.T) {
	root := t.TempDir()
	exePath := filepath.Join(root, "app.exe")
	if err := os.WriteFile(exePath, []byte("fake"), 0o644); err != nil {
		t.Fatal(err)
	}
	resolved := bootstrapResolved{path: exePath, usePowerShell: false}
	err := validateResolvedBootstrapExecutable(resolved, "windows")
	if err != nil {
		t.Fatalf("validateResolvedBootstrapExecutable(windows, .exe 0644) error = %v", err)
	}
}

func TestValidateResolvedBootstrapExecutableWindowsPs10644Accepted(t *testing.T) {
	root := t.TempDir()
	ps1Path := filepath.Join(root, "bootstrap.ps1")
	if err := os.WriteFile(ps1Path, []byte("Write-Host ok"), 0o644); err != nil {
		t.Fatal(err)
	}
	resolved := bootstrapResolved{path: ps1Path, usePowerShell: true}
	err := validateResolvedBootstrapExecutable(resolved, "windows")
	if err != nil {
		t.Fatalf("validateResolvedBootstrapExecutable(windows, .ps1 0644) error = %v", err)
	}
}

func TestValidateLocalAppPackageWindowsExe0644Accepted(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific test")
	}
	root := t.TempDir()
	packageDir := filepath.Join(root, "package")
	if err := os.MkdirAll(packageDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(packageDir, "app.exe"), []byte("fake"), 0o644); err != nil {
		t.Fatal(err)
	}
	manifest := workspacebiz.AppManifest{
		SchemaVersion: workspacebiz.AppManifestSchemaVersionV1,
		AppID:         "exe-test",
		Version:       "0.1.0",
		Name:          "Exe Test",
		Description:   "Test",
		Icon:          workspacebiz.AppManifestIcon{Type: "asset", Src: "icon.png"},
		Runtime: workspacebiz.AppManifestRuntime{
			Bootstrap:       "app.exe",
			HealthcheckPath: "/healthz",
		},
	}
	err := validateLocalAppPackage(packageDir, manifest)
	if err != nil {
		t.Fatalf("validateLocalAppPackage() error = %v, want nil (exe with 0644 should be accepted on Windows)", err)
	}
}

func TestAppFactoryValidationWindowsExe0644Accepted(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific test")
	}
	root := t.TempDir()
	packageDir := filepath.Join(root, "package")
	if err := os.MkdirAll(packageDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(packageDir, "app.exe"), []byte("fake"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(packageDir, "AGENTS.md"), []byte("Test app.\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	resolved, err := resolveBootstrapPath(packageDir, "app.exe")
	if err != nil {
		t.Fatalf("resolveBootstrapPath() error = %v", err)
	}
	if err := validateResolvedBootstrapExecutable(resolved, runtime.GOOS); err != nil {
		t.Fatalf("validateResolvedBootstrapExecutable() error = %v (exe 0644 on Windows should pass factory validator)", err)
	}
}

func TestResolveBootstrapPathPlatformInjectedWindowsExeMode644Accepted(t *testing.T) {
	root := t.TempDir()
	exePath := filepath.Join(root, "app.exe")
	if err := os.WriteFile(exePath, []byte("fake"), 0o644); err != nil {
		t.Fatal(err)
	}
	resolved, err := resolveBootstrapPathForPlatform(root, "app.exe", "windows")
	if err != nil {
		t.Fatalf("resolveBootstrapPathForPlatform(windows .exe) error = %v, want nil", err)
	}
	if resolved.usePowerShell {
		t.Fatal("windows .exe should NOT use PowerShell")
	}
	if resolved.path != exePath {
		t.Fatalf("path = %q, want %q", resolved.path, exePath)
	}
}
