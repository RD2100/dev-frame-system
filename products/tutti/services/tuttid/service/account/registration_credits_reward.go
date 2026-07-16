package account

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	authbridge "github.com/tutti-os/tutti/packages/auth/bridge-go"
	tuttitypes "github.com/tutti-os/tutti/services/tuttid/types"
)

const registrationCreditsRewardStateFile = "registration-credits-reward.json"

type RegistrationCreditsReward struct {
	ID        string
	UserID    string
	GrantNo   string
	Credits   int64
	CreatedAt time.Time
}

type registrationCreditsRewardState struct {
	Pending   *RegistrationCreditsReward `json:"pending,omitempty"`
	Shown     map[string]int64           `json:"shown,omitempty"`
	Attempted map[string]int64           `json:"attempted,omitempty"`
}

type commerceLoginClaimResponse struct {
	GrantNo                string                    `json:"grant_no"`
	FirstLoginClaimed      bool                      `json:"first_login_claimed"`
	FirstLoginGrantNo      string                    `json:"first_login_grant_no"`
	FirstLoginGrantCredits commerceLoginClaimCredits `json:"first_login_grant_credits"`
	DailyClaimed           bool                      `json:"daily_claimed"`
	DailyGrantNo           string                    `json:"daily_grant_no"`
	DailyGrantCredits      commerceLoginClaimCredits `json:"daily_grant_credits"`
}

type commerceLoginClaimCredits int64

func (c *commerceLoginClaimCredits) UnmarshalJSON(data []byte) error {
	if strings.TrimSpace(string(data)) == "null" {
		*c = 0
		return nil
	}
	var number int64
	if err := json.Unmarshal(data, &number); err == nil {
		*c = commerceLoginClaimCredits(number)
		return nil
	}
	var text string
	if err := json.Unmarshal(data, &text); err != nil {
		return err
	}
	text = strings.TrimSpace(text)
	if text == "" {
		*c = 0
		return nil
	}
	parsed, err := strconv.ParseInt(text, 10, 64)
	if err != nil {
		return err
	}
	*c = commerceLoginClaimCredits(parsed)
	return nil
}

var ErrRegistrationCreditsRewardIDRequired = errors.New("registration credits reward id is required")

