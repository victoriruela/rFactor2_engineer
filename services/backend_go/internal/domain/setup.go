package domain

// SetupSection represents a section in an .svm setup file.
type SetupSection struct {
	Name   string            `json:"name"`
	Params map[string]string `json:"params"`
	// ReadOnlyParams lists parameter keys that came from commented-out lines in the SVM
	// (not adjustable in-game). They are included in Params for display/AI context but
	// must never be proposed as changes.
	ReadOnlyParams []string `json:"read_only_params,omitempty"`
}

// Setup represents the full vehicle setup from an .svm file.
type Setup struct {
	Sections map[string]*SetupSection `json:"sections"`
}

// NewSetup creates an empty setup.
func NewSetup() *Setup {
	return &Setup{Sections: make(map[string]*SetupSection)}
}

// SetupChange represents a single parameter change recommendation.
type SetupChange struct {
	Parameter string `json:"parameter"`
	OldValue  string `json:"old_value"`
	NewValue  string `json:"new_value"`
	Reason    string `json:"reason"`
	ChangePct string `json:"change_pct,omitempty"`
}

// SectionReport is the specialist agent output for one setup section.
type SectionReport struct {
	Section string        `json:"section"`
	Items   []SetupChange `json:"items"`
	Summary string        `json:"summary"`
}
