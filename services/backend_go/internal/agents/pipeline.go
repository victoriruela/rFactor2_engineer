package agents

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"regexp"
	"strconv"
	"strings"
	"sync"

	"github.com/rs/zerolog/log"

	"github.com/viciruela/rfactor2-engineer/internal/domain"
	"github.com/viciruela/rfactor2-engineer/internal/ollama"
)

// SkippedSections are setup sections excluded from specialist analysis.
var SkippedSections = map[string]bool{
	"BASIC":       true,
	"LEFTFENDER":  true,
	"RIGHTFENDER": true,
}

// AxlePairs defines bilateral symmetry pairs.
var AxlePairs = [][2]string{
	{"FRONTLEFT", "FRONTRIGHT"},
	{"REARLEFT", "REARRIGHT"},
}

// ProgressEvent reports pipeline progress to callers via the ProgressFn callback.
type ProgressEvent struct {
	Type    string `json:"type"`    // "progress" | "result" | "error"
	Agent   string `json:"agent"`   // "driving" | "specialist" | "chief"
	Section string `json:"section"` // specialist section name, if applicable
	Message string `json:"message"`
}

// ProgressFn is an optional callback receiving real-time pipeline events.
type ProgressFn func(ProgressEvent)

// Pipeline orchestrates the 4-agent analysis pipeline.
type Pipeline struct {
	Client      *ollama.Client
	MappingPath string
}

// NewPipeline creates a new analysis pipeline.
func NewPipeline(client *ollama.Client, mappingPath string) *Pipeline {
	return &Pipeline{Client: client, MappingPath: mappingPath}
}

// Analyze runs the full 4-agent pipeline and returns the analysis response.
// progress is optional; pass nil to disable streaming events.
func (p *Pipeline) Analyze(ctx context.Context, telemetrySummary string, sessionStats *domain.SessionStats, setup *domain.Setup, fixedParams []string) (*domain.AnalysisResponse, error) {
	return p.AnalyzeWithProgress(ctx, telemetrySummary, sessionStats, setup, fixedParams, nil)
}

// AnalyzeWithProgress is like Analyze but calls progress for each pipeline milestone.
func (p *Pipeline) AnalyzeWithProgress(ctx context.Context, telemetrySummary string, sessionStats *domain.SessionStats, setup *domain.Setup, fixedParams []string, progress ProgressFn) (*domain.AnalysisResponse, error) {
	emit := func(ev ProgressEvent) {
		if progress != nil {
			progress(ev)
		}
	}

	if err := p.Client.EnsureRunning(ctx); err != nil {
		return nil, fmt.Errorf("ensuring ollama: %w", err)
	}

	fixedParamsJSON, _ := json.Marshal(fixedParams)

	// 1. Driving analysis
	emit(ProgressEvent{Type: "progress", Agent: "driving", Message: "Analizando datos de conducción con el agente de telemetría..."})
	log.Info().Msg("Running driving analysis agent...")
	drivingAnalysis, err := p.runDrivingAgent(ctx, telemetrySummary, sessionStats)
	if err != nil {
		log.Error().Err(err).Msg("Driving analysis failed")
		drivingAnalysis = "Error en el análisis de conducción: " + err.Error()
		emit(ProgressEvent{Type: "progress", Agent: "driving", Message: "Error en análisis de conducción: " + err.Error()})
	} else {
		emit(ProgressEvent{Type: "progress", Agent: "driving", Message: "Análisis de conducción completado."})
	}

	// 2. Section specialists (concurrent goroutines)
	emit(ProgressEvent{Type: "progress", Agent: "specialist", Message: "Lanzando agentes especialistas de setup por secciones..."})
	log.Info().Msg("Running section specialist agents...")
	specialistReports := p.runSpecialistsWithProgress(ctx, telemetrySummary, setup, string(fixedParamsJSON), emit)

	// 3. Chief engineer consolidation
	emit(ProgressEvent{Type: "progress", Agent: "chief", Message: "Ingeniero jefe consolidando propuestas de los especialistas..."})
	log.Info().Msg("Running chief engineer agent...")
	chiefResult, err := p.runChiefEngineer(ctx, telemetrySummary, setup, specialistReports, string(fixedParamsJSON))
	if err != nil {
		log.Error().Err(err).Msg("Chief engineer failed")
		chiefResult = &chiefOutput{Reasoning: "Error en el ingeniero jefe: " + err.Error()}
		emit(ProgressEvent{Type: "progress", Agent: "chief", Message: "Error en ingeniero jefe: " + err.Error()})
	} else {
		emit(ProgressEvent{Type: "progress", Agent: "chief", Message: "Ingeniero jefe: " + truncate(chiefResult.Reasoning, 300)})
	}

	// 4. Post-processing: axle symmetry
	enforceAxleSymmetry(chiefResult, setup)

	// 5. Format response
	return p.formatResponse(drivingAnalysis, specialistReports, chiefResult, setup, sessionStats, telemetrySummary), nil
}

