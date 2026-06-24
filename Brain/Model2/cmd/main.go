package main

import (
	"encoding/json"
	"log"
	"net/http"

	"sentinel-model-b/internal/config"
	"sentinel-model-b/internal/hub"
	"sentinel-model-b/internal/ws"
)

func main() {
	log.Println("[SENTINEL] Model B (Public Broker) başlatılıyor...")

	// 1. Konfigürasyonu yükle
	cfg := config.Load()
	log.Printf("[CONFIG] Port: %s | Model A: %s | PLC: %s",
		cfg.BrokerPort, cfg.ModelA_URL, cfg.PLC_URL)

	// 2. Hub'ı oluştur ve arka planda çalıştır
	h := hub.NewHub()
	go h.Run()
	log.Println("[HUB] Bağlantı havuzu başlatıldı.")

	// 3. HTTP Router'ı kur
	mux := http.NewServeMux()

	// WebSocket telemetri endpoint'i
	mux.HandleFunc("/ws/telemetry", func(w http.ResponseWriter, r *http.Request) {
		ws.ServeWs(h, w, r)
	})

	// Sağlık kontrolü endpoint'i (Docker Compose healthcheck için)
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{
			"status":  "ok",
			"service": "sentinel-model-b",
		})
	})

	// 4. Sunucuyu başlat (blocking call)
	addr := ":" + cfg.BrokerPort
	log.Printf("[SERVER] Sunucu dinleniyor → ws://localhost%s/ws/telemetry", addr)
	log.Printf("[SERVER] Sağlık kontrolü → http://localhost%s/health", addr)

	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Fatalf("[SERVER] Sunucu başlatılamadı: %v", err)
	}
}
