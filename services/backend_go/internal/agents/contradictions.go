package agents

import (
	"fmt"
	"strings"

	"github.com/rs/zerolog/log"

	"github.com/viciruela/rfactor2-engineer/internal/domain"
)

// Contradiction represents a detected conflict between two domain engineer proposals.
type Contradiction struct {
	ID         string `json:"id"`
	Parameter  string `json:"parameter"`
	Agent1     string `json:"agent_1"`
	Proposal1  string `json:"proposal_1"`
	Direction1 string `json:"direction_1"`
	Agent2     string `json:"agent_2"`
	Proposal2  string `json:"proposal_2"`
	Direction2 string `json:"direction_2"`
}

// domainEngineerOutput holds the parsed result from a single domain engineer.
type domainEngineerOutput struct {
	Role            string
	Label           string
	Sections        []domain.SectionReport
	FindingsSummary string
	Confidence      float64
}

// parameterCouplingMatrix defines indirect coupling between parameters across domains.
// When an agent targets a key and another agent targets one of its coupled params
// in a conflicting direction, that constitutes a coupled contradiction.
var parameterCouplingMatrix = map[string][]string{
	"RearWingSetting":        {"RearRideHeightSetting", "RearSpringRate"},
	"FrontARBSetting":        {"FrontSpringRate", "FrontRideHeightSetting"},
	"BrakeBiasSetting":       {"FrontSpringRate", "RearSpringRate"},
	"DifferentialLockSetting": {"RearSpringRate", "RearARBSetting"},
}

// detectContradictions performs deterministic contradiction detection across domain
// engineer outputs. It checks for:
// 1. Direct opposition: same parameter, opposite direction.
// 2. Coupled parameter conflict: parameter coupling matrix with inconsistent intent.
// No LLM call — pure algorithmic comparison.
func detectContradictions(reports []domainEngineerOutput) []Contradiction {
	// Build parameter → (agent, direction, proposal) index
	type paramProposal struct {
		agent     string
		direction string
		proposal  string
		param     string
	}

	var allProposals []paramProposal
	for _, rep := range reports {
		for _, sec := range rep.Sections {
			for _, item := range sec.Items {
				dir := inferChangeDirection(item)
				allProposals = append(allProposals, paramProposal{
					agent:     rep.Label,
					direction: dir,
					proposal:  fmt.Sprintf("%s → %s", item.Parameter, item.NewValue),
					param:     item.Parameter,
				})
			}
		}
	}

	var contradictions []Contradiction
	cfID := 0

	// 1. Direct opposition: same parameter from different agents, opposite direction
	for i := 0; i < len(allProposals); i++ {
		for j := i + 1; j < len(allProposals); j++ {
			a, b := allProposals[i], allProposals[j]
			if a.agent == b.agent {
				continue
			}
			if normalizeParamKey(a.param) != normalizeParamKey(b.param) {
				continue
			}
			if a.direction != "" && b.direction != "" && a.direction != b.direction {
				cfID++
				contradictions = append(contradictions, Contradiction{
					ID:         fmt.Sprintf("CF-%03d", cfID),
					Parameter:  a.param,
					Agent1:     a.agent,
					Proposal1:  a.proposal,
					Direction1: a.direction,
					Agent2:     b.agent,
					Proposal2:  b.proposal,
					Direction2: b.direction,
				})
			}
		}
	}

	// 2. Coupled parameter conflict
	byParam := make(map[string]paramProposal)
	for _, p := range allProposals {
		byParam[normalizeParamKey(p.param)] = p
	}

	for primaryParam, coupled := range parameterCouplingMatrix {
		primary, hasPrimary := byParam[normalizeParamKey(primaryParam)]
		if !hasPrimary {
			continue
		}
		for _, coupledParam := range coupled {
			secondary, hasSecondary := byParam[normalizeParamKey(coupledParam)]
			if !hasSecondary {
				continue
			}
			if primary.agent == secondary.agent {
				continue
			}
			// Both params are being changed by different agents.
			// If the coupling creates a conflict (e.g., one adds and the other removes load),
			// flag it. The Chief will decide.
			if primary.direction != "" && secondary.direction != "" {
				cfID++
				contradictions = append(contradictions, Contradiction{
					ID:         fmt.Sprintf("CF-%03d", cfID),
					Parameter:  primaryParam + " ↔ " + coupledParam,
					Agent1:     primary.agent,
					Proposal1:  primary.proposal,
					Direction1: primary.direction,
					Agent2:     secondary.agent,
					Proposal2:  secondary.proposal,
					Direction2: secondary.direction,
				})
			}
		}
	}

	if len(contradictions) > 0 {
		log.Info().Int("count", len(contradictions)).Msg("contradictions detected between domain engineers")
	}
	return contradictions
}

