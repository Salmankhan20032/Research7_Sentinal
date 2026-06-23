package main

import (
	"fmt"
	"log"

	// Kendi yazdığımız config paketini projemize dahil ediyoruz
	"sentinel-model-b/internal/config"
)

func main() {
	fmt.Println("SENTINEL Model B (Public Broker) Başlatılıyor...")

	// Konfigürasyonları yükle
	cfg := config.Load()

	// Yüklenen ayarları kontrol amaçlı ekrana basıyoruz
	log.Printf("Dinlenilecek Port : %s\n", cfg.BrokerPort)
	log.Printf("Model A Adresi    : %s\n", cfg.ModelA_URL)
	log.Printf("PLC Adresi        : %s\n", cfg.PLC_URL)

	fmt.Println("Sistem konfigürasyonları başarıyla yüklendi. Hazır.")
}
