package core

import (
	"fmt"
	"sort"
	"strings"
)

type Status string

const (
	StatusActive  Status = "active"
	StatusWarning Status = "warning"
	StatusError   Status = "error"
)

type Issue struct {
	Code    string
	Message string
}

type State struct {
	Status Status
	Scope  string
	Active bool
	Issues []Issue
}

type ScopeIssueMessages struct {
	Reserved func(scope string) Issue
	Conflict func(scope string, winnerAppID string) Issue
}

type ScopeSetOptions struct {
	ReservedScopes map[string]struct{}
	IssueMessages  ScopeIssueMessages
}

type RegisteredApp struct {
	AppID    string
	AppName  string
	Scope    string
	BaseURL  string
	Commands []Command
}

type CapabilityListOptions struct {
	IncludeIntegration bool
}

type CommandRef struct {
	AppID     string
	CommandID string
}

type ScopeSet struct {
	reservedScopes map[string]struct{}
	issueMessages  ScopeIssueMessages
	entries        map[string]*scopeEntry
	states         map[string]State
	commandID      map[string]CommandRef
}

type scopeEntry struct {
	RegisteredApp
	active bool
	issues []Issue
}

func NewScopeSet(options ScopeSetOptions) *ScopeSet {
	reservedScopes := map[string]struct{}{}
	for scope := range options.ReservedScopes {
		reservedScopes[strings.TrimSpace(scope)] = struct{}{}
	}
	return &ScopeSet{
		reservedScopes: reservedScopes,
		issueMessages:  options.IssueMessages,
		entries:        map[string]*scopeEntry{},
		states:         map[string]State{},
		commandID:      map[string]CommandRef{},
	}
}

func (s *ScopeSet) Upsert(app RegisteredApp) State {
	if s == nil {
		return State{}
	}
	s.ensure()
	app.AppID = strings.TrimSpace(app.AppID)
	app.Scope = strings.TrimSpace(app.Scope)
	if app.AppID == "" {
		return State{}
	}
	s.entries[app.AppID] = &scopeEntry{RegisteredApp: app}
	s.recompute()
	return s.State(app.AppID)
}

func (s *ScopeSet) SetError(appID string, scope string, issue Issue) State {
	if s == nil {
		return State{}
	}
	s.ensure()
	appID = strings.TrimSpace(appID)
	if appID == "" {
		return State{}
	}
	delete(s.entries, appID)
	s.recompute()
	state := State{
		Status: StatusError,
		Scope:  strings.TrimSpace(scope),
		Active: false,
		Issues: []Issue{issue},
	}
	s.states[appID] = state
	return cloneState(state)
}

func (s *ScopeSet) Remove(appID string) {
	if s == nil {
		return
	}
	s.ensure()
	delete(s.entries, strings.TrimSpace(appID))
	delete(s.states, strings.TrimSpace(appID))
	s.recompute()
}

func (s *ScopeSet) Capabilities(options ...CapabilityListOptions) []Capability {
	if s == nil || len(s.entries) == 0 {
		return []Capability{}
	}
	includeIntegration := false
	if len(options) > 0 {
		includeIntegration = options[0].IncludeIntegration
	}
	appIDs := make([]string, 0, len(s.entries))
	for appID := range s.entries {
		appIDs = append(appIDs, appID)
	}
	sort.Strings(appIDs)
	result := make([]Capability, 0)
	for _, appID := range appIDs {
		entry := s.entries[appID]
		if entry == nil || !entry.active {
			continue
		}
		for _, command := range entry.Commands {
			if !includeIntegration && NormalizeVisibility(command.Capability.Visibility) == CommandVisibilityIntegration {
				continue
			}
			result = append(result, command.Capability)
		}
	}
	return result
}

