package agents

import (
	"strings"
	"testing"

	"github.com/viciruela/rfactor2-engineer/internal/domain"
)

func TestBuildCoherentReasonUsesFinalValues(t *testing.T) {
	reason := buildCoherentReason("bajar de 10 deg a 8 deg para mejorar apoyo", "10 deg", "12")

	if !strings.Contains(reason, "Aumentar de 10 deg a 12 deg") {
		t.Fatalf("expected canonical direction and values, got %q", reason)
	}
	if strings.Contains(strings.ToLower(reason), "a 8 deg") {
		t.Fatalf("expected stale target value to be removed, got %q", reason)
	}
}

func TestNormalizeChiefReasonsWithFinalValuesAfterSymmetry(t *testing.T) {
	setup := domain.NewSetup()
	setup.Sections["FRONTLEFT"] = &domain.SetupSection{
		Name: "FRONTLEFT",
		Params: map[string]string{
			"Camber": "-3.0 deg",
		},
	}
	setup.Sections["FRONTRIGHT"] = &domain.SetupSection{
		Name: "FRONTRIGHT",
		Params: map[string]string{
			"Camber": "-3.0 deg",
		},
	}

	chief := &chiefOutput{
		Sections: []domain.SectionReport{
			{
				Section: "FRONTLEFT",
				Items: []domain.SetupChange{
					{Parameter: "Camber", NewValue: "-2.5", Reason: "bajar de -3.0 deg a -2.5 deg"},
				},
			},
			{
				Section: "FRONTRIGHT",
				Items: []domain.SetupChange{
					{Parameter: "Camber", NewValue: "-2.0", Reason: "subir de -3.0 deg a -2.0 deg"},
				},
			},
		},
		Reasoning: "texto original no fiable",
	}

	enforceAxleSymmetry(chief, setup)
	normalizeChiefReasonsWithFinalValues(chief, setup)

	left := chief.Sections[0].Items[0]
	right := chief.Sections[1].Items[0]

	if left.NewValue != "-2 deg" && left.NewValue != "-2.5 deg" {
		t.Fatalf("unexpected normalized left value: %q", left.NewValue)
	}
	if left.NewValue != right.NewValue {
		t.Fatalf("expected symmetric final values, got left=%q right=%q", left.NewValue, right.NewValue)
	}
	if !strings.Contains(left.Reason, "de -3.0 deg a ") {
		t.Fatalf("expected left reason to include final traceability, got %q", left.Reason)
	}
	if !strings.Contains(right.Reason, "de -3.0 deg a ") {
		t.Fatalf("expected right reason to include final traceability, got %q", right.Reason)
	}
	if !strings.Contains(chief.Reasoning, "Estrategia final validada") {
		t.Fatalf("expected canonical chief reasoning, got %q", chief.Reasoning)
	}
}

func TestBuildChiefReasoningFromSetupMapWithChanges(t *testing.T) {
	fullSetup := map[string][]domain.SetupChange{
		"REARLEFT": {
			{
				Parameter: "RideHeightSetting",
				OldValue:  "31 mm",
				NewValue:  "30 mm",
				Reason:    "Reducir de 31 mm a 30 mm: mejora estabilidad en apoyo",
			},
		},
	}

	reasoning := buildChiefReasoningFromSetupMap(fullSetup)
	if !strings.Contains(reasoning, "Estrategia final validada") {
		t.Fatalf("expected strategy prefix, got %q", reasoning)
	}
	if !strings.Contains(reasoning, "REARLEFT / RideHeightSetting") {
		t.Fatalf("expected section/parameter traceability, got %q", reasoning)
	}
	if strings.Contains(reasoning, "No se aplican cambios") {
		t.Fatalf("reasoning should not claim no changes when full_setup has items: %q", reasoning)
	}
}

func TestSanitizeReasonDetailRemovesDuplicatedTracePrefix(t *testing.T) {
	got := sanitizeReasonDetail("de 31 mm a 30 mm: de 31 mm a 30 mm: mejora estabilidad en apoyo")
	want := "mejora estabilidad en apoyo"
	if got != want {
		t.Fatalf("expected %q, got %q", want, got)
	}
}

func TestSanitizeReasonDetailNormalizesMojibake(t *testing.T) {
	got := sanitizeReasonDetail("optimizar la distribuciÃ³n y la aceleraciÃ³n con cÃ¡mara a -2.5Â°")
	if strings.Contains(got, "Ã") || strings.Contains(got, "Â") {
		t.Fatalf("expected mojibake cleaned, got %q", got)
	}
	if !strings.Contains(got, "distribución") || !strings.Contains(got, "aceleración") || !strings.Contains(got, "cámara") || !strings.Contains(got, "-2.5°") {
		t.Fatalf("expected normalized accents and degree symbol, got %q", got)
	}
}
