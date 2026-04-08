package handlers

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

// TracksHandler serves static circuit metadata.
type TracksHandler struct{}

// NewTracksHandler creates a tracks handler.
func NewTracksHandler() *TracksHandler {
	return &TracksHandler{}
}

// circuitMeta holds display info for known circuits.
type circuitMeta struct {
	Name    string  `json:"name"`
	Country string  `json:"country"`
	Length  float64 `json:"length_km"`
	Turns   int     `json:"turns"`
}

var knownCircuits = map[string]circuitMeta{
	"barcelona":    {Name: "Circuit de Barcelona-Catalunya", Country: "ES", Length: 4.655, Turns: 16},
	"monza":        {Name: "Autodromo Nazionale Monza", Country: "IT", Length: 5.793, Turns: 11},
	"spa":          {Name: "Circuit de Spa-Francorchamps", Country: "BE", Length: 7.004, Turns: 19},
	"silverstone":  {Name: "Silverstone Circuit", Country: "GB", Length: 5.891, Turns: 18},
	"nurburgring":  {Name: "Nürburgring GP-Strecke", Country: "DE", Length: 5.148, Turns: 15},
	"suzuka":       {Name: "Suzuka International Racing Course", Country: "JP", Length: 5.807, Turns: 18},
	"imola":        {Name: "Autodromo Enzo e Dino Ferrari", Country: "IT", Length: 4.909, Turns: 19},
	"mugello":      {Name: "Autodromo Internazionale del Mugello", Country: "IT", Length: 5.245, Turns: 15},
	"paul_ricard":  {Name: "Circuit Paul Ricard", Country: "FR", Length: 5.842, Turns: 15},
	"zandvoort":    {Name: "Circuit Zandvoort", Country: "NL", Length: 4.259, Turns: 14},
	"portimao":     {Name: "Autódromo Internacional do Algarve", Country: "PT", Length: 4.653, Turns: 15},
	"hungaroring":  {Name: "Hungaroring", Country: "HU", Length: 4.381, Turns: 14},
	"red_bull_ring": {Name: "Red Bull Ring", Country: "AT", Length: 4.318, Turns: 10},
}

// ListTracks handles GET /api/tracks
func (h *TracksHandler) ListTracks(c *gin.Context) {
	result := make([]gin.H, 0, len(knownCircuits))
	for id, meta := range knownCircuits {
		result = append(result, gin.H{
			"id":        id,
			"name":      meta.Name,
			"country":   meta.Country,
			"length_km": meta.Length,
			"turns":     meta.Turns,
		})
	}
	c.JSON(http.StatusOK, gin.H{"tracks": result})
}
