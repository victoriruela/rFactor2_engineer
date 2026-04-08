package parsers

import (
	"math"
	"sort"
)

// SmoothGPS applies outlier removal and rolling window smoothing to GPS coordinates.
// Replaces zeros with NaN-equivalent, removes outliers beyond 1.5*std from median,
// then applies an 11-sample centered rolling mean.
func SmoothGPS(data []float64) []float64 {
	if len(data) == 0 {
		return data
	}

	result := make([]float64, len(data))
	copy(result, data)

	// Replace zeros with forward/backward fill
	replaceZeros(result)

	// Calculate median and std
	median := calcMedian(result)
	std := calcStd(result, median)

	// Replace outliers (> 1.5 * std from median) with median
	if std > 0 {
		threshold := 1.5 * std
		for i, v := range result {
			if math.Abs(v-median) > threshold {
				result[i] = median
			}
		}
	}

	// Apply 11-sample centered rolling mean
	result = rollingMean(result, 11)

	return result
}

func replaceZeros(data []float64) {
	// Forward fill: replace zeros with the last non-zero value
	lastValid := math.NaN()
	for i, v := range data {
		if v != 0 {
			lastValid = v
		} else if !math.IsNaN(lastValid) {
			data[i] = lastValid
		}
	}

	// Backward fill: replace remaining zeros
	lastValid = math.NaN()
	for i := len(data) - 1; i >= 0; i-- {
		if data[i] != 0 {
			lastValid = data[i]
		} else if !math.IsNaN(lastValid) {
			data[i] = lastValid
		}
	}
}

func calcMedian(data []float64) float64 {
	if len(data) == 0 {
		return 0
	}
	sorted := make([]float64, len(data))
	copy(sorted, data)
	sort.Float64s(sorted)

	n := len(sorted)
	if n%2 == 0 {
		return (sorted[n/2-1] + sorted[n/2]) / 2
	}
	return sorted[n/2]
}

func calcStd(data []float64, mean float64) float64 {
	if len(data) <= 1 {
		return 0
	}
	sumSq := 0.0
	for _, v := range data {
		d := v - mean
		sumSq += d * d
	}
	return math.Sqrt(sumSq / float64(len(data)))
}

func rollingMean(data []float64, window int) []float64 {
	if len(data) == 0 || window <= 1 {
		return data
	}

	result := make([]float64, len(data))
	half := window / 2

	for i := range data {
		start := i - half
		if start < 0 {
			start = 0
		}
		end := i + half + 1
		if end > len(data) {
			end = len(data)
		}

		sum := 0.0
		count := 0
		for j := start; j < end; j++ {
			sum += data[j]
			count++
		}
		if count > 0 {
			result[i] = sum / float64(count)
		}
	}

	return result
}
