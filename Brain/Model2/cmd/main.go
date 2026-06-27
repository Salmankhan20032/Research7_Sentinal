package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"sentinel-model-b/internal/command"
	"sentinel-model-b/internal/config"
	"sentinel-model-b/internal/hub"
	"sentinel-model-b/internal/logger"
	"sentinel-model-b/internal/middleware"
	"sentinel-model-b/internal/modela"
	"sentinel-model-b/internal/router"
)

func main() {
	// 1. Logger'ı başlat — diğer her şeyden önce
	logger.Init()
	slog.Info("sentinel_starting", "service", "model-b", "version", "0.1.0")

	// 2. Konfigürasyon
	cfg := config.Load()
	slog.Info("config_loaded",
		"port", cfg.BrokerPort,
		"model_a_url", cfg.ModelA_URL,
		"plc_url", cfg.PLC_URL,
		"honeypot_url", cfg.HoneypotURL,
	)

	// 3. Bağımlılıklar
	modelAClient := modela.NewClient(cfg.ModelA_URL)
	proxy := command.NewProxy(cfg.PLC_URL, cfg.HoneypotURL)
	cmdHandler := command.NewHandler(modelAClient, proxy)
	h := hub.NewHub()
	go h.Run()
	slog.Info("components_ready")

	// 4. Router + RequestLogger middleware
	mux := http.NewServeMux()
	router.Setup(mux, h, modelAClient, cmdHandler)
	slog.Info("routes_registered",
		"routes", []string{"/ws/telemetry", "/api/command", "/health"},
	)

	// 5. HTTP sunucusu
	addr := ":" + cfg.BrokerPort
	srv := &http.Server{
		Addr:         addr,
		Handler:      middleware.RequestLogger(mux), // Tüm istekleri logla
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	go func() {
		slog.Info("server_listening", "addr", addr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("server_failed", "error", err)
			os.Exit(1)
		}
	}()

	// 6. Graceful shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	sig := <-quit
	slog.Warn("shutdown_signal", "signal", sig.String())

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		slog.Error("shutdown_forced", "error", err)
	} else {
		slog.Info("shutdown_clean")
	}
}
