package agents

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"

	"github.com/rs/zerolog/log"

	"github.com/viciruela/rfactor2-engineer/internal/config"
	"github.com/viciruela/rfactor2-engineer/internal/domain"
	"github.com/viciruela/rfactor2-engineer/internal/ollama"
	"github.com/viciruela/rfactor2-engineer/internal/parsers"
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

// Pipeline orchestrates the multi-agent analysis pipeline.
type Pipeline struct {
	Client       *ollama.Client
	MappingPath  string // deprecated — kept for compat
	DataDir      string
	PhysicsRules *PhysicsRuleset
	Routing      *config.ModelRouting
}

// NewPipeline creates a new analysis pipeline.
// dataDir points to the application data directory containing knowledge/ and physics_rules.json.
func NewPipeline(client *ollama.Client, dataDir string) *Pipeline {
	p := &Pipeline{Client: client, DataDir: dataDir, MappingPath: dataDir}
	if dataDir != "" {
		rulesPath := filepath.Join(dataDir, "physics_rules.json")
		rules, err := LoadPhysicsRules(rulesPath)
		if err != nil {
			log.Warn().Err(err).Msg("physics rules not loaded — validation disabled")
		} else {
			p.PhysicsRules = rules
			log.Info().Int("domains", len(rules.Domains)).Msg("physics rules loaded")
		}

		routingPath := filepath.Join(dataDir, "model_routing.json")
		routing, err := config.LoadModelRouting(routingPath)
		if err != nil {
			log.Warn().Err(err).Msg("model routing not loaded — using global defaults")
		} else if routing != nil {
			p.Routing = routing
			log.Info().Int("assignments", len(routing.Assignments)).Msg("model routing loaded")
		}
	}
	return p
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

	// Collect read-only params from setup sections and add to fixed params
	allFixedParams := mergeReadOnlyParams(setup, fixedParams)
	filteredSetup := excludeFixedParamsFromSetup(setup, allFixedParams)

	if err := p.Client.EnsureRunning(ctx); err != nil {
		return nil, fmt.Errorf("ensuring ollama: %w", err)
	}

	fixedParamsJSON, _ := json.Marshal(allFixedParams)

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

	// 2. Domain engineers (4 parallel — replaces telemetry specialists + section specialists)
	emit(ProgressEvent{Type: "progress", Agent: "domain_engineers", Message: "Lanzando ingenieros de dominio (suspensión, chasis, aero, tren motriz)..."})
	log.Info().Msg("Running domain engineers...")
	domainResults := p.runDomainEngineers(ctx, telemetrySummary, sessionStats, filteredSetup, string(fixedParamsJSON), emit)

	// 2.5 Physics validation on domain engineer outputs
	if p.PhysicsRules != nil {
		for i := range domainResults {
			for j := range domainResults[i].Sections {
				validated, valSummary := validateAgentReport(domainResults[i].Sections[j], p.PhysicsRules, allFixedParams)
				domainResults[i].Sections[j] = validated
				if valSummary.LowConfidence {
					log.Warn().Str("agent", domainResults[i].Label).Str("section", validated.Section).Msg("domain engineer section flagged low-confidence")
				}
			}
		}
	}

	// Build telemetry display from domain engineer findings
	telemetryAnalysis := buildDomainEngineerAnalysisDisplay(domainResults)

	// Flatten domain engineer sections into specialist reports (for fallback/display)
	var specialistReports []domain.SectionReport
	for _, dr := range domainResults {
		specialistReports = append(specialistReports, dr.Sections...)
	}
	specialistReports = filterLockedChanges(
		filterInvalidSectionReports(specialistReports, filteredSetup),
		allFixedParams,
	)

	// 3. Contradiction detection (deterministic — no LLM call)
	contradictions := detectContradictions(domainResults)
	if len(contradictions) > 0 {
		emit(ProgressEvent{Type: "progress", Agent: "contradictions", Message: fmt.Sprintf("Detectadas %d contradicciones entre ingenieros de dominio.", len(contradictions))})
	}

	// 4. Chief engineer consolidation with conflict brief
	emit(ProgressEvent{Type: "progress", Agent: "chief", Message: "Ingeniero jefe consolidando propuestas de los ingenieros de dominio..."})
	log.Info().Msg("Running chief engineer agent...")
	chiefResult, err := p.runChiefEngineerV2(ctx, telemetrySummary, filteredSetup, domainResults, contradictions, string(fixedParamsJSON))
	if err != nil {
		log.Error().Err(err).Msg("Chief engineer failed")
		chiefResult = &chiefOutput{Reasoning: "Error en el ingeniero jefe: " + err.Error()}
		emit(ProgressEvent{Type: "progress", Agent: "chief", Message: "Error en ingeniero jefe: " + err.Error()})
	} else {
		chiefResult = filterLockedChiefOutput(chiefResult, allFixedParams)
		chiefResult = filterInvalidSetupParams(chiefResult, filteredSetup)
		// Supplement chief output with specialist proposals it didn't explicitly include.
		// Implements the documented merge strategy: specialist proposals are the floor,
		// chief overrides only the params it explicitly returns.
		chiefResult = mergeSpecialistFloor(chiefResult, specialistReports)
		emit(ProgressEvent{Type: "progress", Agent: "chief", Message: "Ingeniero jefe: " + truncate(chiefResult.Reasoning, 300)})
	}

	// 4.5 Physics validation on chief output
	if p.PhysicsRules != nil {
		for i := range chiefResult.Sections {
			validated, _ := validateAgentReport(chiefResult.Sections[i], p.PhysicsRules, allFixedParams)
			chiefResult.Sections[i] = validated
		}
	}

	// 5. Post-processing: axle symmetry
	enforceAxleSymmetry(chiefResult, filteredSetup)

	// 6. Coherence pass: keep reason text aligned with final values after all guardrails.
	normalizeSectionReasonsWithFinalValues(specialistReports, filteredSetup)
	normalizeChiefReasonsWithFinalValues(chiefResult, filteredSetup)

	// 7. Format response
	return p.formatResponse(drivingAnalysis, telemetryAnalysis, specialistReports, chiefResult, filteredSetup, sessionStats, telemetrySummary), nil
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

	model, temp := p.modelForRole("driving")
	return p.Client.GenerateWithModel(ctx, prompt, "", model, temp)
}

// modelForRole returns the model and temperature for a given pipeline role.
// Falls back to the client's defaults when routing is absent or empty.
func (p *Pipeline) modelForRole(role string) (string, float64) {
	if p.Routing == nil {
		return "", -1 // empty → client defaults
	}
	return p.Routing.ForRole(role, ""), p.Routing.TempForRole(role, -1)
}

// --- Telemetry domain specialists ---

// telemetryFinding represents a single insight from a telemetry expert.
type telemetryFinding struct {
	Finding          string   `json:"finding"`
	Recommendation   string   `json:"recommendation"`
	AffectedSections []string `json:"affected_sections"`
}

