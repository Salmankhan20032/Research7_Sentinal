package main

import (
	"fmt"
	"log"
	"os"
)

func main() {
	// env içerisindeki değişkenlere göre değiştirebiliriz
	modelAURL := os.Getenv("MODEL_A_URL")
	plcURL := os.Getenv("PLC_URL")

	// Eğer yoksa da local olsun
	if modelAURL == "" {
		log.Println("UYARI: MODEL_A_URL çevresel değişkeni bulunamadı. Varsayılan değer atanıyor: http://localhost:8000")
		modelAURL = "http://localhost:8000"
	}
	if plcURL == "" {
		log.Println("UYARI: PLC_URL çevresel değişkeni bulunamadı. Varsayılan değer atanıyor: http://localhost:5020")
		plcURL = "http://localhost:5020"
	}

	// Print
	fmt.Println("SENTINEL Model B (Public Broker) Başlatılıyor...")
	fmt.Printf("Model A (Trust Engine) Adresi: %s\n", modelAURL)
	fmt.Printf("PLC (Sensor Controller) Adresi: %s\n", plcURL)
}

/*

package main

import "fmt"

func main() {
    fmt.Println("SENTINEL Model B (Public Broker) Başlatılıyor...")
}

*/
