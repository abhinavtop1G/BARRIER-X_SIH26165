package auth

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"
)

type GoogleTokenInfo struct {
	Sub           string `json:"sub"`
	Email         string `json:"email"`
	EmailVerified string `json:"email_verified"`
	Name          string `json:"name"`
	Picture       string `json:"picture"`
	Audience      string `json:"aud"`
	Error         string `json:"error"`
	ErrorDesc     string `json:"error_description"`
}

type UserClaims struct {
	UserID    string    `json:"user_id"`
	Email     string    `json:"email"`
	Name      string    `json:"name"`
	Picture   string    `json:"picture"`
	Role      string    `json:"role"`
	ExpiresAt time.Time `json:"expires_at"`
}

var (
	ErrInvalidToken = errors.New("invalid or expired authentication token")
	ErrMissingToken = errors.New("authorization token required")
)

var signingSecret = randomSecret()

func randomSecret() []byte {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		panic("auth: cannot generate signing secret: " + err.Error())
	}
	return b
}

func SetSigningSecret(secret string) {
	if strings.TrimSpace(secret) != "" {
		signingSecret = []byte(secret)
	}
}

func signPayload(payload string) string {
	mac := hmac.New(sha256.New, signingSecret)
	mac.Write([]byte(payload))
	return base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}

func VerifyGoogleIDToken(idToken string, expectedAudience string) (*GoogleTokenInfo, error) {
	idToken = strings.TrimSpace(idToken)
	if idToken == "" {
		return nil, errors.New("empty Google ID token")
	}

	client := &http.Client{Timeout: 10 * time.Second}
	url := "https://oauth2.googleapis.com/tokeninfo?id_token=" + idToken
	resp, err := client.Get(url)
	if err != nil {
		return nil, fmt.Errorf("unable to reach Google token verification service: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var errInfo struct {
			Error            string `json:"error"`
			ErrorDescription string `json:"error_description"`
		}
		_ = json.NewDecoder(resp.Body).Decode(&errInfo)
		msg := errInfo.ErrorDescription
		if msg == "" {
			msg = errInfo.Error
		}
		if msg == "" {
			msg = fmt.Sprintf("HTTP status %d", resp.StatusCode)
		}
		return nil, fmt.Errorf("google token verification rejected: %s", msg)
	}

	var info GoogleTokenInfo
	if err := json.NewDecoder(resp.Body).Decode(&info); err != nil {
		return nil, fmt.Errorf("failed to parse Google tokeninfo response: %w", err)
	}

	if info.Email == "" {
		return nil, errors.New("google token does not contain an email address")
	}

	if expectedAudience != "" && info.Audience != "" && info.Audience != expectedAudience {
		return nil, fmt.Errorf("token audience mismatch: token intended for '%s', configured for '%s'", info.Audience, expectedAudience)
	}

	return &info, nil
}

func IssueSessionToken(info *GoogleTokenInfo) (string, *UserClaims) {
	userName := info.Name
	if userName == "" {
		userName = strings.Split(info.Email, "@")[0]
	}

	claims := &UserClaims{
		UserID:    "usr_" + info.Sub,
		Email:     info.Email,
		Name:      userName,
		Picture:   info.Picture,
		Role:      "hse_administrator",
		ExpiresAt: time.Now().Add(24 * time.Hour),
	}

	claimsJSON, _ := json.Marshal(claims)
	payload := base64.RawURLEncoding.EncodeToString(claimsJSON)
	tokenStr := fmt.Sprintf("bx_session_%s.%s", payload, signPayload(payload))

	return tokenStr, claims
}

func ValidateToken(tokenStr string) (*UserClaims, error) {
	if tokenStr == "" {
		return nil, ErrMissingToken
	}

	tokenStr = strings.TrimPrefix(tokenStr, "Bearer ")
	tokenStr = strings.TrimSpace(tokenStr)

	if tokenStr == "" {
		return nil, ErrMissingToken
	}

	if strings.HasPrefix(tokenStr, "bx_session_") {
		parts := strings.SplitN(strings.TrimPrefix(tokenStr, "bx_session_"), ".", 2)
		if len(parts) != 2 {
			return nil, ErrInvalidToken
		}

		if !hmac.Equal([]byte(signPayload(parts[0])), []byte(parts[1])) {
			return nil, ErrInvalidToken
		}

		data, err := base64.RawURLEncoding.DecodeString(parts[0])
		if err == nil {
			var claims UserClaims
			if err := json.Unmarshal(data, &claims); err == nil {
				if time.Now().After(claims.ExpiresAt) {
					return nil, ErrInvalidToken
				}
				return &claims, nil
			}
		}
	}

	return nil, ErrInvalidToken
}