// telemetryExpertOutput is the parsed JSON output from a telemetry specialist.
type telemetryExpertOutput struct {
	Findings []telemetryFinding `json:"findings"`
	Summary  string             `json:"summary"`
}

// runTelemetrySpecialists runs braking, cornering, tyre and mechanical balance experts in parallel.
// Returns: (insightsText for injection into setup prompts, analysisText for frontend display)
func (p *Pipeline) runTelemetrySpecialists(ctx context.Context, summary string, stats *domain.SessionStats, emit ProgressFn) (string, string) {
	var wg sync.WaitGroup
	var brakingResult, corneringResult, tyreResult, mechanicalResult string
	var brakingParsed, corneringParsed, tyreParsed, mechanicalParsed *telemetryExpertOutput

	wg.Add(4)

	go func() {
		defer wg.Done()
		if emit != nil {
			emit(ProgressEvent{Type: "progress", Agent: "telemetry", Section: "braking", Message: "Experto en frenado analizando zonas de frenada..."})
		}
		raw, err := p.runBrakingExpert(ctx, summary, stats)
		if err != nil {
			log.Error().Err(err).Msg("Braking expert failed")
			brakingResult = "Error en el experto de frenado: " + err.Error()
			return
		}
		brakingResult = raw
		brakingParsed = parseTelemetryExpertOutput(raw)
		if emit != nil {
			msg := "Experto en frenado completado"
			if brakingParsed != nil && len(brakingParsed.Findings) > 0 {
				msg += fmt.Sprintf(" (%d hallazgos)", len(brakingParsed.Findings))
			}
			emit(ProgressEvent{Type: "progress", Agent: "telemetry", Section: "braking", Message: msg})
		}
	}()

	go func() {
		defer wg.Done()
		if emit != nil {
			emit(ProgressEvent{Type: "progress", Agent: "telemetry", Section: "cornering", Message: "Experto en equilibrio analizando curvas..."})
		}
		raw, err := p.runCorneringExpert(ctx, summary, stats)
		if err != nil {
			log.Error().Err(err).Msg("Cornering expert failed")
			corneringResult = "Error en el experto de equilibrio: " + err.Error()
			return
		}
		corneringResult = raw
		corneringParsed = parseTelemetryExpertOutput(raw)
		if emit != nil {
			msg := "Experto en equilibrio completado"
			if corneringParsed != nil && len(corneringParsed.Findings) > 0 {
				msg += fmt.Sprintf(" (%d hallazgos)", len(corneringParsed.Findings))
			}
			emit(ProgressEvent{Type: "progress", Agent: "telemetry", Section: "cornering", Message: msg})
		}
	}()

	go func() {
		defer wg.Done()
		if emit != nil {
			emit(ProgressEvent{Type: "progress", Agent: "telemetry", Section: "tyres", Message: "Experto en neumáticos analizando temperaturas y grip..."})
		}
		raw, err := p.runTyreExpert(ctx, summary, stats)
		if err != nil {
			log.Error().Err(err).Msg("Tyre expert failed")
			tyreResult = "Error en el experto de neumáticos: " + err.Error()
			return
		}
		tyreResult = raw
		tyreParsed = parseTelemetryExpertOutput(raw)
		if emit != nil {
			msg := "Experto en neumáticos completado"
			if tyreParsed != nil && len(tyreParsed.Findings) > 0 {
				msg += fmt.Sprintf(" (%d hallazgos)", len(tyreParsed.Findings))
			}
			emit(ProgressEvent{Type: "progress", Agent: "telemetry", Section: "tyres", Message: msg})
		}
	}()

	go func() {
		defer wg.Done()
		if emit != nil {
			emit(ProgressEvent{Type: "progress", Agent: "telemetry", Section: "mechanical", Message: "Experto en equilibrio mecánico analizando suspensión y cargas..."})
		}
		raw, err := p.runMechanicalBalanceExpert(ctx, summary, stats)
		if err != nil {
			log.Error().Err(err).Msg("Mechanical balance expert failed")
			mechanicalResult = "Error en el experto de equilibrio mecánico: " + err.Error()
			return
		}
		mechanicalResult = raw
		mechanicalParsed = parseTelemetryExpertOutput(raw)
		if emit != nil {
			msg := "Experto en equilibrio mecánico completado"
			if mechanicalParsed != nil && len(mechanicalParsed.Findings) > 0 {
				msg += fmt.Sprintf(" (%d hallazgos)", len(mechanicalParsed.Findings))
			}
			emit(ProgressEvent{Type: "progress", Agent: "telemetry", Section: "mechanical", Message: msg})
		}
	}()

	wg.Wait()

	// Build structured insights text for injection into setup prompt
	insightsText := buildTelemetryInsightsText(brakingParsed, corneringParsed, tyreParsed, mechanicalParsed)

	// Build analysis text for frontend display
	analysisText := buildTelemetryAnalysisDisplay(
		brakingParsed, brakingResult,
		corneringParsed, corneringResult,
		tyreParsed, tyreResult,
		mechanicalParsed, mechanicalResult,
	)

	return insightsText, analysisText
}

func (p *Pipeline) runBrakingExpert(ctx context.Context, summary string, stats *domain.SessionStats) (string, error) {
	prompt := strings.ReplaceAll(BRAKING_EXPERT_PROMPT, "{telemetry_summary}", summary)
	statsJSON, _ := json.MarshalIndent(stats, "", "  ")
	prompt = strings.ReplaceAll(prompt, "{session_stats}", string(statsJSON))
	return p.Client.Generate(ctx, prompt, "")
}

func (p *Pipeline) runCorneringExpert(ctx context.Context, summary string, stats *domain.SessionStats) (string, error) {
	prompt := strings.ReplaceAll(CORNERING_EXPERT_PROMPT, "{telemetry_summary}", summary)
	statsJSON, _ := json.MarshalIndent(stats, "", "  ")
	prompt = strings.ReplaceAll(prompt, "{session_stats}", string(statsJSON))
	return p.Client.Generate(ctx, prompt, "")
}

func (p *Pipeline) runTyreExpert(ctx context.Context, summary string, stats *domain.SessionStats) (string, error) {
	prompt := strings.ReplaceAll(TYRE_EXPERT_PROMPT, "{telemetry_summary}", summary)
	statsJSON, _ := json.MarshalIndent(stats, "", "  ")
	prompt = strings.ReplaceAll(prompt, "{session_stats}", string(statsJSON))
	return p.Client.Generate(ctx, prompt, "")
}

func (p *Pipeline) runMechanicalBalanceExpert(ctx context.Context, summary string, stats *domain.SessionStats) (string, error) {
	prompt := strings.ReplaceAll(MECHANICAL_BALANCE_PROMPT, "{telemetry_summary}", summary)
	statsJSON, _ := json.MarshalIndent(stats, "", "  ")
	prompt = strings.ReplaceAll(prompt, "{session_stats}", string(statsJSON))
	return p.Client.Generate(ctx, prompt, "")
}

// ─── Domain Engineer Pipeline ────────────────────────────────────────────────

