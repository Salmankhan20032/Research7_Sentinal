package hub

import "sync"

// Client, tek bir WebSocket bağlantısını ve ona ait mesaj kuyruğunu temsil eder.
type Client struct {
	Conn interface{ Close() error } // Bağlantı arayüzü (test edilebilirlik için)
	Send chan []byte                // Bu istemciye gönderilecek mesaj kuyruğu
}

// Hub, tüm aktif WebSocket bağlantılarını merkezi olarak yöneten yapıdır.
// Tüm kayıt/silme/yayın işlemleri bu yapı üzerinden geçer.
type Hub struct {
	Clients    map[*Client]bool // Aktif bağlantı havuzu
	Broadcast  chan []byte      // Tüm istemcilere yayın kanalı
	Register   chan *Client     // Yeni bağlantı bildirimi kanalı
	Unregister chan *Client     // Kapanan bağlantı bildirimi kanalı
	mu         sync.Mutex       // Eş zamanlı harita erişimini korur
}

// NewHub, sıfırlanmış ve kullanıma hazır bir Hub örneği döner.
func NewHub() *Hub {
	return &Hub{
		Clients:    make(map[*Client]bool),
		Broadcast:  make(chan []byte, 256),
		Register:   make(chan *Client),
		Unregister: make(chan *Client),
	}
}

// Run, Hub'ın ana döngüsüdür. Ayrı bir goroutine'de çalıştırılmalıdır.
// Tüm kayıt, silme ve yayın olaylarını sıralı biçimde işler.
func (h *Hub) Run() {
	for {
		select {

		// Yeni bir istemci bağlandı
		case client := <-h.Register:
			h.mu.Lock()
			h.Clients[client] = true
			h.mu.Unlock()

		// Bir istemci bağlantısı kapandı
		case client := <-h.Unregister:
			h.mu.Lock()
			if _, ok := h.Clients[client]; ok {
				delete(h.Clients, client)
				close(client.Send) // Kanalı kapat → writePump'ı sonlandırır
			}
			h.mu.Unlock()

		// Tüm aktif istemcilere mesaj yayını
		case message := <-h.Broadcast:
			h.mu.Lock()
			for client := range h.Clients {
				select {
				case client.Send <- message:
				default:
					// Kuyruk doluysa bu istemciyi düş, bağlantısını kapat
					delete(h.Clients, client)
					close(client.Send)
				}
			}
			h.mu.Unlock()
		}
	}
}