func truncate(s string, max int) string {
	r := []rune(s)
	if len(r) <= max {
		return s
	}
	return string(r[:max]) + "…"
}

func (p *Pipeline) runDrivingAgent(ctx context.Context, summary string, stats *domain.SessionStats) (string, error) {
	prompt := strings.ReplaceAll(DRIVING_PROMPT, "{telemetry_summary}", summary)
	statsJSON, _ := json.MarshalIndent(stats, "", "  ")
	prompt = strings.ReplaceAll(prompt, "{session_stats}", string(statsJSON))

	return p.Client.Generate(ctx, prompt, "")
}

func (p *Pipeline) runSpecialists(ctx context.Context, summary string, setup *domain.Setup, fixedParams string) []domain.SectionReport {
	return p.runSpecialistsWithProgress(ctx, summary, setup, fixedParams, nil)
}

func (p *Pipeline) runSpecialistsWithProgress(ctx context.Context, summary string, setup *domain.Setup, fixedParams string, emit ProgressFn) []domain.SectionReport {
	var mu sync.Mutex
	var wg sync.WaitGroup
	var reports []domain.SectionReport

	for sectionName, section := range setup.Sections {
		if SkippedSections[sectionName] {
			continue
		}

		// Skip if all params are gear-related
		hasNonGear := false
		for k := range section.Params {
			if !isGearParam(k) {
				hasNonGear = true
				break
			}
		}
		if !hasNonGear {
			continue
		}

		wg.Add(1)
		go func(secName string, sec *domain.SetupSection) {
			defer wg.Done()

			if emit != nil {
				emit(ProgressEvent{Type: "progress", Agent: "specialist", Section: secName, Message: "Especialista analizando sección: " + secName})
			}

			report, err := p.runSingleSpecialist(ctx, summary, secName, sec, fixedParams)
			if err != nil {
				log.Error().Err(err).Str("section", secName).Msg("Specialist failed")
				report = &domain.SectionReport{
					Section: secName,
					Summary: "Error en el análisis: " + err.Error(),
				}
			} else if emit != nil {
				msg := "Especialista " + secName + " completado"
				if len(report.Items) > 0 {
					msg += fmt.Sprintf(" (%d cambios propuestos)", len(report.Items))
				} else {
					msg += " (sin cambios)"
				}
				emit(ProgressEvent{Type: "progress", Agent: "specialist", Section: secName, Message: msg})
			}

			mu.Lock()
			reports = append(reports, *report)
			mu.Unlock()
		}(sectionName, section)
	}

	wg.Wait()
	return reports
}

func (p *Pipeline) runSingleSpecialist(ctx context.Context, summary, sectionName string, section *domain.SetupSection, fixedParams string) (*domain.SectionReport, error) {
	paramsJSON, _ := json.MarshalIndent(section.Params, "", "  ")

	prompt := strings.ReplaceAll(SECTION_AGENT_PROMPT, "{section_name}", sectionName)
	prompt = strings.ReplaceAll(prompt, "{telemetry_summary}", summary)
	prompt = strings.ReplaceAll(prompt, "{section_params}", string(paramsJSON))
	prompt = strings.ReplaceAll(prompt, "{fixed_params}", fixedParams)

	response, err := p.Client.Generate(ctx, prompt, "")
	if err != nil {
		return nil, err
	}

	report, err := parseSpecialistResponse(sectionName, response)
	if err != nil {
		return nil, fmt.Errorf("parsing specialist response for %s: %w", sectionName, err)
	}

	return report, nil
}

type chiefOutput struct {
	Sections  []domain.SectionReport
	Reasoning string
}

func (p *Pipeline) runChiefEngineer(ctx context.Context, summary string, setup *domain.Setup, specialistReports []domain.SectionReport, fixedParams string) (*chiefOutput, error) {
	setupJSON, _ := json.MarshalIndent(setup, "", "  ")
	reportsJSON, _ := json.MarshalIndent(specialistReports, "", "  ")

	prompt := strings.ReplaceAll(CHIEF_ENGINEER_PROMPT, "{telemetry_summary}", summary)
	prompt = strings.ReplaceAll(prompt, "{full_setup}", string(setupJSON))
	prompt = strings.ReplaceAll(prompt, "{specialist_reports}", string(reportsJSON))
	prompt = strings.ReplaceAll(prompt, "{fixed_params}", fixedParams)

	response, err := p.Client.Generate(ctx, prompt, "")
	if err != nil {
		return nil, err
	}

	return parseChiefResponse(response)
}

