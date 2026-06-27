

# ─── Aşama 1: Builder ────────────────────────────────────────────────────────
# Go binary'sini derler; final imaja yalnızca binary kopyalanır.
FROM golang:1.25-alpine AS builder

# Derleme için gerekli araçlar
RUN apk add --no-cache git ca-certificates tzdata

WORKDIR /build

# Önce bağımlılıkları kopyala ve indir (Docker cache katmanı için)
COPY go.mod go.sum ./
RUN go mod download

# Kaynak kodu kopyala ve derle
COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -ldflags="-w -s" -o sentinel-model-b ./cmd/main.go

# ─── Aşama 2: Final ──────────────────────────────────────────────────────────
# Yalnızca binary ve sertifikalar — imaj boyutu ~10MB civarında olur.
FROM alpine:3.19

RUN apk add --no-cache ca-certificates tzdata

WORKDIR /app

# Builder aşamasından sadece binary'i al
COPY --from=builder /build/sentinel-model-b .

# Çalışma zamanı kullanıcısı (root olarak çalıştırmamak için)
RUN addgroup -S sentinel && adduser -S sentinel -G sentinel
USER sentinel

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:8080/health || exit 1

ENTRYPOINT ["./sentinel-model-b"]