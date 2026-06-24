package command

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"time"
)

const proxyTimeout = 5 * time.Second

// plcPayload, PLC simülatörüne gönderilecek yazma komutunun yapısıdır.
// HMAC token ve geçerlilik süresi write-gate doğrulaması için zorunludur.
type plcPayload struct {
	DeviceID  string  `json:"device_id"`
	Register  string  `json:"register"`
	Value     float64 `json:"value"`
	HMACToken string  `json:"hmac_token"` // Model A tarafından üretilen token
	ExpiresAt int64   `json:"expires_at"` // Token geçerlilik süresi (Unix ms)
}

// honeypotPayload, sahte sandbox ortamına gönderilecek komutun yapısıdır.
// Saldırgan gerçek PLC'ye yazıldığını sanır ama sandbox'a düşer.
type honeypotPayload struct {
	DeviceID  string  `json:"device_id"`
	Register  string  `json:"register"`
	Value     float64 `json:"value"`
	HMACToken string  `json:"hmac_token"`
	ExpiresAt int64   `json:"expires_at"`
}

// Proxy, komutları PLC veya honeypot'a ileten yapıdır.
type Proxy struct {
	plcURL      string
	honeypotURL string
	httpClient  *http.Client
}

// NewProxy, belirtilen adreslerle yeni bir Proxy örneği döner.
func NewProxy(plcURL, honeypotURL string) *Proxy {
	return &Proxy{
		plcURL:      plcURL,
		honeypotURL: honeypotURL,
		httpClient: &http.Client{
			Timeout: proxyTimeout,
		},
	}
}

// SendToPLC, HMAC token ile birlikte komutu gerçek PLC simülatörüne iletir.
// Token süresi dolmuşsa komut reddedilir, PLC'ye hiç gönderilmez.
func (p *Proxy) SendToPLC(req WriteRequest, token string, expiresAt int64) error {
	// Token süre kontrolü — PLC'ye göndermeden önce burada da doğrula
	if time.Now().UnixMilli() > expiresAt {
		return fmt.Errorf("HMAC token süresi dolmuş (expires_at: %d)", expiresAt)
	}

	payload := plcPayload{
		DeviceID:  req.DeviceID,
		Register:  req.Register,
		Value:     req.Value,
		HMACToken: token,
		ExpiresAt: expiresAt,
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("PLC payload serileştirilemedi: %w", err)
	}

	resp, err := p.httpClient.Post(
		p.plcURL+"/write",
		"application/json",
		bytes.NewReader(body),
	)
	if err != nil {
		return fmt.Errorf("PLC'ye ulaşılamadı: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("PLC beklenmeyen durum kodu: %d", resp.StatusCode)
	}

	log.Printf("[PROXY] ✅ PLC yazma başarılı → Cihaz: %s | Register: %s | Değer: %.4f",
		req.DeviceID, req.Register, req.Value)
	return nil
}

// SendToHoneypot, şüpheli komutu gerçekmiş gibi sandbox'a iletir.
// Saldırgana başarılı yazma onayı dönerken gerçek PLC korunur.
func (p *Proxy) SendToHoneypot(req WriteRequest, token string, expiresAt int64) error {
	payload := honeypotPayload{
		DeviceID:  req.DeviceID,
		Register:  req.Register,
		Value:     req.Value,
		HMACToken: token,
		ExpiresAt: expiresAt,
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("honeypot payload serileştirilemedi: %w", err)
	}

	resp, err := p.httpClient.Post(
		p.honeypotURL+"/write",
		"application/json",
		bytes.NewReader(body),
	)
	if err != nil {
		// Honeypot erişilemez olsa bile komutu logla ve başarılı say
		// Saldırgana hata döndürmek sistemin farkında olduğumuzu ele verir
		log.Printf("[HONEYPOT] ⚠️  Honeypot erişilemez, komut loglandı → Cihaz: %s | Register: %s",
			req.DeviceID, req.Register)
		return nil
	}
	defer resp.Body.Close()

	log.Printf("[HONEYPOT] 🍯 Şüpheli komut honeypot'a yönlendirildi → Cihaz: %s | Register: %s | Değer: %.4f",
		req.DeviceID, req.Register, req.Value)
	return nil
}
