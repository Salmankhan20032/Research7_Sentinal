package config

import "os"

// Uygulamanın çalışması için gereken tüm ayarları tutan yapı
type Config struct {
	BrokerPort string
	ModelA_URL string
	PLC_URL    string
}

// getEnv, belirtilen çevresel değişkeni okur. Bulamazsa fallback değerini döner.
func getEnv(key, fallback string) string {
	if value, exists := os.LookupEnv(key); exists {
		return value
	}
	return fallback
}

// Load, sistemdeki değişkenleri okuyarak Config yapısını doldurur ve döndürür.
func Load() *Config {
	return &Config{
		BrokerPort: getEnv("BROKER_PORT", "8080"),
		ModelA_URL: getEnv("MODEL_A_URL", "http://modela:8000"), // Docker ağı varsayılanı
		PLC_URL:    getEnv("PLC_URL", "http://plc_sim:5020"),    // Docker ağı varsayılanı
	}
}
