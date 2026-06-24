package command

// WriteRequest, operatör panosundan veya üst sistemden gelen
// fiziksel yazma komutunun yapısıdır.
type WriteRequest struct {
	DeviceID string  `json:"device_id"` // Hedef cihaz kimliği
	Register string  `json:"register"`  // Yazılacak register adresi (örn: "HR001")
	Value    float64 `json:"value"`     // Yazılacak değer
}

// WriteResponse, komut işleminin sonucunu operatöre dönen yanıt yapısıdır.
type WriteResponse struct {
	Success  bool   `json:"success"`
	Routed   string `json:"routed"` // "plc" veya "honeypot"
	Message  string `json:"message"`
	DeviceID string `json:"device_id"`
	Register string `json:"register"`
}
