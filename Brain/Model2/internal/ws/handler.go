package ws

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"time"

	"sentinel-model-b/internal/hub"
	"sentinel-model-b/internal/modela"

	"github.com/gorilla/websocket"
)

const (
	writeWait      = 10 * time.Second
	pongWait       = 60 * time.Second
	pingPeriod     = (pongWait * 9) / 10
	maxMessageSize = 4096
)

// allowedOrigins, WebSocket bağlantısı kabul edilecek kaynakların listesi.
// Ortam değişkeninden okunur; Docker ortamında iç servisler ve UI adresi buraya eklenir.
var allowedOrigins = func() map[string]bool {
	origins := map[string]bool{
		"http://localhost:3000": true, // Geliştirme — React/UI
		"http://localhost:8080": true, // Geliştirme — aynı host test
		"http://dashboard:3000": true, // Docker ağı — UI servisi
	}
	// Ortam değişkeninden ek origin eklenebilir
	if extra := os.Getenv("ALLOWED_ORIGIN"); extra != "" {
		origins[extra] = true
	}
	return origins
}()

var upgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	CheckOrigin: func(r *http.Request) bool {
		origin := r.Header.Get("Origin")

		// Origin header yoksa (örn. doğrudan curl/wscat) geliştirme modunda izin ver
		if origin == "" {
			log.Println("[WS] Origin header yok — bağlantı kabul edildi (no-origin istemci)")
			return true
		}

		if allowedOrigins[origin] {
			return true
		}

		log.Printf("[WS] Reddedilen origin: %s", origin)
		return false
	},
}

// readPump, istemciden sürekli mesaj okur ve her paketi Model A'ya iletir.
func readPump(c *hub.Client, h *hub.Hub, conn *websocket.Conn, modelA *modela.Client) {
	defer func() {
		h.Unregister <- c
		conn.Close()
		log.Println("[WS] Bağlantı kapandı.")
	}()

	conn.SetReadLimit(maxMessageSize)
	conn.SetReadDeadline(time.Now().Add(pongWait))
	conn.SetPongHandler(func(string) error {
		conn.SetReadDeadline(time.Now().Add(pongWait))
		return nil
	})

	for {
		_, message, err := conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err,
				websocket.CloseGoingAway,
				websocket.CloseAbnormalClosure,
			) {
				log.Printf("[WS] Beklenmeyen kapanma hatası: %v", err)
			}
			break
		}

		// 1. Ham veriyi TelemetryPacket struct'ına dönüştür
		var packet TelemetryPacket
		if err := json.Unmarshal(message, &packet); err != nil {
			log.Printf("[WS] Geçersiz telemetri paketi: %v", err)
			continue
		}

		log.Printf("[WS] Telemetri alındı → Cihaz: %s | Tip: %s | Okuma Sayısı: %d",
			packet.DeviceID, packet.SensorType, len(packet.Readings))

		// 2. TelemetryPacket → InferenceRequest dönüşümü
		req := modela.InferenceRequest{
			DeviceID:   packet.DeviceID,
			SensorType: packet.SensorType,
			Timestamp:  packet.Timestamp,
			Readings:   packet.Readings,
		}

		// 3. Model A'ya gönder — goroutine içinde çalıştır, bağlantıyı bloklamaz
		go func(r modela.InferenceRequest) {
			resp, err := modelA.Score(r)
			if err != nil {
				log.Printf("[MODELA] Skor alınamadı (Cihaz: %s): %v", r.DeviceID, err)
				return
			}

			// 4. Sonucu logla — ilerleyen aşamada komut yönlendirmede kullanılacak
			log.Printf("[MODELA] Karar → Cihaz: %s | Skor: %.4f | Token: %s... | Expires: %d",
				r.DeviceID,
				resp.SuspicionScore,
				safeTokenPrefix(resp.HMACToken),
				resp.ExpiresAt,
			)
		}(req)

		// 5. Ham paketi UI dashboard'a yayınla
		h.Broadcast <- message
	}
}

// safeTokenPrefix, token boş olsa bile güvenli biçimde ilk 8 karakteri döner.
func safeTokenPrefix(token string) string {
	if len(token) < 8 {
		return token
	}
	return token[:8]
}

// writePump, sunucudan istemciye mesaj gönderir ve ping/pong ile canlılık kontrolü yapar.
func writePump(c *hub.Client, conn *websocket.Conn) {
	ticker := time.NewTicker(pingPeriod)
	defer func() {
		ticker.Stop()
		conn.Close()
	}()

	for {
		select {
		case message, ok := <-c.Send:
			conn.SetWriteDeadline(time.Now().Add(writeWait))
			if !ok {
				conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}
			if err := conn.WriteMessage(websocket.TextMessage, message); err != nil {
				log.Printf("[WS] Yazma hatası: %v", err)
				return
			}

		case <-ticker.C:
			conn.SetWriteDeadline(time.Now().Add(writeWait))
			if err := conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				log.Printf("[WS] Ping gönderilemedi: %v", err)
				return
			}
		}
	}
}

// ServeWs, HTTP bağlantısını WebSocket'e yükseltir ve pump goroutine'lerini başlatır.
func ServeWs(h *hub.Hub, w http.ResponseWriter, r *http.Request, modelA *modela.Client) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("[WS] Upgrade hatası: %v", err)
		return
	}

	client := &hub.Client{
		Conn: conn,
		Send: make(chan []byte, 256),
	}

	h.Register <- client
	log.Printf("[WS] Yeni bağlantı kabul edildi → %s", r.RemoteAddr)

	go writePump(client, conn)
	go readPump(client, h, conn, modelA)
}
