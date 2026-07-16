package api

import (
	"context"
	"testing"

	tuttigenerated "github.com/tutti-os/tutti/services/tuttid/api/generated"
	cliservice "github.com/tutti-os/tutti/services/tuttid/service/cli"
)

func TestListCliCapabilitiesAppliesProviderFiltersByDefault(t *testing.T) {
	api := DaemonAPI{CLIRegistry: newTestFilteredCLIRegistry(t)}

	response, err := api.ListCliCapabilities(context.Background(), tuttigenerated.ListCliCapabilitiesRequestObject{
		Params: tuttigenerated.ListCliCapabilitiesParams{},
	})
	if err != nil {
		t.Fatalf("ListCliCapabilities: %v", err)
	}

	commands := response.(tuttigenerated.ListCliCapabilities200JSONResponse).Commands
	if got, want := generatedCommandIDs(commands), []string{"diagnostics.visible"}; !equalStringSlices(got, want) {
		t.Fatalf("command ids = %#v, want %#v", got, want)
	}
}

func TestListCliCapabilitiesCanIncludeHiddenCapabilities(t *testing.T) {
	includeHidden := true
	api := DaemonAPI{CLIRegistry: newTestFilteredCLIRegistry(t)}

	response, err := api.ListCliCapabilities(context.Background(), tuttigenerated.ListCliCapabilitiesRequestObject{
		Params: tuttigenerated.ListCliCapabilitiesParams{
			IncludeHidden: &includeHidden,
		},
	})
	if err != nil {
		t.Fatalf("ListCliCapabilities: %v", err)
	}

	commands := response.(tuttigenerated.ListCliCapabilities200JSONResponse).Commands
	if got, want := generatedCommandIDs(commands), []string{"diagnostics.hidden", "diagnostics.visible", "diagnostics.internal"}; !equalStringSlices(got, want) {
		t.Fatalf("command ids = %#v, want %#v", got, want)
	}
}

func TestListCliCapabilitiesCanIncludeIntegrationCapabilities(t *testing.T) {
	includeIntegration := true
	api := DaemonAPI{CLIRegistry: newTestFilteredCLIRegistry(t)}

	response, err := api.ListCliCapabilities(context.Background(), tuttigenerated.ListCliCapabilitiesRequestObject{
		Params: tuttigenerated.ListCliCapabilitiesParams{},
	})
	if err != nil {
		t.Fatalf("ListCliCapabilities: %v", err)
	}
	commands := response.(tuttigenerated.ListCliCapabilities200JSONResponse).Commands
	if got, want := generatedCommandIDs(commands), []string{"diagnostics.visible"}; !equalStringSlices(got, want) {
		t.Fatalf("command ids = %#v, want %#v", got, want)
	}
	if commands[0].Visibility == nil || *commands[0].Visibility != tuttigenerated.Public {
		t.Fatalf("visibility = %#v, want public", commands[0].Visibility)
	}

	response, err = api.ListCliCapabilities(context.Background(), tuttigenerated.ListCliCapabilitiesRequestObject{
		Params: tuttigenerated.ListCliCapabilitiesParams{
			IncludeIntegration: &includeIntegration,
		},
	})
	if err != nil {
		t.Fatalf("ListCliCapabilities include integration: %v", err)
	}
	commands = response.(tuttigenerated.ListCliCapabilities200JSONResponse).Commands
	if got, want := generatedCommandIDs(commands), []string{"diagnostics.visible", "diagnostics.internal"}; !equalStringSlices(got, want) {
		t.Fatalf("command ids with integration = %#v, want %#v", got, want)
	}
	if commands[1].Visibility == nil || *commands[1].Visibility != tuttigenerated.Integration {
		t.Fatalf("integration visibility = %#v", commands[1].Visibility)
	}
}

type testFilteringCLIProvider struct{}

func (testFilteringCLIProvider) AppID() string {
	return "diagnostics"
}

func (testFilteringCLIProvider) Commands() []cliservice.Command {
	internal := testCLICommand("diagnostics.internal", []string{"internal"})
	internal.Capability.Visibility = cliservice.CapabilityVisibilityIntegration
	return []cliservice.Command{
		testCLICommand("diagnostics.hidden", []string{"hidden"}),
		testCLICommand("diagnostics.visible", []string{"visible"}),
		internal,
	}
}

func (testFilteringCLIProvider) FilterCapabilities(_ context.Context, _ cliservice.InvokeContext, capabilities []cliservice.Capability) []cliservice.Capability {
	result := make([]cliservice.Capability, 0, len(capabilities))
	for _, capability := range capabilities {
		if capability.ID != "diagnostics.hidden" {
			result = append(result, capability)
		}
	}
	return result
}

func newTestFilteredCLIRegistry(t *testing.T) *cliservice.Registry {
	t.Helper()
	registry, err := cliservice.NewRegistryFromProviders(testFilteringCLIProvider{})
	if err != nil {
		t.Fatalf("NewRegistryFromProviders: %v", err)
	}
	return registry
}

func testCLICommand(id string, path []string) cliservice.Command {
	return cliservice.Command{
		Capability: cliservice.Capability{
			ID:      id,
			Path:    path,
			Summary: "Test command",
			Output: cliservice.CapabilityOutput{
				DefaultMode: cliservice.OutputModePlain,
				JSON:        true,
			},
		},
		Handler: func(context.Context, cliservice.InvokeRequest) (cliservice.CommandOutput, error) {
			return cliservice.CommandOutput{Kind: cliservice.OutputModePlain, Text: "ok"}, nil
		},
	}
}

func generatedCommandIDs(commands []tuttigenerated.CliCapability) []string {
	ids := make([]string, 0, len(commands))
	for _, command := range commands {
		ids = append(ids, command.Id)
	}
	return ids
}

func equalStringSlices(left []string, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}