func (s *ScopeSet) Command(commandID string) (RegisteredApp, Command, bool) {
	if s == nil {
		return RegisteredApp{}, Command{}, false
	}
	ref, ok := s.commandID[strings.TrimSpace(commandID)]
	if !ok {
		return RegisteredApp{}, Command{}, false
	}
	entry := s.entries[ref.AppID]
	if entry == nil || !entry.active {
		return RegisteredApp{}, Command{}, false
	}
	for _, command := range entry.Commands {
		if command.Capability.ID == ref.CommandID {
			return entry.RegisteredApp, command, true
		}
	}
	return RegisteredApp{}, Command{}, false
}

func (s *ScopeSet) UpdateBaseURL(appID string, baseURL string) {
	if s == nil {
		return
	}
	if entry := s.entries[strings.TrimSpace(appID)]; entry != nil {
		entry.BaseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
	}
}

func (s *ScopeSet) State(appID string) State {
	if s == nil {
		return State{}
	}
	state, ok := s.states[strings.TrimSpace(appID)]
	if !ok {
		return State{}
	}
	return cloneState(state)
}

func (s *ScopeSet) Empty() bool {
	return s == nil || len(s.entries) == 0 && len(s.states) == 0
}

func (s *ScopeSet) ensure() {
	if s.entries == nil {
		s.entries = map[string]*scopeEntry{}
	}
	if s.states == nil {
		s.states = map[string]State{}
	}
	if s.commandID == nil {
		s.commandID = map[string]CommandRef{}
	}
	if s.reservedScopes == nil {
		s.reservedScopes = map[string]struct{}{}
	}
}

func (s *ScopeSet) recompute() {
	s.ensure()
	for commandID := range s.commandID {
		delete(s.commandID, commandID)
	}
	for appID, state := range s.states {
		if state.Status != StatusError {
			delete(s.states, appID)
		}
	}
	if len(s.entries) == 0 {
		return
	}
	byScope := map[string][]*scopeEntry{}
	for _, entry := range s.entries {
		if entry == nil {
			continue
		}
		entry.active = false
		entry.issues = nil
		byScope[entry.Scope] = append(byScope[entry.Scope], entry)
	}
	for scope, scopedEntries := range byScope {
		sort.Slice(scopedEntries, func(left, right int) bool {
			return scopedEntries[left].AppID < scopedEntries[right].AppID
		})
		if _, reserved := s.reservedScopes[scope]; reserved {
			for _, entry := range scopedEntries {
				entry.issues = []Issue{s.reservedIssue(scope)}
				s.states[entry.AppID] = stateFromEntry(entry, StatusWarning)
			}
			continue
		}
		winner := scopedEntries[0]
		winner.active = true
		s.states[winner.AppID] = stateFromEntry(winner, StatusActive)
		for _, command := range winner.Commands {
			s.commandID[command.Capability.ID] = CommandRef{
				AppID:     winner.AppID,
				CommandID: command.Capability.ID,
			}
		}
		for _, loser := range scopedEntries[1:] {
			loser.issues = []Issue{s.conflictIssue(scope, winner.AppID)}
			s.states[loser.AppID] = stateFromEntry(loser, StatusWarning)
		}
	}
}

func (s *ScopeSet) reservedIssue(scope string) Issue {
	if s.issueMessages.Reserved != nil {
		return s.issueMessages.Reserved(scope)
	}
	return Issue{
		Code:    "app_cli_scope_reserved",
		Message: fmt.Sprintf("CLI scope %q is reserved.", scope),
	}
}

func (s *ScopeSet) conflictIssue(scope string, winnerAppID string) Issue {
	if s.issueMessages.Conflict != nil {
		return s.issueMessages.Conflict(scope, winnerAppID)
	}
	return Issue{
		Code:    "app_cli_scope_conflict",
		Message: fmt.Sprintf("CLI scope %q is already provided by app %q.", scope, winnerAppID),
	}
}

func stateFromEntry(entry *scopeEntry, status Status) State {
	return State{
		Status: status,
		Scope:  entry.Scope,
		Active: status == StatusActive,
		Issues: append([]Issue(nil), entry.issues...),
	}
}

func cloneState(state State) State {
	state.Issues = append([]Issue(nil), state.Issues...)
	return state
}
