package middleware

import (
	"log"
	"net"
	"net/http"
	"sync"
	"time"

	"golang.org/x/time/rate"
)

// ipLimiter, tek bir IP için rate limiter ve son görülme zamanını tutar.
type ipLimiter struct {
	limiter  *rate.Limiter
	lastSeen time.Time
}

// RateLimiter, IP bazlı istek sınırlayıcıyı yöneten yapıdır.
type RateLimiter struct {
	mu       sync.Mutex
	limiters map[string]*ipLimiter
	rps      rate.Limit // Saniyedeki maksimum istek sayısı
	burst    int        // Anlık izin verilen maksimum istek patlaması
}

// NewRateLimiter, belirtilen RPS ve burst değerleriyle yeni bir limiter oluşturur.
// Ayrıca 3 dakikada bir eski kayıtları temizleyen goroutine başlatır.
func NewRateLimiter(rps float64, burst int) *RateLimiter {
	rl := &RateLimiter{
		limiters: make(map[string]*ipLimiter),
		rps:      rate.Limit(rps),
		burst:    burst,
	}
	go rl.cleanupLoop()
	return rl
}

// getLimiter, IP için mevcut limiter'ı döner; yoksa yeni oluşturur.
func (rl *RateLimiter) getLimiter(ip string) *rate.Limiter {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	if ipl, exists := rl.limiters[ip]; exists {
		ipl.lastSeen = time.Now()
		return ipl.limiter
	}

	l := rate.NewLimiter(rl.rps, rl.burst)
	rl.limiters[ip] = &ipLimiter{limiter: l, lastSeen: time.Now()}
	return l
}

// cleanupLoop, 3 dakikadır istek atmayan IP'leri bellekten temizler.
func (rl *RateLimiter) cleanupLoop() {
	ticker := time.NewTicker(3 * time.Minute)
	defer ticker.Stop()
	for range ticker.C {
		rl.mu.Lock()
		for ip, ipl := range rl.limiters {
			if time.Since(ipl.lastSeen) > 3*time.Minute {
				delete(rl.limiters, ip)
			}
		}
		rl.mu.Unlock()
	}
}

// Limit, HTTP handler'ı rate limiting middleware'ine sarar.
// Limiti aşan IP'lere 429 Too Many Requests döner.
func (rl *RateLimiter) Limit(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ip, _, err := net.SplitHostPort(r.RemoteAddr)
		if err != nil {
			ip = r.RemoteAddr
		}

		if !rl.getLimiter(ip).Allow() {
			log.Printf("[RATELIMIT] %s — istek limiti aşıldı", ip)
			http.Error(w, `{"error":"rate limit aşıldı, lütfen bekleyin"}`, http.StatusTooManyRequests)
			return
		}

		next(w, r)
	}
}