func (p *Pipeline) formatResponse(drivingAnalysis string, specialistReports []domain.SectionReport, chief *chiefOutput, setup *domain.Setup, stats *domain.SessionStats, summary string) *domain.AnalysisResponse {
	setupAnalysis := make(map[string][]domain.SetupChange)
	fullSetup := make(map[string][]domain.SetupChange)

	if chief != nil {
		for _, sec := range chief.Sections {
			changes := make([]domain.SetupChange, 0, len(sec.Items))
			for _, item := range sec.Items {
				change := item
				// Compute change percentage
				if origSec, ok := setup.Sections[sec.Section]; ok {
					if origVal, ok := origSec.Params[item.Parameter]; ok {
						change.OldValue = origVal
						change.ChangePct = computeChangePct(origVal, item.NewValue)
					}
				}
				changes = append(changes, change)
			}
			if len(changes) > 0 {
				setupAnalysis[sec.Section] = changes
				fullSetup[sec.Section] = changes
			}
		}
	}

	// Fallback: if chief produced no items, use specialist reports directly
	if len(setupAnalysis) == 0 {
		log.Warn().Msg("Chief produced no setup changes; falling back to specialist reports")
		for _, rep := range specialistReports {
			if len(rep.Items) == 0 {
				continue
			}
			changes := make([]domain.SetupChange, 0, len(rep.Items))
			for _, item := range rep.Items {
				change := item
				if origSec, ok := setup.Sections[rep.Section]; ok {
					if origVal, ok := origSec.Params[item.Parameter]; ok {
						change.OldValue = origVal
						change.ChangePct = computeChangePct(origVal, item.NewValue)
					}
				}
				changes = append(changes, change)
			}
			if len(changes) > 0 {
				setupAnalysis[rep.Section] = changes
				fullSetup[rep.Section] = changes
			}
		}
	}

	chiefReasoning := ""
	if chief != nil {
		chiefReasoning = chief.Reasoning
	}

	return &domain.AnalysisResponse{
		DrivingAnalysis:  drivingAnalysis,
		SetupAnalysis:    setupAnalysis,
		FullSetup:        fullSetup,
		SessionStats:     stats,
		AgentReports:     specialistReports,
		TelemetrySummary: summary,
		ChiefReasoning:   chiefReasoning,
	}
}

// --- Parsing helpers ---

func parseSpecialistResponse(section, response string) (*domain.SectionReport, error) {
	jsonStr := ExtractJSON(response)
	if jsonStr == "" {
		return &domain.SectionReport{Section: section, Summary: response}, nil
	}

	var raw struct {
		Items   []json.RawMessage `json:"items"`
		Summary string            `json:"summary"`
		// Alternate keys (Jimmy)
		Recomendaciones []json.RawMessage `json:"recomendaciones"`
		Resumen         string            `json:"resumen"`
	}
	if err := json.Unmarshal([]byte(jsonStr), &raw); err != nil {
		return &domain.SectionReport{Section: section, Summary: response}, nil
	}

	items := raw.Items
	if len(items) == 0 {
		items = raw.Recomendaciones
	}
	summary := raw.Summary
	if summary == "" {
		summary = raw.Resumen
	}

	var changes []domain.SetupChange
	for _, rawItem := range items {
		change := normalizeSetupChange(rawItem)
		if change.Parameter != "" {
			changes = append(changes, change)
		}
	}

	return &domain.SectionReport{
		Section: section,
		Items:   changes,
		Summary: summary,
	}, nil
}

func normalizeSetupChange(raw json.RawMessage) domain.SetupChange {
	var m map[string]any
	if err := json.Unmarshal(raw, &m); err != nil {
		return domain.SetupChange{}
	}

	return domain.SetupChange{
		Parameter: getStringAlt(m, "parameter", "parametro"),
		NewValue:  getStringAlt(m, "new_value", "nuevo_valor", "newValue", "nuevoValor"),
		Reason:    getStringAlt(m, "reason", "motivo", "razon"),
	}
}

func getStringAlt(m map[string]any, keys ...string) string {
	for _, k := range keys {
		if v, ok := m[k]; ok {
			return fmt.Sprintf("%v", v)
		}
	}
	return ""
}

func parseChiefResponse(response string) (*chiefOutput, error) {
	jsonStr := ExtractJSON(response)
	if jsonStr == "" {
		return &chiefOutput{Reasoning: response}, nil
	}

	var raw struct {
		FullSetup struct {
			Sections []struct {
				Section string            `json:"section"`
				Items   []json.RawMessage `json:"items"`
			} `json:"sections"`
		} `json:"full_setup"`
		ChiefReasoning string `json:"chief_reasoning"`
	}
	if err := json.Unmarshal([]byte(jsonStr), &raw); err != nil {
		return &chiefOutput{Reasoning: response}, nil
	}

	var sections []domain.SectionReport
	for _, sec := range raw.FullSetup.Sections {
		var changes []domain.SetupChange
		for _, rawItem := range sec.Items {
			change := normalizeSetupChange(rawItem)
			if change.Parameter != "" {
				changes = append(changes, change)
			}
		}
		sections = append(sections, domain.SectionReport{
			Section: sec.Section,
			Items:   changes,
		})
	}

	return &chiefOutput{
		Sections:  sections,
		Reasoning: raw.ChiefReasoning,
	}, nil
}