func (s *Service) registrationCreditsReward(
	ctx context.Context,
	session *authbridge.Session,
	user *authbridge.UserInfo,
) *RegistrationCreditsReward {
	if session == nil || user == nil || strings.TrimSpace(user.UserID) == "" {
		slog.Info("account registration credits reward skipped without session user",
			"event", "account.registration_credits_reward.skipped",
			"reason", "missing_session_or_user",
			"has_session", session != nil,
			"has_user", user != nil,
		)
		return nil
	}
	cookie := sessionCookie(session)
	if cookie == "" {
		slog.Info("account registration credits reward skipped without cookie",
			"event", "account.registration_credits_reward.skipped",
			"reason", "missing_session_cookie",
			"user_hash", accountLogHash(user.UserID),
		)
		return nil
	}
	userID := strings.TrimSpace(user.UserID)

	s.rewardMu.Lock()
	defer s.rewardMu.Unlock()

	state, err := s.loadRegistrationCreditsRewardState()
	if err != nil {
		slog.Warn("account registration credits reward state load failed",
			"event", "account.registration_credits_reward.state_load_failed",
			"user_hash", accountLogHash(userID),
			"error", err,
		)
		state = registrationCreditsRewardState{}
	}
	if pending := visibleRegistrationCreditsReward(state, userID); pending != nil {
		slog.Info("account registration credits reward pending reused",
			"event", "account.registration_credits_reward.pending_reused",
			"user_hash", accountLogHash(userID),
			"reward_hash", accountLogHash(pending.ID),
			"credits", pending.Credits,
		)
		return pending
	}
	if state.Attempted != nil && state.Attempted[userID] > 0 {
		slog.Info("account registration credits reward claim skipped after prior attempt",
			"event", "account.registration_credits_reward.claim_skipped",
			"reason", "already_attempted",
			"user_hash", accountLogHash(userID),
		)
		return nil
	}

	slog.Info("account registration credits reward claim requested",
		"event", "account.registration_credits_reward.claim_requested",
		"user_hash", accountLogHash(userID),
	)
	claim, err := s.claimRegistrationCredits(ctx, cookie)
	if err != nil {
		slog.Warn("account registration credits reward claim failed",
			"event", "account.registration_credits_reward.claim_failed",
			"user_hash", accountLogHash(userID),
			"error_code", productSummaryErrorCode(err),
			"error", err,
		)
		return nil
	}
	now := time.Now().UTC()
	if state.Attempted == nil {
		state.Attempted = map[string]int64{}
	}
	state.Attempted[userID] = now.UnixMilli()
	slog.Info("account registration credits reward claim completed",
		"event", "account.registration_credits_reward.claim_completed",
		"user_hash", accountLogHash(userID),
		"first_login_claimed", claim.FirstLoginClaimed,
		"first_login_grant_credits", claim.FirstLoginGrantCredits,
		"first_login_grant_hash", accountLogHash(claim.FirstLoginGrantNo),
		"grant_hash", accountLogHash(claim.GrantNo),
		"daily_claimed", claim.DailyClaimed,
		"daily_grant_credits", claim.DailyGrantCredits,
		"daily_grant_hash", accountLogHash(claim.DailyGrantNo),
	)

	if !claim.FirstLoginClaimed || claim.FirstLoginGrantCredits <= 0 {
		if err := s.saveRegistrationCreditsRewardState(state); err != nil {
			slog.Warn("account registration credits reward attempt save failed",
				"event", "account.registration_credits_reward.attempt_save_failed",
				"user_hash", accountLogHash(userID),
				"error", err,
			)
		}
		slog.Info("account registration credits reward not created",
			"event", "account.registration_credits_reward.not_created",
			"reason", "no_first_login_reward",
			"user_hash", accountLogHash(userID),
			"first_login_claimed", claim.FirstLoginClaimed,
			"first_login_grant_credits", claim.FirstLoginGrantCredits,
			"daily_claimed", claim.DailyClaimed,
			"daily_grant_credits", claim.DailyGrantCredits,
		)
		return nil
	}
	grantNo := strings.TrimSpace(claim.FirstLoginGrantNo)
	if grantNo == "" {
		grantNo = strings.TrimSpace(claim.GrantNo)
	}
	if grantNo == "" {
		grantNo = fmt.Sprintf("first-login-%d", now.UnixMilli())
	}
	rewardID := registrationCreditsRewardID(userID, grantNo)
	if state.Shown != nil && state.Shown[rewardID] > 0 {
		if err := s.saveRegistrationCreditsRewardState(state); err != nil {
			slog.Warn("account registration credits reward shown state save failed",
				"event", "account.registration_credits_reward.shown_state_save_failed",
				"user_hash", accountLogHash(userID),
				"reward_hash", accountLogHash(rewardID),
				"error", err,
			)
		}
		slog.Info("account registration credits reward not created",
			"event", "account.registration_credits_reward.not_created",
			"reason", "already_shown",
			"user_hash", accountLogHash(userID),
			"reward_hash", accountLogHash(rewardID),
		)
		return nil
	}

	reward := &RegistrationCreditsReward{
		ID:        rewardID,
		UserID:    userID,
		GrantNo:   grantNo,
		Credits:   int64(claim.FirstLoginGrantCredits),
		CreatedAt: now,
	}
	state.Pending = reward
	if err := s.saveRegistrationCreditsRewardState(state); err != nil {
		slog.Warn("account registration credits reward pending save failed",
			"event", "account.registration_credits_reward.pending_save_failed",
			"user_hash", accountLogHash(userID),
			"reward_hash", accountLogHash(rewardID),
			"credits", reward.Credits,
			"error", err,
		)
		return copyRegistrationCreditsReward(reward)
	}
	slog.Info("account registration credits reward pending created",
		"event", "account.registration_credits_reward.pending_created",
		"user_hash", accountLogHash(userID),
		"reward_hash", accountLogHash(rewardID),
		"grant_hash", accountLogHash(grantNo),
		"credits", reward.Credits,
	)
	return copyRegistrationCreditsReward(reward)
}

