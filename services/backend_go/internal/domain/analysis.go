package domain

// AnalysisRequest holds parameters for an analysis run.
type AnalysisRequest struct {
	TelemetrySummary string     `json:"telemetry_summary"`
	Setup            *Setup     `json:"setup"`
	GPSData          []GPSPoint `json:"gps_data,omitempty"`
	Model            string     `json:"model,omitempty"`
	Provider         string     `json:"provider,omitempty"`
	FixedParams      []string   `json:"fixed_params,omitempty"`
}

// AnalysisResponse is the full result returned to the frontend.
type AnalysisResponse struct {
	CircuitData         []GPSPoint               `json:"circuit_data"`
	IssuesOnMap         []IssueMarker            `json:"issues_on_map"`
	DrivingAnalysis     string                   `json:"driving_analysis"`
	SetupAnalysis       map[string][]SetupChange `json:"setup_analysis"`
	FullSetup           map[string][]SetupChange `json:"full_setup"`
	SessionStats        *SessionStats            `json:"session_stats"`
	LapsData            []LapStats               `json:"laps_data"`
	AgentReports        []SectionReport          `json:"agent_reports"`
	TelemetrySummary    string                   `json:"telemetry_summary_sent"`
	ChiefReasoning      string                   `json:"chief_reasoning"`
	TelemetryTimeSeries []TelemetrySample        `json:"telemetry_series"`
}

// IssueMarker is a point on the circuit map where a driving issue was detected.
type IssueMarker struct {
	Lat         float64 `json:"lat"`
	Lon         float64 `json:"lon"`
	Description string  `json:"description"`
	Severity    string  `json:"severity"`
}

// UploadInit is the response to POST /api/uploads/init.
type UploadInit struct {
	UploadID  string `json:"upload_id"`
	ChunkSize int    `json:"chunk_size"`
	Filename  string `json:"filename"`
}

// ChunkResponse is the response to PUT /api/uploads/{id}/chunk.
type ChunkResponse struct {
	UploadID      string `json:"upload_id"`
	ChunkIndex    int    `json:"chunk_index"`
	BytesReceived int64  `json:"bytes_received"`
}

// CompleteResponse is the response to POST /api/uploads/{id}/complete.
type CompleteResponse struct {
	Filename      string `json:"filename"`
	BytesReceived int64  `json:"bytes_received"`
}

// SessionInfo describes a complete uploaded session.
type SessionInfo struct {
	ID        string `json:"id"`
	Telemetry string `json:"telemetry"`
	SVM       string `json:"svm"`
}
