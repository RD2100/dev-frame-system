package workspace

import (
	"context"
	"errors"
	"runtime"
	"strings"
	"testing"

	workspacebiz "github.com/tutti-os/tutti/services/tuttid/biz/workspace"
	builtinapps "github.com/tutti-os/tutti/services/tuttid/builtin-apps"
)

func TestIsBuiltinSupportedOnPlatformEmptyPlatformsAlwaysSupported(t *testing.T) {
	dist := builtinapps.Distribution{}
	if !isBuiltinSupportedOnPlatform(dist, "windows", "amd64") {
		t.Fatal("empty platforms should be supported on all OS+arch")
	}
	if !isBuiltinSupportedOnPlatform(dist, "linux", "arm64") {
		t.Fatal("empty platforms should be supported on all OS+arch")
	}
	if !isBuiltinSupportedOnPlatform(dist, "darwin", "arm64") {
		t.Fatal("empty platforms should be supported on all OS+arch")
	}
}

func TestIsBuiltinSupportedOnPlatformMatchesDeclaredOSAndArch(t *testing.T) {
	dist := builtinapps.Distribution{Platforms: []string{"darwin/arm64", "darwin/amd64"}}
	if !isBuiltinSupportedOnPlatform(dist, "darwin", "arm64") {
		t.Fatal("darwin/arm64 should be supported when declared")
	}
	if !isBuiltinSupportedOnPlatform(dist, "darwin", "amd64") {
		t.Fatal("darwin/amd64 should be supported when declared")
	}
}

func TestIsBuiltinSupportedOnPlatformUnsupportedOS(t *testing.T) {
	dist := builtinapps.Distribution{Platforms: []string{"darwin/arm64", "darwin/amd64"}}
	if isBuiltinSupportedOnPlatform(dist, "windows", "amd64") {
		t.Fatal("windows should not be supported when only darwin is declared")
	}
	if isBuiltinSupportedOnPlatform(dist, "linux", "amd64") {
		t.Fatal("linux should not be supported when only darwin is declared")
	}
}

func TestIsBuiltinSupportedOnPlatformUnsupportedArch(t *testing.T) {
	dist := builtinapps.Distribution{Platforms: []string{"darwin/arm64"}}
	if isBuiltinSupportedOnPlatform(dist, "darwin", "amd64") {
		t.Fatal("darwin/amd64 should not be supported when only darwin/arm64 is declared")
	}
}

func TestIsBuiltinSupportedOnPlatformMultipleOS(t *testing.T) {
	dist := builtinapps.Distribution{Platforms: []string{"darwin/arm64", "linux/amd64"}}
	if !isBuiltinSupportedOnPlatform(dist, "darwin", "arm64") {
		t.Fatal("darwin/arm64 should be supported")
	}
	if !isBuiltinSupportedOnPlatform(dist, "linux", "amd64") {
		t.Fatal("linux/amd64 should be supported")
	}
	if isBuiltinSupportedOnPlatform(dist, "darwin", "amd64") {
		t.Fatal("darwin/amd64 should not be supported")
	}
}

func TestInitBuiltinPackagesSkipsUnsupportedPlatform(t *testing.T) {
	store := newAppStoreStub()
	service := AppCenterService{
		Store:    store,
		StateDir: t.TempDir(),
		BuiltinCatalog: func() ([]builtinapps.App, error) {
			return []builtinapps.App{
				{
					Manifest: workspacebiz.AppManifest{
						AppID:   "darwin-only-app",
						Version: "1.0.0",
						Runtime: workspacebiz.AppManifestRuntime{
							Bootstrap:       "bootstrap.sh",
							HealthcheckPath: "/",
						},
					},
					Distribution: builtinapps.Distribution{
						Kind:      builtinapps.DistributionEmbeddedArchive,
						Platforms: []string{"darwin/arm64", "darwin/amd64"},
					},
				},
			}, nil
		},
	}

	if err := service.InitBuiltinPackages(context.Background()); err != nil {
		t.Fatalf("InitBuiltinPackages() error = %v, want nil", err)
	}

	packages, err := store.ListAppPackages(context.Background())
	if err != nil {
		t.Fatalf("ListAppPackages() error = %v", err)
	}
	if len(packages) != 0 {
		t.Fatalf("ListAppPackages() len = %d, want 0 (unsupported builtin skipped)", len(packages))
	}
}