// domainEngineerPrompts maps role → prompt template constant.
var domainEngineerPrompts = map[string]string{
	"suspension": SUSPENSION_ENGINEER_PROMPT,
	"chassis":    CHASSIS_ENGINEER_PROMPT,
	"aero":       AERO_ENGINEER_PROMPT,
	"powertrain": POWERTRAIN_ENGINEER_PROMPT,
}

// loadKnowledge reads and concatenates knowledge markdown files from the data directory.
func (p *Pipeline) loadKnowledge(files ...string) string {
	if p.DataDir == "" {
		return "Conocimiento de dominio no disponible."
	}
	var sb strings.Builder
	for _, f := range files {
		path := filepath.Join(p.DataDir, "knowledge", f)
		data, err := os.ReadFile(path)
		if err != nil {
			log.Warn().Err(err).Str("file", f).Msg("failed to load knowledge file")
			continue
		}
		sb.WriteString("--- " + f + " ---\n")
		sb.Write(data)
		sb.WriteString("\n\n")
	}
	if sb.Len() == 0 {
		return "Conocimiento de dominio no disponible."
	}
	return sb.String()
}

// buildSectionsParams builds a human-readable listing of params for the given sections only.
func buildSectionsParams(setup *domain.Setup, sections []string) string {
	if setup == nil {
		return "No hay datos de setup disponibles."
	}

	var sb strings.Builder
	for _, secName := range sections {
		sec, ok := setup.Sections[secName]
		if !ok || sec == nil || len(sec.Params) == 0 {
			continue
		}

		params := make([]string, 0, len(sec.Params))
		for k := range sec.Params {
			if !isGearParam(k) {
				params = append(params, k)
			}
		}
		if len(params) == 0 {
			continue
		}
		sort.Strings(params)

		sb.WriteString(fmt.Sprintf("[%s]\n", secName))
		for _, paramName := range params {
			sb.WriteString(fmt.Sprintf("  %s (actual: %s)\n", paramName, displaySetupValue(sec.Params[paramName])))
		}
		sb.WriteString("\n")
	}

	if sb.Len() == 0 {
		return "Las secciones asignadas no tienen parámetros ajustables."
	}
	return sb.String()
}

// runDomainEngineers runs 4 domain engineers in parallel and returns their outputs.
func (p *Pipeline) runDomainEngineers(ctx context.Context, summary string, stats *domain.SessionStats, setup *domain.Setup, fixedParams string, emit ProgressFn) []domainEngineerOutput {
	roles := []string{"suspension", "chassis", "aero", "powertrain"}

	var wg sync.WaitGroup
	results := make([]domainEngineerOutput, len(roles))

	for i, role := range roles {
		wg.Add(1)
		go func(idx int, r string) {
			defer wg.Done()

			label := DomainEngineerLabels[r]
			if emit != nil {
				emit(ProgressEvent{Type: "progress", Agent: "domain_engineer", Section: r, Message: label + " analizando..."})
			}

			result, err := p.runSingleDomainEngineer(ctx, r, summary, stats, setup, fixedParams)
			if err != nil {
				log.Error().Err(err).Str("role", r).Msg("Domain engineer failed")
				results[idx] = domainEngineerOutput{
					Role:            r,
					Label:           label,
					FindingsSummary: "Error en el análisis: " + err.Error(),
					Confidence:      0,
				}
				if emit != nil {
					emit(ProgressEvent{Type: "progress", Agent: "domain_engineer", Section: r, Message: label + ": ERROR — " + err.Error()})
				}
				return
			}

			results[idx] = *result
			if emit != nil {
				totalItems := 0
				for _, sec := range result.Sections {
					totalItems += len(sec.Items)
				}
				msg := fmt.Sprintf("%s completado (%d cambios propuestos, confianza %.0f%%)", label, totalItems, result.Confidence*100)
				emit(ProgressEvent{Type: "progress", Agent: "domain_engineer", Section: r, Message: msg})
			}
		}(i, role)
	}

	wg.Wait()
	return results
}

// runSingleDomainEngineer runs one domain engineer for a specific role.
func (p *Pipeline) runSingleDomainEngineer(ctx context.Context, role string, summary string, stats *domain.SessionStats, setup *domain.Setup, fixedParams string) (*domainEngineerOutput, error) {
	promptTemplate, ok := domainEngineerPrompts[role]
	if !ok {
		return nil, fmt.Errorf("unknown domain engineer role: %s", role)
	}

	sections := DomainEngineerSections[role]
	knowledgeFiles := DomainEngineerKnowledge[role]
	knowledge := p.loadKnowledge(knowledgeFiles...)

	sectionsParams := buildSectionsParams(setup, sections)
	statsJSON, _ := json.MarshalIndent(stats, "", "  ")

	prompt := strings.ReplaceAll(promptTemplate, "{telemetry_summary}", summary)
	prompt = strings.ReplaceAll(prompt, "{session_stats}", string(statsJSON))
	prompt = strings.ReplaceAll(prompt, "{assigned_sections_params}", sectionsParams)
	prompt = strings.ReplaceAll(prompt, "{fixed_params}", fixedParams)
	prompt = strings.ReplaceAll(prompt, "{knowledge_context}", knowledge)

	model, temp := p.modelForRole(role)
	response, err := p.Client.GenerateWithModel(ctx, prompt, "", model, temp)
	if err != nil {
		return nil, err
	}

	result, err := parseDomainEngineerResponse(role, response, setup, sections)
	if err != nil {
		return nil, fmt.Errorf("parsing domain engineer %s response: %w", role, err)
	}

	return result, nil
}

// parseDomainEngineerResponse parses the JSON output from a domain engineer.
func parseDomainEngineerResponse(role string, response string, setup *domain.Setup, assignedSections []string) (*domainEngineerOutput, error) {
	label := DomainEngineerLabels[role]

	jsonStr := ExtractJSON(response)
	if jsonStr == "" {
		return &domainEngineerOutput{
			Role:            role,
			Label:           label,
			FindingsSummary: response,
			Confidence:      0.3,
		}, nil
	}

	var raw struct {
		Sections []struct {
			Section string            `json:"section"`
			Items   []json.RawMessage `json:"items"`
		} `json:"sections"`
		FindingsSummary string  `json:"findings_summary"`
		Confidence      float64 `json:"confidence"`
		// Alternate keys
		Resumen   string  `json:"resumen"`
		Confianza float64 `json:"confianza"`
	}
	if err := json.Unmarshal([]byte(jsonStr), &raw); err != nil {
		return &domainEngineerOutput{
			Role:            role,
			Label:           label,
			FindingsSummary: response,
			Confidence:      0.3,
		}, nil
	}

	// Allow valid sections only
	validSections := make(map[string]bool)
	for _, s := range assignedSections {
		validSections[s] = true
	}

	var sections []domain.SectionReport
	for _, sec := range raw.Sections {
		if !validSections[sec.Section] {
			log.Warn().Str("role", role).Str("section", sec.Section).Msg("domain engineer proposed changes for unassigned section — dropped")
			continue
		}

		var changes []domain.SetupChange
		for _, rawItem := range sec.Items {
			change := normalizeSetupChange(rawItem)
			if change.Parameter != "" {
				// Normalize values using original setup
				if origSec, ok := setup.Sections[sec.Section]; ok {
					change.NewValue = ensureUnitValue(change.NewValue, origSec.Params[change.Parameter])
				}
				changes = append(changes, change)
			}
		}
		sections = append(sections, domain.SectionReport{
			Section: sec.Section,
			Items:   changes,
		})
	}

	findingsSummary := raw.FindingsSummary
	if findingsSummary == "" {
		findingsSummary = raw.Resumen
	}
	confidence := raw.Confidence
	if confidence == 0 {
		confidence = raw.Confianza
	}
	if confidence == 0 {
		confidence = 0.7 // default when not provided
	}

	return &domainEngineerOutput{
		Role:            role,
		Label:           label,
		Sections:        sections,
		FindingsSummary: findingsSummary,
		Confidence:      confidence,
	}, nil
}

