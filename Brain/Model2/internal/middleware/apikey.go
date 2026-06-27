package middleware

import (
	"log"
	"net/http"
	"os"
)

// APIKeyAuth, X-API-Key header'ını doğrulayan middleware'dir.
// Key ortam değişkeninden okunur; eksik ya da yanlışsa 401 döner.
// Yalnızca /api/command gibi yazma endpoint'lerine uygulanır.
func APIKeyAuth(next http.HandlerFunc) http.HandlerFunc {
	expectedKey := os.Getenv("API_KEY")

	// API_KEY tanımsızsa güvenli taraf: tüm istekleri reddet
	if expectedKey == "" {
		log.Println("[APIKEY] ⚠️  API_KEY ortam değişkeni tanımsız — tüm istekler reddedilecek")
	}

	return func(w http.ResponseWriter, r *http.Request) {
		if expectedKey == "" {
			http.Error(w, `{"error":"sunucu yapılandırma hatası: API key tanımsız"}`,
				http.StatusInternalServerError)
			return
		}

		key := r.Header.Get("X-API-Key")
		if key == "" {
			log.Printf("[APIKEY] Eksik X-API-Key header → %s %s", r.Method, r.URL.Path)
			http.Error(w, `{"error":"X-API-Key header zorunludur"}`,
				http.StatusUnauthorized)
			return
		}

		if key != expectedKey {
			log.Printf("[APIKEY] Geçersiz API key → IP: %s", r.RemoteAddr)
			http.Error(w, `{"error":"geçersiz API key"}`,
				http.StatusUnauthorized)
			return
		}

		next(w, r)
	}
}
