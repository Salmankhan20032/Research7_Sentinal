package router

import (
	"encoding/json"
	"net/http"
	"time"

	"sentinel-model-b/internal/command"
	"sentinel-model-b/internal/hub"
	"sentinel-model-b/internal/middleware"
	"sentinel-model-b/internal/modela"
	"sentinel-model-b/internal/ws"
)

// Setup, tüm HTTP ve WebSocket route'larını mux'a kayıt eder.
func Setup(mux *http.ServeMux, h *hub.Hub, modelAClient *modela.Client, cmdHandler *command.Handler) {
	// Rate limiter: saniyede 10 istek, anlık 20 burst
	rl := middleware.NewRateLimiter(10, 20)

	// --- WebSocket — Origin kontrolü handler içinde yapılıyor ---
	mux.HandleFunc("/ws/telemetry", func(w http.ResponseWriter, r *http.Request) {
		ws.ServeWs(h, w, r, modelAClient)
	})

	// --- Komut Proxy — Rate limit + API Key zorunlu ---
	mux.HandleFunc("/api/command",
		rl.Limit(
			middleware.APIKeyAuth(cmdHandler.ServeHTTP),
		),
	)

	// --- Health Check — Açık endpoint, auth yok ---
	mux.HandleFunc("/health", healthHandler(modelAClient))
}

func healthHandler(modelAClient *modela.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		modelAReachable, modelAStatus := modelAClient.Ping()

		overall := "ok"
		httpStatus := http.StatusOK
		if !modelAReachable {
			overall = "degraded"
			httpStatus = http.StatusServiceUnavailable
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(httpStatus)
		json.NewEncoder(w).Encode(map[string]any{
			"status":          overall,
			"service":         "sentinel-model-b",
			"timestamp":       time.Now().UTC().Format(time.RFC3339),
			"model_a_status":  modelAStatus,
			"model_a_healthy": modelAReachable,
		})
	}
}