// runChiefEngineerV2 runs the chief engineer with domain engineer reports and contradiction list.
func (p *Pipeline) runChiefEngineerV2(ctx context.Context, summary string, setup *domain.Setup, domainReports []domainEngineerOutput, contradictions []Contradiction, fixedParams string) (*chiefOutput, error) {
	domainReportsText := formatDomainReportsForChief(domainReports)
	contradictionsText := formatContradictionsForChief(contradictions)
	setupJSON, _ := json.MarshalIndent(formatSetupSectionsForLLM(setup.Sections), "", "  ")

	prompt := strings.ReplaceAll(CHIEF_ENGINEER_V2_PROMPT, "{telemetry_summary}", summary)
	prompt = strings.ReplaceAll(prompt, "{full_setup}", string(setupJSON))
	prompt = strings.ReplaceAll(prompt, "{domain_reports}", domainReportsText)
	prompt = strings.ReplaceAll(prompt, "{contradictions}", contradictionsText)
	prompt = strings.ReplaceAll(prompt, "{fixed_params}", fixedParams)

	model, temp := p.modelForRole("chief")
	response, err := p.Client.GenerateWithModel(ctx, prompt, "", model, temp)
	if err != nil {
		return nil, err
	}

	// Reuse parseGlobalSetupResponse which handles both "sections" and "full_setup.sections"
	chief, err := parseGlobalSetupResponse(response)
	if err != nil {
		return nil, fmt.Errorf("parsing chief V2 response: %w", err)
	}
	chief = normalizeChiefValues(chief, setup)

	return chief, nil
}

// buildDomainEngineerInsightsText builds a structured text summary of all domain engineer
// findings for display. Analogous to buildTelemetryInsightsText but from domain engineers.
func buildDomainEngineerInsightsText(reports []domainEngineerOutput) string {
	var sb strings.Builder
	for _, rep := range reports {
		if rep.FindingsSummary == "" && len(rep.Sections) == 0 {
			continue
		}
		sb.WriteString("=== " + rep.Label + " ===\n")
		if rep.FindingsSummary != "" {
			sb.WriteString(rep.FindingsSummary + "\n\n")
		}
		for _, sec := range rep.Sections {
			for _, item := range sec.Items {
				sb.WriteString(fmt.Sprintf("- [%s] %s → %s: %s\n", sec.Section, item.Parameter, item.NewValue, item.Reason))
			}
		}
		sb.WriteString("\n")
	}
	if sb.Len() == 0 {
		return "No se obtuvieron hallazgos de los ingenieros de dominio."
	}
	return sb.String()
}

// buildDomainEngineerAnalysisDisplay builds user-facing markdown analysis from domain engineers.
func buildDomainEngineerAnalysisDisplay(reports []domainEngineerOutput) string {
	var sb strings.Builder
	for _, rep := range reports {
		sb.WriteString("## Análisis del " + rep.Label + "\n\n")
		if rep.FindingsSummary != "" {
			sb.WriteString(rep.FindingsSummary + "\n\n")
		}
		for _, sec := range rep.Sections {
			if len(sec.Items) == 0 {
				continue
			}
			sb.WriteString(fmt.Sprintf("### %s\n", sec.Section))
			for i, item := range sec.Items {
				sb.WriteString(fmt.Sprintf("**%d.** %s → %s\n", i+1, item.Parameter, item.NewValue))
				if item.Reason != "" {
					sb.WriteString(fmt.Sprintf("   *%s*\n\n", item.Reason))
				}
			}
		}
		sb.WriteString("\n")
	}
	if sb.Len() == 0 {
		return "No se obtuvieron análisis de los ingenieros de dominio.\n"
	}
	return sb.String()
}

func parseTelemetryExpertOutput(raw string) *telemetryExpertOutput {
	jsonStr := ExtractJSON(raw)
	if jsonStr == "" {
		return nil
	}
	var out telemetryExpertOutput
	if err := json.Unmarshal([]byte(jsonStr), &out); err != nil {
		return nil
	}
	return &out
}

func buildTelemetryInsightsText(braking, cornering, tyre, mechanical *telemetryExpertOutput) string {
	var sb strings.Builder

	type expertEntry struct {
		label  string
		output *telemetryExpertOutput
	}
	experts := []expertEntry{
		{"EXPERTO EN FRENADO", braking},
		{"EXPERTO EN EQUILIBRIO Y CURVAS", cornering},
		{"EXPERTO EN NEUMÁTICOS", tyre},
		{"EXPERTO EN EQUILIBRIO MECÁNICO", mechanical},
	}

	for _, e := range experts {
		if e.output == nil || (len(e.output.Findings) == 0 && e.output.Summary == "") {
			continue
		}
		sb.WriteString("=== " + e.label + " ===\n")
		if e.output.Summary != "" {
			sb.WriteString(e.output.Summary + "\n\n")
		}
		for i, f := range e.output.Findings {
			sb.WriteString(fmt.Sprintf("%d. %s\n", i+1, f.Finding))
			if f.Recommendation != "" {
				sb.WriteString(fmt.Sprintf("   → Recomendación: %s\n", f.Recommendation))
			}
			if len(f.AffectedSections) > 0 {
				sb.WriteString(fmt.Sprintf("   → Secciones afectadas: %s\n", strings.Join(f.AffectedSections, ", ")))
			}
		}
		sb.WriteString("\n")
	}

	if sb.Len() == 0 {
		return "No se obtuvieron hallazgos de los expertos de telemetría."
	}
	return sb.String()
}

