package ws

// TelemetryPacket, bir sensör kontrolöründen gelen ham telemetri verisinin
// Go karşılığıdır. JSON olarak WebSocket üzerinden iletilir.
type TelemetryPacket struct {
	DeviceID   string    `json:"device_id"`   // Hangi cihazdan geldiği
	Timestamp  int64     `json:"timestamp"`   // Unix epoch (ms)
	Readings   []float64 `json:"readings"`    // W=32 sliding window sensör verisi
	SensorType string    `json:"sensor_type"` // Örn: "pressure", "temperature"
}
