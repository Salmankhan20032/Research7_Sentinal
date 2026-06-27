package logger

import (
	"log/slog"
	"os"
	"strings"
)

// Init, uygulama genelinde kullanılacak slog logger'ını başlatır.
// LOG_FORMAT=text → insan okunabilir; diğer her şey → JSON (production varsayılanı).
// LOG_LEVEL=debug|info|warn|error → seviye filtresi; varsayılan info.
func Init() *slog.Logger {
	level := parseLevel(os.Getenv("LOG_LEVEL"))
	opts := &slog.HandlerOptions{Level: level}

	var handler slog.Handler
	if strings.ToLower(os.Getenv("LOG_FORMAT")) == "text" {
		handler = slog.NewTextHandler(os.Stdout, opts)
	} else {
		handler = slog.NewJSONHandler(os.Stdout, opts)
	}

	l := slog.New(handler)
	slog.SetDefault(l) // Tüm pakette slog.Info(...) doğrudan kullanılabilir
	return l
}

func parseLevel(s string) slog.Level {
	switch strings.ToLower(s) {
	case "debug":
		return slog.LevelDebug
	case "warn":
		return slog.LevelWarn
	case "error":
		return slog.LevelError
	default:
		return slog.LevelInfo
	}
}