func buildTelemetryAnalysisDisplay(
	braking *telemetryExpertOutput, brakingRaw string,
	cornering *telemetryExpertOutput, corneringRaw string,
	tyre *telemetryExpertOutput, tyreRaw string,
	mechanical *telemetryExpertOutput, mechanicalRaw string,
) string {
	var sb strings.Builder

	type expertEntry struct {
		label  string
		parsed *telemetryExpertOutput
		raw    string
	}
	experts := []expertEntry{
		{"Experto en Frenado", braking, brakingRaw},
		{"Experto en Equilibrio y Curvas", cornering, corneringRaw},
		{"Experto en Neumáticos", tyre, tyreRaw},
		{"Experto en Equilibrio Mecánico", mechanical, mechanicalRaw},
	}

	for _, e := range experts {
		sb.WriteString("## Análisis del " + e.label + "\n\n")
		if e.parsed != nil && e.parsed.Summary != "" {
			sb.WriteString(e.parsed.Summary + "\n\n")
			for i, f := range e.parsed.Findings {
				sb.WriteString(fmt.Sprintf("**%d.** %s\n", i+1, f.Finding))
				if f.Recommendation != "" {
					sb.WriteString(fmt.Sprintf("   *Recomendación:* %s\n\n", f.Recommendation))
				}
			}
		} else if e.raw != "" {
			sb.WriteString(e.raw + "\n\n")
		} else {
			sb.WriteString("No disponible.\n\n")
		}
	}

	return sb.String()
}

// --- Global setup agent (replaces per-section specialists + chief engineer) ---

// chiefOutput holds the consolidated setup recommendations.
type chiefOutput struct {
	Sections  []domain.SectionReport
	Reasoning string
}

// globalSetupOutput is the parsed JSON output from the global setup agent.
type globalSetupOutput struct {
	Sections  []domain.SectionReport `json:"sections"`
	Reasoning string                 `json:"reasoning"`
}

func (p *Pipeline) runGlobalSetupAgent(ctx context.Context, summary string, setup *domain.Setup, fixedParams string, telemetryInsights string) (*chiefOutput, error) {
	setupBySection := buildSetupParamsBySection(setup)

	prompt := strings.ReplaceAll(GLOBAL_SETUP_AGENT_PROMPT, "{telemetry_summary}", summary)
	prompt = strings.ReplaceAll(prompt, "{setup_params_by_section}", setupBySection)
	prompt = strings.ReplaceAll(prompt, "{fixed_params}", fixedParams)
	prompt = strings.ReplaceAll(prompt, "{telemetry_insights}", telemetryInsights)

	response, err := p.Client.Generate(ctx, prompt, "")
	if err != nil {
		return nil, err
	}

	return parseGlobalSetupResponse(response)
}

// buildSetupParamsBySection builds a human-readable listing of section → params with current values.
func buildSetupParamsBySection(setup *domain.Setup) string {
	if setup == nil {
		return "No hay datos de setup disponibles."
	}

	// Sort sections for deterministic output
	sections := make([]string, 0, len(setup.Sections))
	for name := range setup.Sections {
		if SkippedSections[name] {
			continue
		}
		sections = append(sections, name)
	}
	sort.Strings(sections)

	var sb strings.Builder
	for _, secName := range sections {
		sec := setup.Sections[secName]
		if sec == nil || len(sec.Params) == 0 {
			continue
		}

		// Collect non-gear params sorted
		params := make([]string, 0, len(sec.Params))
		for k := range sec.Params {
			if !isGearParam(k) {
				params = append(params, k)
			}
		}
		if len(params) == 0 {
			continue
		}
		sort.Strings(params)

		sb.WriteString(fmt.Sprintf("[%s]\n", secName))
		for _, paramName := range params {
			sb.WriteString(fmt.Sprintf("  %s (actual: %s)\n", paramName, sec.Params[paramName]))
		}
		sb.WriteString("\n")
	}
	return sb.String()
}

func parseGlobalSetupResponse(response string) (*chiefOutput, error) {
	jsonStr := ExtractJSON(response)
	if jsonStr == "" {
		return &chiefOutput{Reasoning: response}, nil
	}

	var raw struct {
		Sections []struct {
			Section string            `json:"section"`
			Items   []json.RawMessage `json:"items"`
		} `json:"sections"`
		// Also accept the existing chief format for backward compat
		FullSetup struct {
			Sections []struct {
				Section string            `json:"section"`
				Items   []json.RawMessage `json:"items"`
			} `json:"sections"`
		} `json:"full_setup"`
		Reasoning      string `json:"reasoning"`
		ChiefReasoning string `json:"chief_reasoning"`
	}
	if err := json.Unmarshal([]byte(jsonStr), &raw); err != nil {
		return &chiefOutput{Reasoning: response}, nil
	}

	// Accept either top-level "sections" or nested "full_setup.sections"
	rawSections := raw.Sections
	if len(rawSections) == 0 {
		rawSections = raw.FullSetup.Sections
	}
	reasoning := raw.Reasoning
	if reasoning == "" {
		reasoning = raw.ChiefReasoning
	}

	var sections []domain.SectionReport
	for _, sec := range rawSections {
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
		Reasoning: reasoning,
	}, nil
}

// filterInvalidSetupParams removes proposed changes where the parameter does not exist in the setup section.
func filterInvalidSetupParams(chief *chiefOutput, setup *domain.Setup) *chiefOutput {
	if chief == nil || setup == nil {
		return chief
	}

	filteredSections := make([]domain.SectionReport, 0, len(chief.Sections))
	for _, section := range chief.Sections {
		sec, ok := setup.Sections[section.Section]
		if !ok {
			// Unknown section — drop entire section
			log.Warn().Str("section", section.Section).Msg("Global setup agent proposed unknown section; dropping")
			continue
		}

		validItems := make([]domain.SetupChange, 0, len(section.Items))
		for _, item := range section.Items {
			if _, exists := sec.Params[item.Parameter]; exists {
				validItems = append(validItems, item)
			} else {
				log.Warn().Str("section", section.Section).Str("param", item.Parameter).Msg("Global setup agent proposed non-existent param; dropping")
			}
		}
		section.Items = validItems
		filteredSections = append(filteredSections, section)
	}

	chief.Sections = filteredSections
	return chief
}

// countSectionsWithChanges returns the number of sections in a chiefOutput that have at least one change.
func countSectionsWithChanges(chief *chiefOutput) int {
	if chief == nil {
		return 0
	}
	count := 0
	for _, sec := range chief.Sections {
		if len(sec.Items) > 0 {
			count++
		}
	}
	return count
}

// mergeReadOnlyParams extends user-supplied fixedParams with read-only params from all setup sections.
func mergeReadOnlyParams(setup *domain.Setup, fixedParams []string) []string {
	if setup == nil {
		return fixedParams
	}

	seen := make(map[string]struct{}, len(fixedParams))
	result := make([]string, 0, len(fixedParams))
	for _, p := range fixedParams {
		key := normalizeParamKey(p)
		if _, dup := seen[key]; !dup {
			seen[key] = struct{}{}
			result = append(result, p)
		}
	}

	for _, sec := range setup.Sections {
		if sec == nil {
			continue
		}
		for _, paramName := range sec.ReadOnlyParams {
			key := normalizeParamKey(paramName)
			if _, already := seen[key]; !already {
				seen[key] = struct{}{}
				result = append(result, paramName)
			}
		}
	}
	return result
}

