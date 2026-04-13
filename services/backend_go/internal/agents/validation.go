package agents

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"

	"github.com/rs/zerolog/log"

	"github.com/viciruela/rfactor2-engineer/internal/domain"
)

// PhysicsRule represents a single physics validation rule from physics_rules.json.
type PhysicsRule struct {
	ID             string   `json:"id"`
	If             string   `json:"if"`
	Then           string   `json:"then"`
	Direction      string   `json:"direction"`
	AffectedParams []string `json:"affected_params"`
	Physics        string   `json:"physics"`
}

// PhysicsRuleset holds the full loaded physics rules, organized by domain.
type PhysicsRuleset struct {
	Version string                     `json:"version"`
	Domains map[string][]PhysicsRule   `json:"domains"`
}

// ValidationResult captures the outcome of validating a single setup change.
type ValidationResult struct {
	IsValid    bool     `json:"is_valid"`
	Violations []string `json:"violations"`
	RuleIDs    []string `json:"rule_ids"`
}

// AgentValidationSummary summarizes validation for an entire agent's output.
type AgentValidationSummary struct {
	AgentName      string `json:"agent_name"`
	TotalItems     int    `json:"total_items"`
	ValidItems     int    `json:"valid_items"`
	RejectedItems  int    `json:"rejected_items"`
	LowConfidence  bool   `json:"low_confidence"`
}

// LoadPhysicsRules loads and parses the physics rules from the given JSON file path.
func LoadPhysicsRules(path string) (*PhysicsRuleset, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("reading physics rules: %w", err)
	}
	var ruleset PhysicsRuleset
	if err := json.Unmarshal(data, &ruleset); err != nil {
		return nil, fmt.Errorf("parsing physics rules: %w", err)
	}
	return &ruleset, nil
}

// validateRecommendation checks a single setup change against the validation domain
// rules (VC-xxx anti-hallucination rules). Returns whether the change is valid
// and a list of violated rule descriptions.
func validateRecommendation(change domain.SetupChange, ruleset *PhysicsRuleset, fixedParams []string) ValidationResult {
	if ruleset == nil {
		return ValidationResult{IsValid: true}
	}

	var violations []string
	var ruleIDs []string

	validationRules, ok := ruleset.Domains["validation"]
	if !ok {
		return ValidationResult{IsValid: true}
	}

	for _, rule := range validationRules {
		violated := false
		switch rule.ID {
		case "VC-005":
			// Hallucinated data — checked separately with telemetry context
			// This requires telemetry input checking, handled at a higher level
			continue
		case "VC-006":
			// Reason says "increase" but value decreases (or vice versa)
			violated = checkDirectionCoherence(change)
		case "VC-007":
			// Driving advice instead of setup change
			violated = checkDrivingAdvice(change)
		case "VC-009":
			// Locked parameter violation
			violated = checkFixedParam(change.Parameter, fixedParams)
		case "VC-010":
			// Unit policy: clicks/steps instead of physical units
			violated = checkUnitPolicy(change.NewValue)
		case "VC-001":
			// "reduce rear wing to fix understeer"
			violated = checkPhysicsInversion(change, "RearWingSetting", "decrease", "understeer")
		case "VC-002":
			// "increase front spring to improve traction on exit"
			violated = checkCausalLink(change, "FrontSpringRate", "traction", "exit")
		case "VC-003":
			// "soften brake bias for mid-corner balance"
			violated = checkScopeError(change, "BrakeBiasSetting", "mid-corner")
		case "VC-004":
			// Softens both front AND rear ARB — checked at report level
			continue
		case "VC-008":
			// "increase front downforce to reduce oversteer"
			violated = checkPhysicsInversion(change, "FrontWingSetting", "increase", "oversteer")
		}

		if violated {
			violations = append(violations, fmt.Sprintf("[%s] %s", rule.ID, rule.Physics))
			ruleIDs = append(ruleIDs, rule.ID)
		}
	}

	return ValidationResult{
		IsValid:    len(violations) == 0,
		Violations: violations,
		RuleIDs:    ruleIDs,
	}
}

