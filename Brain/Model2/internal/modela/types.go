package modela

// InferenceRequest, Model A'ya gönderilecek telemetri verisinin yapısıdır.
// TelemetryPacket'ten dönüştürülerek oluşturulur.
type InferenceRequest struct {
	DeviceID   string    `json:"device_id"`
	SensorType string    `json:"sensor_type"`
	Timestamp  int64     `json:"timestamp"`
	Readings   []float64 `json:"readings"` // W=32 sliding window
}

// InferenceResponse, Model A'dan dönen karar verisinin yapısıdır.
// SuspicionScore eşiği aşarsa komut honeypot'a yönlendirilecek.
type InferenceResponse struct {
	SuspicionScore float64 `json:"suspicion_score"` // 0.0 → 1.0 arası
	HMACToken      string  `json:"hmac_token"`      // Write-gate için kriptografik token
	ExpiresAt      int64   `json:"expires_at"`      // Token geçerlilik süresi (Unix ms)
}
