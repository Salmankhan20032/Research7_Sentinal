package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"sentinel-model-b/internal/command"
	"sentinel-model-b/internal/config"
	"sentinel-model-b/internal/hub"
	"sentinel-model-b/internal/modela"
	"sentinel-model-b/internal/router"
)

func main() {
	log.Println("[SENTINEL] Model B (Public Broker) başlatılıyor...")

	// 1. Konfigürasyon
	cfg := config.Load()
	log.Printf("[CONFIG] Port: %s | Model A: %s | PLC: %s | Honeypot: %s",
		cfg.BrokerPort, cfg.ModelA_URL, cfg.PLC_URL, cfg.HoneypotURL)

	// 2. Bağımlılıkları oluştur
	modelAClient := modela.NewClient(cfg.ModelA_URL)
	proxy := command.NewProxy(cfg.PLC_URL, cfg.HoneypotURL)
	cmdHandler := command.NewHandler(modelAClient, proxy)
	h := hub.NewHub()
	go h.Run()
	log.Println("[HUB] Bağlantı havuzu başlatıldı.")

	// 3. Router'ı kur
	mux := http.NewServeMux()
	router.Setup(mux, h, modelAClient, cmdHandler)
	log.Println("[ROUTER] Route'lar kayıt edildi: /ws/telemetry | /api/command | /health")

	// 4. HTTP sunucusunu yapılandır
	addr := ":" + cfg.BrokerPort
	srv := &http.Server{
		Addr:         addr,
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// 5. Sunucuyu ayrı goroutine'de başlat
	go func() {
		log.Printf("[SERVER] Dinleniyor → http://localhost%s", addr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("[SERVER] Başlatma hatası: %v", err)
		}
	}()

	// 6. OS sinyallerini dinle (Ctrl+C → SIGINT, Docker stop → SIGTERM)
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	received := <-quit
	log.Printf("[SENTINEL] Sinyal alındı: %s — kapatılıyor...", received)

	// 7. Graceful shutdown: 15 saniye içinde açık bağlantılar tamamlansın
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		log.Printf("[SERVER] Zorla kapatılıyor: %v", err)
	} else {
		log.Println("[SERVER] Temiz kapatma tamamlandı.")
	}

	log.Println("[SENTINEL] Model B kapatıldı.")
}