// validateAgentReport validates all setup changes from a single agent and strips
// invalid items. Returns the filtered report along with a validation summary.
// If >50% of items are rejected, the summary flags the report as low-confidence.
func validateAgentReport(report domain.SectionReport, ruleset *PhysicsRuleset, fixedParams []string) (domain.SectionReport, AgentValidationSummary) {
	summary := AgentValidationSummary{
		AgentName:  report.Section,
		TotalItems: len(report.Items),
	}

	if ruleset == nil {
		summary.ValidItems = summary.TotalItems
		return report, summary
	}

	var validItems []domain.SetupChange
	for _, item := range report.Items {
		result := validateRecommendation(item, ruleset, fixedParams)
		if result.IsValid {
			validItems = append(validItems, item)
			summary.ValidItems++
		} else {
			summary.RejectedItems++
			log.Warn().
				Str("agent", report.Section).
				Str("parameter", item.Parameter).
				Strs("violations", result.Violations).
				Msg("recommendation rejected by physics validation")
		}
	}

	// Check VC-004: both front AND rear ARB softened simultaneously
	validItems = checkSymmetricARBChange(validItems, ruleset)
	summary.ValidItems = len(validItems)
	summary.RejectedItems = summary.TotalItems - summary.ValidItems

	// Low confidence flag: >50% rejected
	if summary.TotalItems > 0 && float64(summary.RejectedItems)/float64(summary.TotalItems) > 0.5 {
		summary.LowConfidence = true
		log.Warn().
			Str("agent", report.Section).
			Int("total", summary.TotalItems).
			Int("rejected", summary.RejectedItems).
			Msg("agent report flagged as low-confidence (>50% rejected)")
	}

	filtered := report
	filtered.Items = validItems
	return filtered, summary
}

// --- Individual check functions ---

// checkDirectionCoherence verifies that the stated reason direction matches the actual value change.
func checkDirectionCoherence(change domain.SetupChange) bool {
	reasonLower := strings.ToLower(change.Reason)
	oldVal := extractNumericValue(change.OldValue)
	newVal := extractNumericValue(change.NewValue)

	if oldVal == 0 && newVal == 0 {
		return false // can't verify without numeric values
	}

	if strings.Contains(reasonLower, "aumentar") || strings.Contains(reasonLower, "incrementar") || strings.Contains(reasonLower, "increase") || strings.Contains(reasonLower, "subir") {
		if newVal < oldVal {
			return true // violation: says increase but value decreases
		}
	}
	if strings.Contains(reasonLower, "reducir") || strings.Contains(reasonLower, "disminuir") || strings.Contains(reasonLower, "decrease") || strings.Contains(reasonLower, "bajar") {
		if newVal > oldVal {
			return true // violation: says decrease but value increases
		}
	}
	return false
}

// checkDrivingAdvice detects recommendations that are driving technique advice rather than setup changes.
func checkDrivingAdvice(change domain.SetupChange) bool {
	drivingPhrases := []string{
		"reduce speed", "reducir velocidad",
		"brake earlier", "frenar antes",
		"brake later", "frenar más tarde",
		"be smoother", "ser más suave",
		"lift earlier", "levantar antes",
		"shift earlier", "cambiar antes",
	}
	reasonLower := strings.ToLower(change.Reason)
	paramLower := strings.ToLower(change.Parameter)

	// If the parameter itself doesn't look like a setup param, flag it
	if paramLower == "" || strings.Contains(paramLower, "técnica") || strings.Contains(paramLower, "technique") {
		return true
	}

	for _, phrase := range drivingPhrases {
		if strings.Contains(reasonLower, phrase) {
			// Only flag if the reason is ONLY about driving, not setup-related too
			setupTerms := []string{"spring", "damper", "wing", "arb", "camber", "pressure", "bias", "diff", "resorte", "amortiguador", "alerón"}
			hasSetupContext := false
			for _, term := range setupTerms {
				if strings.Contains(reasonLower, term) {
					hasSetupContext = true
					break
				}
			}
			if !hasSetupContext {
				return true
			}
		}
	}
	return false
}

// checkFixedParam returns true if the parameter is in the fixed/locked list.
func checkFixedParam(param string, fixedParams []string) bool {
	paramLower := strings.ToLower(param)
	for _, fp := range fixedParams {
		if strings.ToLower(fp) == paramLower {
			return true
		}
	}
	return false
}

// checkUnitPolicy returns true if the new value appears to be in clicks/steps rather than physical units.
func checkUnitPolicy(newValue string) bool {
	valLower := strings.ToLower(newValue)
	clickTerms := []string{"click", "step", "notch", "clic", "paso", "muesca"}
	for _, term := range clickTerms {
		if strings.Contains(valLower, term) {
			return true
		}
	}
	return false
}