// inferChangeDirection determines the direction of a setup change by comparing
// old and new values numerically. Returns "increase", "decrease", or "".
func inferChangeDirection(change domain.SetupChange) string {
	// Try to extract from reason text first (more reliable)
	reasonLower := strings.ToLower(change.Reason)
	if strings.Contains(reasonLower, "aumentar") || strings.Contains(reasonLower, "incrementar") || strings.Contains(reasonLower, "subir") {
		return "increase"
	}
	if strings.Contains(reasonLower, "reducir") || strings.Contains(reasonLower, "disminuir") || strings.Contains(reasonLower, "bajar") {
		return "decrease"
	}

	// Fall back to numeric comparison
	oldVal, okOld := ExtractNumeric(change.OldValue)
	newVal, okNew := ExtractNumeric(change.NewValue)
	if okOld && okNew {
		if newVal > oldVal {
			return "increase"
		}
		if newVal < oldVal {
			return "decrease"
		}
	}

	// Try new_value alone if old isn't set yet (domain engineers may not have OldValue)
	// We can also look at the reason for "de X a Y" pattern
	return ""
}

// formatContradictionsForChief formats the contradiction list as text for the Chief prompt.
func formatContradictionsForChief(contradictions []Contradiction) string {
	if len(contradictions) == 0 {
		return "No se detectaron contradicciones entre los ingenieros de dominio."
	}

	var sb strings.Builder
	for _, c := range contradictions {
		sb.WriteString(fmt.Sprintf("[%s] Parámetro: %s\n", c.ID, c.Parameter))
		sb.WriteString(fmt.Sprintf("  %s propone: %s (dirección: %s)\n", c.Agent1, c.Proposal1, c.Direction1))
		sb.WriteString(fmt.Sprintf("  %s propone: %s (dirección: %s)\n", c.Agent2, c.Proposal2, c.Direction2))
		sb.WriteString("  → El ingeniero jefe debe resolver este conflicto.\n\n")
	}
	return sb.String()
}

// formatDomainReportsForChief formats all domain engineer reports as text for the Chief prompt.
func formatDomainReportsForChief(reports []domainEngineerOutput) string {
	var sb strings.Builder
	for _, rep := range reports {
		sb.WriteString(fmt.Sprintf("=== %s (confianza: %.0f%%) ===\n", rep.Label, rep.Confidence*100))
		if rep.FindingsSummary != "" {
			sb.WriteString("Hallazgos: " + rep.FindingsSummary + "\n\n")
		}
		for _, sec := range rep.Sections {
			if len(sec.Items) == 0 {
				continue
			}
			sb.WriteString(fmt.Sprintf("[%s]\n", sec.Section))
			for _, item := range sec.Items {
				sb.WriteString(fmt.Sprintf("  %s → %s: %s\n", item.Parameter, item.NewValue, item.Reason))
			}
			sb.WriteString("\n")
		}
		sb.WriteString("\n")
	}

	if sb.Len() == 0 {
		return "Los ingenieros de dominio no propusieron cambios."
	}
	return sb.String()
}
