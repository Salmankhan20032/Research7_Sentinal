package modela

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"sync"
	"time"
)

// circuitState, devre kesicinin mevcut durumunu tanımlar.
type circuitState int

const (
	stateClosed   circuitState = iota // Normal çalışma — istekler geçer
	stateOpen                         // Devre açık — istekler engellenir
	stateHalfOpen                     // Deneme aşaması — tek istek geçer
)

const (
	failureThreshold = 3                      // Kaç ardışık hatadan sonra devre açılır
	recoveryTimeout  = 30 * time.Second       // Devre açıkken ne kadar beklenir
	requestTimeout   = 5 * time.Second        // Tek bir HTTP isteğinin zaman aşımı
	maxRetries       = 2                      // Hata durumunda kaç kez yeniden denenr
	retryDelay       = 500 * time.Millisecond // Denemeler arası bekleme süresi
)

// Client, Model A ile iletişimi yöneten yapıdır.
// İçinde HTTP istemcisi ve circuit breaker durumu barındırır.
type Client struct {
	baseURL      string
	httpClient   *http.Client
	mu           sync.Mutex
	state        circuitState
	failureCount int
	lastFailure  time.Time
}

// NewClient, belirtilen Model A adresine bağlanan yeni bir Client döner.
func NewClient(modelAURL string) *Client {
	return &Client{
		baseURL: modelAURL,
		httpClient: &http.Client{
			Timeout: requestTimeout,
		},
		state: stateClosed,
	}
}

// isAvailable, circuit breaker mantığına göre isteğin gönderilip
// gönderilemeyeceğine karar verir.
func (c *Client) isAvailable() bool {
	c.mu.Lock()
	defer c.mu.Unlock()

	switch c.state {
	case stateClosed:
		// Normal durum — her zaman geçer
		return true

	case stateOpen:
		// Recovery süresi dolduysa yarı açık moda geç ve bir deneme yap
		if time.Since(c.lastFailure) >= recoveryTimeout {
			slog.Warn("circuit_half_open")

			c.state = stateHalfOpen
			return true
		}
		slog.Warn("circuit_open_blocked")

		return false

	case stateHalfOpen:
		// Sadece tek deneme geçer
		return true
	}
	return false
}

// recordSuccess, başarılı istek sonrası devreyi kapalı (normal) duruma alır.
func (c *Client) recordSuccess() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.state = stateClosed
	c.failureCount = 0
	slog.Info("circuit_closed")

}

// recordFailure, hata sayacını artırır; eşik aşılırsa devreyi açar.
func (c *Client) recordFailure() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.failureCount++
	c.lastFailure = time.Now()
	if c.failureCount >= failureThreshold {
		c.state = stateOpen
		slog.Error("circuit_opened", "failure_count", c.failureCount, "retry_after", recoveryTimeout.String())

	}
}

// Score, bir telemetri paketini Model A'ya gönderir ve
// suspicion score ile HMAC token içeren yanıtı döner.
// Hata durumunda retry ve circuit breaker mekanizması devreye girer.
func (c *Client) Score(req InferenceRequest) (*InferenceResponse, error) {
	if !c.isAvailable() {
		return nil, fmt.Errorf("circuit breaker açık: Model A şu an erişilemez")
	}

	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("istek serileştirilemedi: %w", err)
	}

	var lastErr error
	for attempt := 0; attempt <= maxRetries; attempt++ {
		if attempt > 0 {
			slog.Info("modela_retry", "attempt", attempt, "max", maxRetries)

			time.Sleep(retryDelay)
		}

		resp, err := c.httpClient.Post(
			c.baseURL+"/score",
			"application/json",
			bytes.NewReader(body),
		)
		if err != nil {
			lastErr = err
			slog.Warn("modela_attempt_failed", "attempt", attempt+1, "error", err)

			continue
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			lastErr = fmt.Errorf("Model A beklenmeyen durum kodu: %d", resp.StatusCode)
			slog.Warn("modela_bad_status", "error", lastErr)

			continue
		}

		var inferenceResp InferenceResponse
		if err := json.NewDecoder(resp.Body).Decode(&inferenceResp); err != nil {
			lastErr = fmt.Errorf("yanıt çözümlenemedi: %w", err)
			slog.Warn("modela_bad_status", "error", lastErr)

			continue
		}

		// Başarılı — circuit breaker'ı sıfırla
		c.recordSuccess()

		slog.Info("modela_score_received",
			"device_id", req.DeviceID, // req'i fonksiyona parametre olarak taşı veya logda kullan
			"suspicion_score", inferenceResp.SuspicionScore,
			"expires_at", inferenceResp.ExpiresAt,
		)
		return &inferenceResp, nil
	}

	// Tüm denemeler başarısız
	c.recordFailure()
	return nil, fmt.Errorf("Model A'ya ulaşılamadı (%d deneme): %w", maxRetries+1, lastErr)
}

func (c *Client) Ping() (bool, string) {
	c.mu.Lock()
	cbOpen := c.state == stateOpen
	c.mu.Unlock()

	if cbOpen {
		return false, "circuit_open"
	}

	req, err := http.NewRequest(http.MethodGet, c.baseURL+"/health", nil)
	if err != nil {
		return false, "request_build_error"
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	req = req.WithContext(ctx)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return false, "unreachable"
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusOK {
		return true, "ok"
	}
	return false, fmt.Sprintf("status_%d", resp.StatusCode)
}