// --- Utility functions ---

// ExtractJSON extracts a JSON object from potentially messy LLM output using brace-depth counting.
func ExtractJSON(text string) string {
	start := strings.IndexByte(text, '{')
	if start < 0 {
		return ""
	}

	depth := 0
	inString := false
	escaped := false
	end := -1

	for i := start; i < len(text); i++ {
		ch := text[i]
		if escaped {
			escaped = false
			continue
		}
		if ch == '\\' && inString {
			escaped = true
			continue
		}
		if ch == '"' {
			inString = !inString
			continue
		}
		if inString {
			continue
		}
		if ch == '{' {
			depth++
		} else if ch == '}' {
			depth--
			if depth == 0 {
				end = i + 1
				break
			}
		}
	}

	if end <= start {
		return ""
	}

	jsonStr := text[start:end]
	// Clean trailing commas before closing braces/brackets
	jsonStr = cleanTrailingCommas(jsonStr)
	return jsonStr
}

var trailingCommaRe = regexp.MustCompile(`,\s*([}\]])`)

func cleanTrailingCommas(s string) string {
	return trailingCommaRe.ReplaceAllString(s, "$1")
}

// ExtractNumeric extracts the first numeric value from a string.
func ExtractNumeric(s string) (float64, bool) {
	re := regexp.MustCompile(`-?\d+\.?\d*`)
	match := re.FindString(s)
	if match == "" {
		return 0, false
	}
	v, err := strconv.ParseFloat(match, 64)
	if err != nil {
		return 0, false
	}
	return v, true
}

func computeChangePct(oldRaw, newRaw string) string {
	oldVal, okOld := ExtractNumeric(oldRaw)
	newVal, okNew := ExtractNumeric(newRaw)
	if !okOld || !okNew || oldVal == 0 {
		return ""
	}
	pct := ((newVal - oldVal) / math.Abs(oldVal)) * 100
	return fmt.Sprintf("%+.1f%%", pct)
}

func isGearParam(name string) bool {
	lower := strings.ToLower(name)
	return strings.Contains(lower, "gear") && strings.Contains(lower, "setting")
}

func enforceAxleSymmetry(chief *chiefOutput, setup *domain.Setup) {
	if chief == nil {
		return
	}

	sectionMap := make(map[string]*domain.SectionReport)
	for i := range chief.Sections {
		sectionMap[chief.Sections[i].Section] = &chief.Sections[i]
	}

	for _, pair := range AxlePairs {
		left, hasLeft := sectionMap[pair[0]]
		right, hasRight := sectionMap[pair[1]]
		if !hasLeft || !hasRight {
			continue
		}

		leftParams := make(map[string]*domain.SetupChange)
		for i := range left.Items {
			leftParams[left.Items[i].Parameter] = &left.Items[i]
		}

		for i := range right.Items {
			rc := &right.Items[i]
			if lc, ok := leftParams[rc.Parameter]; ok {
				// Both sides have a change for same param — harmonize to more conservative
				harmonizeSymmetricPair(lc, rc, setup, pair[0], pair[1])
			}
		}
	}
}

func harmonizeSymmetricPair(left, right *domain.SetupChange, setup *domain.Setup, leftSec, rightSec string) {
	leftNew, okL := ExtractNumeric(left.NewValue)
	rightNew, okR := ExtractNumeric(right.NewValue)
	if !okL || !okR {
		return
	}

	if leftNew == rightNew {
		return // Already symmetric
	}

	// Get original values
	var leftOrig, rightOrig float64
	if s, ok := setup.Sections[leftSec]; ok {
		if v, ok := s.Params[left.Parameter]; ok {
			leftOrig, _ = ExtractNumeric(v)
		}
	}
	if s, ok := setup.Sections[rightSec]; ok {
		if v, ok := s.Params[right.Parameter]; ok {
			rightOrig, _ = ExtractNumeric(v)
		}
	}

	// Pick the more conservative value (smaller delta from original)
	leftDelta := math.Abs(leftNew - leftOrig)
	rightDelta := math.Abs(rightNew - rightOrig)

	var chosen float64
	if leftDelta <= rightDelta {
		chosen = leftNew
	} else {
		chosen = rightNew
	}

	chosenStr := fmt.Sprintf("%.0f", chosen)
	symmetryNote := " [Armonizado por simetría de eje]"

	left.NewValue = chosenStr
	left.Reason += symmetryNote
	right.NewValue = chosenStr
	right.Reason += symmetryNote
}