func TestInitBuiltinPackagesSkipsUnsupportedArch(t *testing.T) {
	store := newAppStoreStub()
	service := AppCenterService{
		Store:    store,
		StateDir: t.TempDir(),
		BuiltinCatalog: func() ([]builtinapps.App, error) {
			return []builtinapps.App{
				{
					Manifest: workspacebiz.AppManifest{
						AppID:   "arm64-only-app",
						Version: "1.0.0",
						Runtime: workspacebiz.AppManifestRuntime{
							Bootstrap:       "bootstrap.sh",
							HealthcheckPath: "/",
						},
					},
					Distribution: builtinapps.Distribution{
						Kind:      builtinapps.DistributionEmbeddedArchive,
						Platforms: []string{runtime.GOOS + "/arm64"},
					},
				},
			}, nil
		},
	}

	if err := service.InitBuiltinPackages(context.Background()); err != nil {
		t.Fatalf("InitBuiltinPackages() error = %v, want nil", err)
	}

	packages, err := store.ListAppPackages(context.Background())
	if err != nil {
		t.Fatalf("ListAppPackages() error = %v", err)
	}
	if len(packages) != 0 {
		t.Fatalf("ListAppPackages() len = %d, want 0 (unsupported arch skipped)", len(packages))
	}
}

func TestInitBuiltinPackagesPropagatesErrorForSupportedPlatform(t *testing.T) {
	store := newAppStoreStub()
	service := AppCenterService{
		Store:    store,
		StateDir: t.TempDir(),
		BuiltinCatalog: func() ([]builtinapps.App, error) {
			return []builtinapps.App{
				{
					Manifest: workspacebiz.AppManifest{
						AppID:   "multi-platform-app",
						Version: "1.0.0",
						Runtime: workspacebiz.AppManifestRuntime{
							Bootstrap:       "bootstrap.sh",
							HealthcheckPath: "/",
						},
					},
					Distribution: builtinapps.Distribution{
						Kind:                 builtinapps.DistributionEmbeddedArchive,
						EmbeddedArtifactPath: "nonexistent/archive.zip",
						Platforms:            []string{runtime.GOOS + "/" + runtime.GOARCH},
					},
				},
			}, nil
		},
	}

	err := service.InitBuiltinPackages(context.Background())
	if err == nil {
		t.Fatal("InitBuiltinPackages() error = nil, want error for supported platform with invalid artifact")
	}
	if !strings.Contains(err.Error(), "initialize embedded builtin app archive") {
		t.Fatalf("InitBuiltinPackages() error = %v, want wrapped archive error", err)
	}
}

func TestInitBuiltinPackagesUnrelatedErrorNotSwallowed(t *testing.T) {
	store := newAppStoreStub()
	catalogErr := errors.New("catalog fetch failed")
	service := AppCenterService{
		Store:    store,
		StateDir: t.TempDir(),
		BuiltinCatalog: func() ([]builtinapps.App, error) {
			return nil, catalogErr
		},
	}

	err := service.InitBuiltinPackages(context.Background())
	if err == nil {
		t.Fatal("InitBuiltinPackages() error = nil, want catalog error")
	}
	if !errors.Is(err, catalogErr) {
		t.Fatalf("InitBuiltinPackages() error = %v, want %v", err, catalogErr)
	}
}

func TestInitBuiltinPackagesSkipsRemoteBuiltinsUnconditionally(t *testing.T) {
	store := newAppStoreStub()
	service := AppCenterService{
		Store:    store,
		StateDir: t.TempDir(),
		BuiltinCatalog: func() ([]builtinapps.App, error) {
			return []builtinapps.App{
				{
					Manifest: workspacebiz.AppManifest{
						AppID:   "remote-app",
						Version: "1.0.0",
						Runtime: workspacebiz.AppManifestRuntime{
							Bootstrap:       "bootstrap.sh",
							HealthcheckPath: "/",
						},
					},
					Distribution: builtinapps.Distribution{
						Kind:      builtinapps.DistributionRemote,
						Platforms: []string{"darwin/arm64"},
					},
				},
			}, nil
		},
	}

	if err := service.InitBuiltinPackages(context.Background()); err != nil {
		t.Fatalf("InitBuiltinPackages() error = %v", err)
	}

	packages, err := store.ListAppPackages(context.Background())
	if err != nil {
		t.Fatalf("ListAppPackages() error = %v", err)
	}
	if len(packages) != 0 {
		t.Fatalf("ListAppPackages() len = %d, want 0 (remote builtins are not initialized here)", len(packages))
	}
}
