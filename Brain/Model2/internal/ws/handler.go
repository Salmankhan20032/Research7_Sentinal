package ws

import (
	"encoding/json"
	"log"
	"net/http"
	"time"

	"sentinel-model-b/internal/hub"

	"github.com/gorilla/websocket"
)

const (
	writeWait      = 10 * time.Second    // Bir yazma işleminin maksimum süresi
	pongWait       = 60 * time.Second    // İstemciden pong bekleme süresi
	pingPeriod     = (pongWait * 9) / 10 // Ping gönderme aralığı (pongWait'in %90'ı)
	maxMessageSize = 4096                // Bayt cinsinden maksimum mesaj boyutu
)

// upgrader, gelen HTTP bağlantısını WebSocket protokolüne yükseltir.
// CheckOrigin geliştirme aşamasında herkese açık; 6. Aşamada kısıtlanacak.
var upgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	CheckOrigin: func(r *http.Request) bool {
		return true
	},
}

// readPump, istemciden sürekli mesaj okur.
// Bağlantı koptuğunda veya hata oluştuğunda hub'a bildirim yapar ve temizlik yapar.
func readPump(c *hub.Client, h *hub.Hub, conn *websocket.Conn) {
	defer func() {
		h.Unregister <- c
		conn.Close()
		log.Printf("[WS] Bağlantı kapandı. Aktif istemci sayısı güncelleniyor.")
	}()

	conn.SetReadLimit(maxMessageSize)
	conn.SetReadDeadline(time.Now().Add(pongWait))
	conn.SetPongHandler(func(string) error {
		// Her pong geldiğinde deadline'ı sıfırla → bağlantı canlı
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

		// Gelen ham veriyi TelemetryPacket struct'ına dönüştür
		var packet TelemetryPacket
		if err := json.Unmarshal(message, &packet); err != nil {
			log.Printf("[WS] Geçersiz telemetri paketi: %v", err)
			continue // Hatalı paketi atla, bağlantıyı kesme
		}

		log.Printf("[WS] Telemetri alındı → Cihaz: %s | Tip: %s | Okuma Sayısı: %d",
			packet.DeviceID, packet.SensorType, len(packet.Readings))

		// Paketi tüm bağlı istemcilere yayınla (UI dashboard için)
		h.Broadcast <- message
	}
}

// writePump, sunucudan istemciye mesaj gönderir.
// Ticker ile düzenli ping atarak bağlantının canlı olup olmadığını kontrol eder.
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
				// Hub kanalı kapattı → istemciye kapanma mesajı gönder
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
				log.Printf("[WS] Ping gönderilemedi, bağlantı kopmuş olabilir: %v", err)
				return
			}
		}
	}
}

// ServeWs, gelen HTTP isteğini WebSocket'e yükseltir,
// yeni istemciyi hub'a kaydeder ve pump goroutine'lerini başlatır.
func ServeWs(h *hub.Hub, w http.ResponseWriter, r *http.Request) {
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

	// Her iki pump ayrı goroutine'de çalışır:
	// readPump  → istemci → sunucu yönü
	// writePump → sunucu  → istemci yönü
	go writePump(client, conn)
	go readPump(client, h, conn)
}
