package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"
)

const tokenTTL = 800 * time.Millisecond

type issueRequest struct {
	WorkerID    string `json:"worker_id"`
	CommandHash string `json:"command_hash"`
	Timestamp   int64  `json:"timestamp"`
}

type issueResponse struct {
	Token     string `json:"token"`
	ExpiresAt int64  `json:"expires_at"`
	Valid     bool   `json:"valid"`
}

type verifyRequest struct {
	Token       string `json:"token"`
	WorkerID    string `json:"worker_id"`
	CommandHash string `json:"command_hash"`
	Timestamp   int64  `json:"timestamp"`
}

type verifyResponse struct {
	Valid  bool   `json:"valid"`
	Reason string `json:"reason"`
}

func main() {
	port := env("PORT", "8081")
	secret := os.Getenv("SENTINEL_HMAC_SECRET")
	if secret == "" {
		log.Fatal("missing SENTINEL_HMAC_SECRET")
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", withCORS(func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	}))
	mux.HandleFunc("/token/issue", withCORS(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"reason": "method_not_allowed"})
			return
		}
		var req issueRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"reason": "invalid_json"})
			return
		}
		if expired(req.Timestamp) {
			logJSON("issue_rejected", map[string]any{"worker_id": req.WorkerID, "reason": "timestamp_expired"})
			writeJSON(w, http.StatusUnauthorized, verifyResponse{Valid: false, Reason: "timestamp_expired"})
			return
		}
		token := computeToken(secret, req.WorkerID, req.CommandHash, req.Timestamp)
		expires := req.Timestamp + tokenTTL.Milliseconds()
		logJSON("token_issue", map[string]any{"worker_id": req.WorkerID, "command_hash": req.CommandHash, "expires_at": expires})
		writeJSON(w, http.StatusOK, issueResponse{Token: token, ExpiresAt: expires, Valid: true})
	}))
	mux.HandleFunc("/token/verify", withCORS(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"reason": "method_not_allowed"})
			return
		}
		var req verifyRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"reason": "invalid_json"})
			return
		}
		expected := computeToken(secret, req.WorkerID, req.CommandHash, req.Timestamp)
		if expired(req.Timestamp) {
			logJSON("token_verify", map[string]any{"worker_id": req.WorkerID, "valid": false, "reason": "timestamp_expired"})
			writeJSON(w, http.StatusUnauthorized, verifyResponse{Valid: false, Reason: "timestamp_expired"})
			return
		}
		if !hmac.Equal([]byte(expected), []byte(req.Token)) {
			logJSON("token_verify", map[string]any{"worker_id": req.WorkerID, "valid": false, "reason": "token_mismatch"})
			writeJSON(w, http.StatusUnauthorized, verifyResponse{Valid: false, Reason: "token_mismatch"})
			return
		}
		logJSON("token_verify", map[string]any{"worker_id": req.WorkerID, "valid": true})
		writeJSON(w, http.StatusOK, verifyResponse{Valid: true, Reason: "ok"})
	}))

	server := &http.Server{
		Addr:              ":" + port,
		Handler:           mux,
		ReadHeaderTimeout: 3 * time.Second,
	}

	log.Printf("sentinel-engine listening on %s", port)
	log.Fatal(server.ListenAndServe())
}

func computeToken(secret, workerID, commandHash string, timestamp int64) string {
	payload := fmt.Sprintf("%s:%s:%d", workerID, commandHash, timestamp)
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(payload))
	return hex.EncodeToString(mac.Sum(nil))
}

func expired(timestamp int64) bool {
	now := time.Now().UnixMilli()
	return now-timestamp > tokenTTL.Milliseconds()
}

func env(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func withCORS(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next(w, r)
	}
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func logJSON(event string, fields map[string]any) {
	fields["event"] = event
	fields["ts"] = strconv.FormatInt(time.Now().UnixMilli(), 10)
	encoded, err := json.Marshal(fields)
	if err != nil {
		log.Printf(`{"event":"marshal_error","error":"%s"}`, err.Error())
		return
	}
	log.Print(string(encoded))
}