func (s *Service) claimRegistrationCredits(ctx context.Context, cookie string) (commerceLoginClaimResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, productSummaryTimeout)
	defer cancel()

	var out commerceLoginClaimResponse
	err := s.postSessionJSON(ctx, s.commerceBaseURL(), "/v1/credits/login-claim", cookie, bytes.NewReader([]byte(`{}`)), &out)
	return out, err
}

func (s *Service) DismissRegistrationCreditsReward(_ context.Context, rewardID string) error {
	rewardID = strings.TrimSpace(rewardID)
	if rewardID == "" {
		return ErrRegistrationCreditsRewardIDRequired
	}

	s.rewardMu.Lock()
	defer s.rewardMu.Unlock()

	state, err := s.loadRegistrationCreditsRewardState()
	if err != nil {
		return err
	}
	if state.Shown == nil {
		state.Shown = map[string]int64{}
	}
	state.Shown[rewardID] = time.Now().UTC().UnixMilli()
	if state.Pending != nil && state.Pending.ID == rewardID {
		state.Pending = nil
	}
	if err := s.saveRegistrationCreditsRewardState(state); err != nil {
		slog.Warn("account registration credits reward dismiss save failed",
			"event", "account.registration_credits_reward.dismiss_save_failed",
			"reward_hash", accountLogHash(rewardID),
			"error", err,
		)
		return err
	}
	slog.Info("account registration credits reward dismissed",
		"event", "account.registration_credits_reward.dismissed",
		"reward_hash", accountLogHash(rewardID),
	)
	return nil
}

func visibleRegistrationCreditsReward(state registrationCreditsRewardState, userID string) *RegistrationCreditsReward {
	if state.Pending == nil || state.Pending.UserID != userID || state.Pending.Credits <= 0 {
		return nil
	}
	if state.Shown != nil && state.Shown[state.Pending.ID] > 0 {
		return nil
	}
	return copyRegistrationCreditsReward(state.Pending)
}

func copyRegistrationCreditsReward(reward *RegistrationCreditsReward) *RegistrationCreditsReward {
	if reward == nil {
		return nil
	}
	copy := *reward
	return &copy
}

func registrationCreditsRewardID(userID string, grantNo string) string {
	return "registrationCreditsToastShown:" + strings.TrimSpace(userID) + ":" + strings.TrimSpace(grantNo)
}

func (s *Service) loadRegistrationCreditsRewardState() (registrationCreditsRewardState, error) {
	body, err := os.ReadFile(s.registrationCreditsRewardStatePath())
	if err != nil {
		if os.IsNotExist(err) {
			return registrationCreditsRewardState{}, nil
		}
		return registrationCreditsRewardState{}, err
	}
	var state registrationCreditsRewardState
	if err := json.Unmarshal(body, &state); err != nil {
		return registrationCreditsRewardState{}, err
	}
	return state, nil
}

func (s *Service) saveRegistrationCreditsRewardState(state registrationCreditsRewardState) error {
	path := s.registrationCreditsRewardStatePath()
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	body, err := json.MarshalIndent(state, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(body, '\n'), 0o600)
}

func (s *Service) registrationCreditsRewardStatePath() string {
	if strings.TrimSpace(s.RegistrationCreditsRewardStatePath) != "" {
		return strings.TrimSpace(s.RegistrationCreditsRewardStatePath)
	}
	authPath := firstNonEmpty(s.AuthJSONPath, filepath.Join(tuttitypes.DefaultStateDir(), "account", "auth.json"))
	return filepath.Join(filepath.Dir(authPath), registrationCreditsRewardStateFile)
}