// checkPhysicsInversion detects a common LLM hallucination where a parameter change
// is recommended in the wrong direction for the stated symptom.
func checkPhysicsInversion(change domain.SetupChange, paramSubstring, direction, symptom string) bool {
	paramLower := strings.ToLower(change.Parameter)
	reasonLower := strings.ToLower(change.Reason)

	if !strings.Contains(paramLower, strings.ToLower(paramSubstring)) {
		return false
	}

	// Check if the reason mentions the symptom
	symptomES := translateSymptom(symptom)
	if !strings.Contains(reasonLower, symptom) && !strings.Contains(reasonLower, symptomES) {
		return false
	}

	// Check if the actual value change matches the forbidden direction
	oldVal := extractNumericValue(change.OldValue)
	newVal := extractNumericValue(change.NewValue)
	if oldVal == 0 && newVal == 0 {
		return false
	}

	switch direction {
	case "decrease":
		return newVal < oldVal
	case "increase":
		return newVal > oldVal
	}
	return false
}

// checkCausalLink detects when a parameter change claims to fix a symptom
// with no known causal relationship.
func checkCausalLink(change domain.SetupChange, paramSubstring, symptom, phase string) bool {
	paramLower := strings.ToLower(change.Parameter)
	reasonLower := strings.ToLower(change.Reason)

	if !strings.Contains(paramLower, strings.ToLower(paramSubstring)) {
		return false
	}

	symptomES := translateSymptom(symptom)
	phaseES := translatePhase(phase)

	hasSymptom := strings.Contains(reasonLower, symptom) || strings.Contains(reasonLower, symptomES)
	hasPhase := strings.Contains(reasonLower, phase) || strings.Contains(reasonLower, phaseES)

	return hasSymptom && hasPhase
}

// checkScopeError detects when a parameter is recommended for a phase where it has no effect.
func checkScopeError(change domain.SetupChange, paramSubstring, phase string) bool {
	paramLower := strings.ToLower(change.Parameter)
	reasonLower := strings.ToLower(change.Reason)

	if !strings.Contains(paramLower, strings.ToLower(paramSubstring)) {
		return false
	}

	phaseES := translatePhase(phase)
	return strings.Contains(reasonLower, phase) || strings.Contains(reasonLower, phaseES)
}

// checkSymmetricARBChange detects VC-004: both front AND rear ARB softened in the same report.
func checkSymmetricARBChange(items []domain.SetupChange, ruleset *PhysicsRuleset) []domain.SetupChange {
	frontARBIdx := -1
	rearARBIdx := -1
	frontDecreases := false
	rearDecreases := false

	for i, item := range items {
		paramLower := strings.ToLower(item.Parameter)
		if strings.Contains(paramLower, "frontantirollbar") || strings.Contains(paramLower, "front_anti_roll") || strings.Contains(paramLower, "front arb") {
			frontARBIdx = i
			oldVal := extractNumericValue(item.OldValue)
			newVal := extractNumericValue(item.NewValue)
			if newVal < oldVal {
				frontDecreases = true
			}
		}
		if strings.Contains(paramLower, "rearantirollbar") || strings.Contains(paramLower, "rear_anti_roll") || strings.Contains(paramLower, "rear arb") {
			rearARBIdx = i
			oldVal := extractNumericValue(item.OldValue)
			newVal := extractNumericValue(item.NewValue)
			if newVal < oldVal {
				rearDecreases = true
			}
		}
	}

	if frontDecreases && rearDecreases && frontARBIdx >= 0 && rearARBIdx >= 0 {
		log.Warn().Msg("VC-004: both front and rear ARB softened simultaneously — removing both ARB changes")
		var filtered []domain.SetupChange
		for i, item := range items {
			if i != frontARBIdx && i != rearARBIdx {
				filtered = append(filtered, item)
			}
		}
		return filtered
	}
	return items
}

// --- Translation helpers for bilingual reason detection ---

func translateSymptom(en string) string {
	m := map[string]string{
		"understeer": "subviraje",
		"oversteer":  "sobreviraje",
		"traction":   "tracción",
		"braking":    "frenada",
		"stability":  "estabilidad",
	}
	if es, ok := m[en]; ok {
		return es
	}
	return en
}

func translatePhase(en string) string {
	m := map[string]string{
		"entry":      "entrada",
		"mid-corner": "mitad de curva",
		"exit":       "salida",
		"braking":    "frenada",
		"straight":   "recta",
	}
	if es, ok := m[en]; ok {
		return es
	}
	return en
}

// extractNumericValue extracts the first numeric value from a setup value string.
// Reuses the existing ExtractNumeric logic from the package.
func extractNumericValue(s string) float64 {
	v, ok := ExtractNumeric(s)
	if !ok {
		return 0
	}
	return v
}
