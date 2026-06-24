package modela

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
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
			log.Println("[CIRCUIT] Yarı açık moda geçildi, deneme isteği gönderiliyor.")
			c.state = stateHalfOpen
			return true
		}
		log.Println("[CIRCUIT] Devre açık — Model A isteği engellendi.")
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
	log.Println("[CIRCUIT] İstek başarılı — devre kapalı durumda.")
}

// recordFailure, hata sayacını artırır; eşik aşılırsa devreyi açar.
func (c *Client) recordFailure() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.failureCount++
	c.lastFailure = time.Now()
	if c.failureCount >= failureThreshold {
		c.state = stateOpen
		log.Printf("[CIRCUIT] %d ardışık hata — devre açıldı. %s sonra tekrar denenecek.",
			c.failureCount, recoveryTimeout)
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
			log.Printf("[CLIENT] Yeniden deneniyor (%d/%d)...", attempt, maxRetries)
			time.Sleep(retryDelay)
		}

		resp, err := c.httpClient.Post(
			c.baseURL+"/score",
			"application/json",
			bytes.NewReader(body),
		)
		if err != nil {
			lastErr = err
			log.Printf("[CLIENT] Model A isteği başarısız (deneme %d): %v", attempt+1, err)
			continue
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			lastErr = fmt.Errorf("Model A beklenmeyen durum kodu: %d", resp.StatusCode)
			log.Printf("[CLIENT] %v", lastErr)
			continue
		}

		var inferenceResp InferenceResponse
		if err := json.NewDecoder(resp.Body).Decode(&inferenceResp); err != nil {
			lastErr = fmt.Errorf("yanıt çözümlenemedi: %w", err)
			log.Printf("[CLIENT] %v", lastErr)
			continue
		}

		// Başarılı — circuit breaker'ı sıfırla
		c.recordSuccess()
		log.Printf("[CLIENT] Model A yanıtı alındı → Suspicion: %.4f | Token: %s... | Expires: %d",
			inferenceResp.SuspicionScore,
			inferenceResp.HMACToken[:8],
			inferenceResp.ExpiresAt,
		)
		return &inferenceResp, nil
	}

	// Tüm denemeler başarısız
	c.recordFailure()
	return nil, fmt.Errorf("Model A'ya ulaşılamadı (%d deneme): %w", maxRetries+1, lastErr)
}