func (p *Pipeline) runSpecialists(ctx context.Context, summary string, setup *domain.Setup, fixedParams string, telemetryInsights string) []domain.SectionReport {
	return p.runSpecialistsWithProgress(ctx, summary, setup, fixedParams, telemetryInsights, nil)
}

func (p *Pipeline) runSpecialistsWithProgress(ctx context.Context, summary string, setup *domain.Setup, fixedParams string, telemetryInsights string, emit ProgressFn) []domain.SectionReport {
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

			report, err := p.runSingleSpecialist(ctx, summary, secName, sec, fixedParams, telemetryInsights)
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

func (p *Pipeline) runSingleSpecialist(ctx context.Context, summary, sectionName string, section *domain.SetupSection, fixedParams string, telemetryInsights string) (*domain.SectionReport, error) {
	paramsJSON, _ := json.MarshalIndent(formatSetupParamsForLLM(section.Params), "", "  ")

	prompt := strings.ReplaceAll(SECTION_AGENT_PROMPT, "{section_name}", sectionName)
	prompt = strings.ReplaceAll(prompt, "{telemetry_summary}", summary)
	prompt = strings.ReplaceAll(prompt, "{section_params}", string(paramsJSON))
	prompt = strings.ReplaceAll(prompt, "{fixed_params}", fixedParams)
	prompt = strings.ReplaceAll(prompt, "{telemetry_insights}", telemetryInsights)

	response, err := p.Client.Generate(ctx, prompt, "")
	if err != nil {
		return nil, err
	}

	report, err := parseSpecialistResponse(sectionName, response)
	if err != nil {
		return nil, fmt.Errorf("parsing specialist response for %s: %w", sectionName, err)
	}
	if sec := section; sec != nil {
		report = normalizeSectionReportValues(report, sec.Params)
	}

	return report, nil
}

// runChiefEngineer consolidates specialist reports into a final setup proposal.
func (p *Pipeline) runChiefEngineer(ctx context.Context, summary string, setup *domain.Setup, specialistReports []domain.SectionReport, fixedParams string, telemetryInsights string) (*chiefOutput, error) {
	reportsJSON, _ := json.MarshalIndent(specialistReports, "", "  ")
	setupJSON, _ := json.MarshalIndent(formatSetupSectionsForLLM(setup.Sections), "", "  ")

	prompt := strings.ReplaceAll(CHIEF_ENGINEER_PROMPT, "{telemetry_summary}", summary)
	prompt = strings.ReplaceAll(prompt, "{full_setup}", string(setupJSON))
	prompt = strings.ReplaceAll(prompt, "{specialist_reports}", string(reportsJSON))
	prompt = strings.ReplaceAll(prompt, "{fixed_params}", fixedParams)
	prompt = strings.ReplaceAll(prompt, "{telemetry_insights}", telemetryInsights)

	response, err := p.Client.Generate(ctx, prompt, "")
	if err != nil {
		return nil, err
	}

	chief, err := parseChiefResponse(response)
	if err != nil {
		return nil, fmt.Errorf("parsing chief response: %w", err)
	}
	chief = normalizeChiefValues(chief, setup)

	return chief, nil
}

// filterInvalidSectionReports drops any SectionReport for a section that doesn't exist in setup,
// and drops individual items whose parameter doesn't exist in that section.
func filterInvalidSectionReports(reports []domain.SectionReport, setup *domain.Setup) []domain.SectionReport {
	filtered := make([]domain.SectionReport, 0, len(reports))
	for _, rep := range reports {
		sec, ok := setup.Sections[rep.Section]
		if !ok {
			log.Warn().Str("section", rep.Section).Msg("Specialist proposed changes for unknown section — dropped")
			continue
		}
		validItems := make([]domain.SetupChange, 0, len(rep.Items))
		for _, item := range rep.Items {
			if _, ok := sec.Params[item.Parameter]; ok {
				validItems = append(validItems, item)
			} else {
				log.Warn().Str("section", rep.Section).Str("param", item.Parameter).Msg("Specialist proposed unknown param — dropped")
			}
		}
		rep.Items = validItems
		filtered = append(filtered, rep)
	}
	return filtered
}

// mergeSpecialistFloor supplements the chief's output with specialist proposals the chief did
// not explicitly include. This implements the documented merge strategy: "build from specialist
// proposals first; chief overrides only for params it explicitly returns." Specialist reports
// passed in must already be physics-validated and locked-param-filtered. The chief's proposals
// take precedence for any (section, parameter) pair it explicitly returns; everything else is
// taken from the specialists, preventing chief LLM output truncation from silently dropping
// valid findings.
func mergeSpecialistFloor(chief *chiefOutput, specialistReports []domain.SectionReport) *chiefOutput {
	if chief == nil || len(specialistReports) == 0 {
		return chief
	}

	// Index what the chief already covers: section → set of parameter names.
	chiefCovered := make(map[string]map[string]bool)
	for _, sec := range chief.Sections {
		if _, ok := chiefCovered[sec.Section]; !ok {
			chiefCovered[sec.Section] = make(map[string]bool)
		}
		for _, item := range sec.Items {
			chiefCovered[sec.Section][item.Parameter] = true
		}
	}

	// Build a stable index: section name → position in chief.Sections slice.
	chiefSectionIdx := make(map[string]int, len(chief.Sections))
	for i, sec := range chief.Sections {
		chiefSectionIdx[sec.Section] = i
	}

	added := 0
	for _, rep := range specialistReports {
		if len(rep.Items) == 0 {
			continue
		}
		covered, secPresent := chiefCovered[rep.Section]
		if !secPresent {
			// Chief has no entry for this section — add the entire specialist section.
			chief.Sections = append(chief.Sections, rep)
			added += len(rep.Items)
			continue
		}
		// Chief mentions this section — add only the params it omitted.
		idx := chiefSectionIdx[rep.Section]
		for _, item := range rep.Items {
			if !covered[item.Parameter] {
				chief.Sections[idx].Items = append(chief.Sections[idx].Items, item)
				covered[item.Parameter] = true
				added++
			}
		}
	}

	if added > 0 {
		log.Info().Int("added", added).Msg("mergeSpecialistFloor: supplemented chief with specialist proposals")
	}
	return chief
}

func (p *Pipeline) formatResponse(drivingAnalysis string, telemetryAnalysis string, specialistReports []domain.SectionReport, chief *chiefOutput, setup *domain.Setup, stats *domain.SessionStats, summary string) *domain.AnalysisResponse {
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
						change.NewValue = ensureUnitValue(item.NewValue, origVal)
						change.OldValue = displaySetupValue(origVal)
						change.ChangePct = computeChangePct(change.OldValue, change.NewValue)
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
						change.NewValue = ensureUnitValue(item.NewValue, origVal)
						change.OldValue = displaySetupValue(origVal)
						change.ChangePct = computeChangePct(change.OldValue, change.NewValue)
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
	if len(fullSetup) > 0 {
		if strings.TrimSpace(chiefReasoning) == "" || strings.HasPrefix(chiefReasoning, "No se aplican cambios de setup") {
			chiefReasoning = buildChiefReasoningFromSetupMap(fullSetup)
		}
	}

	return &domain.AnalysisResponse{
		DrivingAnalysis:   drivingAnalysis,
		TelemetryAnalysis: telemetryAnalysis,
		SetupAnalysis:     setupAnalysis,
		FullSetup:         fullSetup,
		SessionStats:      stats,
		AgentReports:      specialistReports,
		TelemetrySummary:  summary,
		ChiefReasoning:    chiefReasoning,
	}
}

func buildChiefReasoningFromSetupMap(fullSetup map[string][]domain.SetupChange) string {
	sections := make([]string, 0, len(fullSetup))
	for section := range fullSetup {
		sections = append(sections, section)
	}
	sort.Strings(sections)

	lines := make([]string, 0)
	for _, section := range sections {
		items := fullSetup[section]
		for _, item := range items {
			reason := strings.TrimSpace(item.Reason)
			if reason == "" {
				reason = fmt.Sprintf("Ajustar de %s a %s: ajuste respaldado por telemetría y lógica de ingeniería de pista.", item.OldValue, item.NewValue)
			}
			lines = append(lines, fmt.Sprintf("- %s / %s: %s", section, item.Parameter, reason))
		}
	}

	if len(lines) == 0 {
		return "No se aplican cambios de setup tras consolidar guardarraíles y coherencia física."
	}

	return "Estrategia final validada por telemetría y guardarraíles:\n" + strings.Join(lines, "\n")
}

func formatSetupParamsForLLM(params map[string]string) map[string]string {
	formatted := make(map[string]string, len(params))
	for k, v := range params {
		formatted[k] = displaySetupValue(v)
	}
	return formatted
}

func formatSetupSectionsForLLM(sections map[string]*domain.SetupSection) map[string]*domain.SetupSection {
	formatted := make(map[string]*domain.SetupSection, len(sections))
	for secName, sec := range sections {
		if sec == nil {
			continue
		}
		cloned := &domain.SetupSection{
			Name:           sec.Name,
			Params:         formatSetupParamsForLLM(sec.Params),
			ReadOnlyParams: append([]string(nil), sec.ReadOnlyParams...),
		}
		formatted[secName] = cloned
	}
	return formatted
}

func normalizeSectionReportValues(report *domain.SectionReport, sectionParams map[string]string) *domain.SectionReport {
	if report == nil {
		return nil
	}
	for i := range report.Items {
		param := report.Items[i].Parameter
		orig, ok := sectionParams[param]
		if !ok {
			orig = ""
		}
		report.Items[i].NewValue = ensureUnitValue(report.Items[i].NewValue, orig)
	}
	return report
}

func normalizeChiefValues(chief *chiefOutput, setup *domain.Setup) *chiefOutput {
	if chief == nil || setup == nil {
		return chief
	}
	for secIdx := range chief.Sections {
		sec := &chief.Sections[secIdx]
		origSec, ok := setup.Sections[sec.Section]
		if !ok || origSec == nil {
			for i := range sec.Items {
				sec.Items[i].NewValue = ensureUnitValue(sec.Items[i].NewValue, "")
			}
			continue
		}
		for i := range sec.Items {
			param := sec.Items[i].Parameter
			orig := origSec.Params[param]
			sec.Items[i].NewValue = ensureUnitValue(sec.Items[i].NewValue, orig)
		}
	}
	return chief
}

func displaySetupValue(raw string) string {
	clean := strings.TrimSpace(parsers.CleanValue(raw))
	if clean == "" {
		return ""
	}
	if hasUnitText(clean) {
		return clean
	}
	return clean + " deg"
}

func ensureUnitValue(value, originalRaw string) string {
	val := strings.TrimSpace(value)
	if val == "" {
		return val
	}
	val = strings.TrimSpace(parsers.CleanValue(val))
	if hasUnitText(val) {
		return val
	}
	return val + " " + inferUnitFromOriginal(originalRaw)
}

func inferUnitFromOriginal(originalRaw string) string {
	display := displaySetupValue(originalRaw)
	if idx := firstUnitIndex(display); idx >= 0 {
		unit := strings.TrimSpace(display[idx:])
		if unit != "" {
			return unit
		}
	}
	return "deg"
}

func hasUnitText(s string) bool {
	return firstUnitIndex(strings.TrimSpace(s)) >= 0
}

func firstUnitIndex(s string) int {
	for i, r := range s {
		if (r >= 'A' && r <= 'Z') || (r >= 'a' && r <= 'z') || r == '°' || r == '%' {
			return i
		}
	}
	return -1
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
	oldTrim := strings.TrimSpace(oldRaw)
	newTrim := strings.TrimSpace(newRaw)

	// Business rule: missing or unchanged target value must always be zero.
	if newTrim == "" {
		return "0.0%"
	}
	if oldTrim == newTrim {
		return "0.0%"
	}

	oldVal, okOld := ExtractNumeric(oldRaw)
	newVal, okNew := ExtractNumeric(newRaw)
	if !okOld || !okNew || oldVal == 0 {
		return ""
	}
	if math.Abs(newVal-oldVal) < 1e-9 {
		return "0.0%"
	}
	pct := ((newVal - oldVal) / math.Abs(oldVal)) * 100
	return fmt.Sprintf("%+.1f%%", pct)
}

func normalizeParamKey(name string) string {
	return strings.ToLower(strings.TrimSpace(name))
}

func buildFixedParamSet(fixedParams []string) map[string]struct{} {
	set := make(map[string]struct{}, len(fixedParams))
	for _, param := range fixedParams {
		key := normalizeParamKey(param)
		if key == "" {
			continue
		}
		set[key] = struct{}{}
	}
	return set
}

func excludeFixedParamsFromSetup(setup *domain.Setup, fixedParams []string) *domain.Setup {
	if setup == nil {
		return nil
	}
	blocked := buildFixedParamSet(fixedParams)
	if len(blocked) == 0 {
		return setup
	}

	clone := domain.NewSetup()
	for sectionName, section := range setup.Sections {
		if section == nil {
			continue
		}
		params := make(map[string]string)
		for paramName, paramValue := range section.Params {
			if _, blockedParam := blocked[normalizeParamKey(paramName)]; blockedParam {
				continue
			}
			params[paramName] = paramValue
		}
		if len(params) == 0 {
			continue
		}
		clone.Sections[sectionName] = &domain.SetupSection{
			Name:   section.Name,
			Params: params,
		}
	}
	return clone
}

func filterLockedChanges(reports []domain.SectionReport, fixedParams []string) []domain.SectionReport {
	blocked := buildFixedParamSet(fixedParams)
	if len(blocked) == 0 {
		return reports
	}

	filtered := make([]domain.SectionReport, 0, len(reports))
	for _, report := range reports {
		items := make([]domain.SetupChange, 0, len(report.Items))
		for _, item := range report.Items {
			if _, blockedParam := blocked[normalizeParamKey(item.Parameter)]; blockedParam {
				continue
			}
			items = append(items, item)
		}
		report.Items = items
		filtered = append(filtered, report)
	}
	return filtered
}

func filterLockedChiefOutput(chief *chiefOutput, fixedParams []string) *chiefOutput {
	if chief == nil {
		return nil
	}
	blocked := buildFixedParamSet(fixedParams)
	if len(blocked) == 0 {
		return chief
	}

	filteredSections := make([]domain.SectionReport, 0, len(chief.Sections))
	for _, section := range chief.Sections {
		items := make([]domain.SetupChange, 0, len(section.Items))
		for _, item := range section.Items {
			if _, blockedParam := blocked[normalizeParamKey(item.Parameter)]; blockedParam {
				continue
			}
			items = append(items, item)
		}
		section.Items = items
		filteredSections = append(filteredSections, section)
	}
	chief.Sections = filteredSections
	return chief
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

func normalizeSectionReasonsWithFinalValues(reports []domain.SectionReport, setup *domain.Setup) {
	if setup == nil {
		return
	}
	for secIdx := range reports {
		sec := &reports[secIdx]
		origSec := setup.Sections[sec.Section]
		if origSec == nil {
			continue
		}
		for itemIdx := range sec.Items {
			item := &sec.Items[itemIdx]
			item.NewValue = ensureUnitValue(item.NewValue, origSec.Params[item.Parameter])
			item.Reason = buildCoherentReason(item.Reason, origSec.Params[item.Parameter], item.NewValue)
		}
	}
}

func normalizeChiefReasonsWithFinalValues(chief *chiefOutput, setup *domain.Setup) {
	if chief == nil || setup == nil {
		return
	}

	for secIdx := range chief.Sections {
		sec := &chief.Sections[secIdx]
		origSec := setup.Sections[sec.Section]
		if origSec == nil {
			continue
		}
		for itemIdx := range sec.Items {
			item := &sec.Items[itemIdx]
			item.NewValue = ensureUnitValue(item.NewValue, origSec.Params[item.Parameter])
			item.Reason = buildCoherentReason(item.Reason, origSec.Params[item.Parameter], item.NewValue)
		}
	}

	chief.Reasoning = buildChiefReasoningFromFinalSetup(chief.Sections, setup)
}

func buildChiefReasoningFromFinalSetup(sections []domain.SectionReport, setup *domain.Setup) string {
	lines := make([]string, 0)
	for _, sec := range sections {
		origSec := setup.Sections[sec.Section]
		if origSec == nil {
			continue
		}
		for _, item := range sec.Items {
			oldRaw := origSec.Params[item.Parameter]
			if strings.TrimSpace(oldRaw) == "" {
				continue
			}
			line := fmt.Sprintf("- %s / %s: %s", sec.Section, item.Parameter, buildCoherentReason("", oldRaw, item.NewValue))
			lines = append(lines, line)
		}
	}

	if len(lines) == 0 {
		return "No se aplican cambios de setup tras consolidar guardarraíles y coherencia física."
	}

	return "Estrategia final validada por telemetría y guardarraíles:\n" + strings.Join(lines, "\n")
}

func buildCoherentReason(existingReason, oldRaw, newRaw string) string {
	oldVal := displaySetupValue(oldRaw)
	newVal := ensureUnitValue(newRaw, oldRaw)
	direction := inferDirection(oldVal, newVal)

	base := fmt.Sprintf("%s de %s a %s", direction, oldVal, newVal)
	detail := sanitizeReasonDetail(existingReason)
	if detail == "" {
		return base + ": ajuste respaldado por telemetría y lógica de ingeniería de pista."
	}

	return base + ": " + detail
}

func inferDirection(oldVal, newVal string) string {
	oldNum, okOld := ExtractNumeric(oldVal)
	newNum, okNew := ExtractNumeric(newVal)
	if okOld && okNew {
		if newNum > oldNum {
			return "Aumentar"
		}
		if newNum < oldNum {
			return "Reducir"
		}
		return "Mantener"
	}
	if strings.TrimSpace(newVal) == strings.TrimSpace(oldVal) {
		return "Mantener"
	}
	return "Ajustar"
}

func sanitizeReasonDetail(reason string) string {
	clean := normalizeMojibake(strings.TrimSpace(reason))
	if clean == "" {
		return ""
	}

	patterns := []string{
		`(?i)\b(aumentar|subir|incrementar|reducir|bajar|disminuir|mantener|ajustar)\b\s+de\s+[^:;,.]+\s+a\s+[^:;,.]+`,
		`(?i)\b(objetivo|target)\s*[:=]?\s*[^:;,.]+`,
	}
	for _, pattern := range patterns {
		re := regexp.MustCompile(pattern)
		clean = strings.TrimSpace(re.ReplaceAllString(clean, ""))
	}

	tracePrefix := regexp.MustCompile(`(?i)^\s*de\s+.+?\s+a\s+.+?\s*:\s*`)
	for {
		trimmed := strings.TrimSpace(tracePrefix.ReplaceAllString(clean, ""))
		if trimmed == clean {
			break
		}
		clean = trimmed
	}

	clean = regexp.MustCompile(`\s+:\s+:`).ReplaceAllString(clean, ":")
	clean = regexp.MustCompile(`\s{2,}`).ReplaceAllString(clean, " ")
	clean = strings.TrimLeft(clean, ":;,. ")
	clean = strings.TrimSpace(clean)
	return clean
}

func normalizeMojibake(s string) string {
	replacer := strings.NewReplacer(
		"telemetrÃa", "telemetría",
		"guardarraÃles", "guardarraíles",
		"vehÃculo", "vehículo",
		"frenada intensa", "frenada intensa",
		"distribuciÃ³n", "distribución",
		"aceleraciÃ³n", "aceleración",
		"mÃnima", "mínima",
		"cÃ¡mara", "cámara",
		"desvÃo", "desvío",
		"suspensiÃ³n", "suspensión",
		"tracciÃ³n", "tracción",
		"Ã³", "ó",
		"Ã¡", "á",
		"Ã©", "é",
		"Ã­", "í",
		"Ãº", "ú",
		"Ã±", "ñ",
		"Â°", "°",
		"â", "'",
	)
	return replacer.Replace(s)
}

// RunDomainEngineer exposes a single domain-engineer run for benchmarking.
// Returns the parsed SectionReports and the raw findings summary.
func (p *Pipeline) RunDomainEngineer(ctx context.Context, role string, telemetrySummary string, stats *domain.SessionStats, setup *domain.Setup, fixedParams []string) ([]domain.SectionReport, string, error) {
	fixedStr := strings.Join(fixedParams, ", ")
	out, err := p.runSingleDomainEngineer(ctx, role, telemetrySummary, stats, setup, fixedStr)
	if err != nil {
		return nil, "", err
	}
	return out.Sections, out.FindingsSummary, nil
}

// RunDrivingAgentBench exposes the driving agent run for benchmarking.
func (p *Pipeline) RunDrivingAgentBench(ctx context.Context, telemetrySummary string, stats *domain.SessionStats) (string, error) {
	return p.runDrivingAgent(ctx, telemetrySummary, stats)
}
