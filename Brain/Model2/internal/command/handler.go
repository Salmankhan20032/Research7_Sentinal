package command

import (
	"encoding/json"
	"log"
	"log/slog"
	"net/http"
	"time"

	"sentinel-model-b/internal/modela"
)

const suspicionThreshold = 0.75 // Bu eşiği aşan komutlar honeypot'a yönlendirilir

// Handler, /api/command endpoint'ini yöneten yapıdır.
// Model A istemcisi ve Proxy bağımlılıklarını içerir.
type Handler struct {
	modelA *modela.Client
	proxy  *Proxy
}

// NewHandler, bağımlılıkları enjekte ederek yeni bir Handler döner.
func NewHandler(modelA *modela.Client, proxy *Proxy) *Handler {
	return &Handler{
		modelA: modelA,
		proxy:  proxy,
	}
}

// ServeHTTP, /api/command endpoint'ine gelen POST isteklerini işler.
// Akış:
//  1. İsteği parse et ve doğrula
//  2. Model A'dan suspicion score ve HMAC token al
//  3. Score eşiği kontrolü yap
//  4. Eşik altıysa → PLC'ye ilet
//     Eşik üstüysa → Honeypot'a yönlendir
//  5. Yanıtı operatöre döndür
func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// Sadece POST kabul et
	if r.Method != http.MethodPost {
		http.Error(w, "Sadece POST desteklenir", http.StatusMethodNotAllowed)
		return
	}

	// 1. İstek gövdesini parse et
	var req WriteRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		log.Printf("[CMD] Geçersiz istek gövdesi: %v", err)
		http.Error(w, "Geçersiz JSON", http.StatusBadRequest)
		return
	}
	defer r.Body.Close()

	// 2. Zorunlu alanları doğrula
	if req.DeviceID == "" || req.Register == "" {
		log.Printf("[CMD] Eksik alan → DeviceID: %q | Register: %q", req.DeviceID, req.Register)
		http.Error(w, "device_id ve register zorunludur", http.StatusBadRequest)
		return
	}

	slog.Info("command_received", "device_id", req.DeviceID, "register",
		req.Register, "value", req.Value)

	// 3. Model A'dan suspicion score ve HMAC token talep et
	// Komut verisini InferenceRequest'e dönüştür
	inferenceReq := modela.InferenceRequest{
		DeviceID:   req.DeviceID,
		SensorType: "command", // Komut kanalından geldiğini belirt
		Timestamp:  time.Now().UnixMilli(),
		Readings:   []float64{req.Value}, // Tek değerlik sliding window
	}

	inferenceResp, err := h.modelA.Score(inferenceReq)
	if err != nil {
		slog.Error("command_score_failed", "device_id", req.DeviceID, "error", err)

		// Model A erişilemezse güvenli taraf → komutu reddet
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(WriteResponse{
			Success:  false,
			Routed:   "rejected",
			Message:  "Trust Engine erişilemez, komut güvenlik gerekçesiyle reddedildi",
			DeviceID: req.DeviceID,
			Register: req.Register,
		})
		return
	}

	log.Printf("[CMD] Model A kararı → Suspicion: %.4f | Eşik: %.2f",
		inferenceResp.SuspicionScore, suspicionThreshold)

	// 4. Suspicion score'a göre yönlendirme kararı ver
	var routed string
	var routeErr error

	if inferenceResp.SuspicionScore > suspicionThreshold {
		// ⚠️  Şüpheli komut → Honeypot'a yönlendir
		log.Printf("[CMD] ⚠️  Şüpheli komut tespit edildi (%.4f > %.2f) → Honeypot'a yönlendiriliyor",
			inferenceResp.SuspicionScore, suspicionThreshold)
		routeErr = h.proxy.SendToHoneypot(req, inferenceResp.HMACToken, inferenceResp.ExpiresAt)
		routed = "honeypot"
	} else {
		// ✅ Güvenli komut → PLC'ye ilet
		log.Printf("[CMD] ✅ Güvenli komut onaylandı (%.4f ≤ %.2f) → PLC'ye iletiliyor",
			inferenceResp.SuspicionScore, suspicionThreshold)
		routeErr = h.proxy.SendToPLC(req, inferenceResp.HMACToken, inferenceResp.ExpiresAt)
		routed = "plc"
	}

	// 5. Yönlendirme hatası kontrolü
	w.Header().Set("Content-Type", "application/json")

	if routeErr != nil {
		slog.Error("command_route_error", "routed", routed, "error", routeErr)

		w.WriteHeader(http.StatusBadGateway)
		json.NewEncoder(w).Encode(WriteResponse{
			Success:  false,
			Routed:   routed,
			Message:  routeErr.Error(),
			DeviceID: req.DeviceID,
			Register: req.Register,
		})
		return
	}

	// 6. Başarılı yanıt — honeypot durumunda saldırgana gerçekmiş gibi görünür
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(WriteResponse{
		Success:  true,
		Routed:   routed,
		Message:  "Komut başarıyla işlendi",
		DeviceID: req.DeviceID,
		Register: req.Register,
	})
}
