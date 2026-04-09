package domain

import "math"

// TelemetryData holds parsed telemetry channels keyed by name.
type TelemetryData struct {
	Channels map[string][]float64
	LapCol   string
	TimeCol  string
}

// GPSPoint represents a single GPS coordinate.
type GPSPoint struct {
	Lat float64 `json:"lat"`
	Lon float64 `json:"lon"`
}

// TelemetrySample holds a single downsampled time-series sample for the frontend charts.
type TelemetrySample struct {
	T    float64 `json:"t"`
	Spd  float64 `json:"spd"`
	Thr  float64 `json:"thr"`
	Brk  float64 `json:"brk"`
	RPM  float64 `json:"rpm"`
	Gear float64 `json:"gear"`
	Lat  float64 `json:"lat"`
	Lon  float64 `json:"lon"`
	Lap  int     `json:"lap"`

	// Steering
	Steer        float64 `json:"steer"`
	SteerTorque  float64 `json:"steer_torque"`
	Clutch       float64 `json:"clutch"`

	// G-forces
	GLat  float64 `json:"g_lat"`
	GLong float64 `json:"g_long"`
	GVert float64 `json:"g_vert"`

	// Ride heights (mm)
	RideHFL float64 `json:"ride_h_fl"`
	RideHFR float64 `json:"ride_h_fr"`
	RideHRL float64 `json:"ride_h_rl"`
	RideHRR float64 `json:"ride_h_rr"`

	// Brake temperatures (°C)
	BrakeTFL float64 `json:"brake_t_fl"`
	BrakeTFR float64 `json:"brake_t_fr"`
	BrakeTRL float64 `json:"brake_t_rl"`
	BrakeTRR float64 `json:"brake_t_rr"`

	// Brake bias
	BrakeBias float64 `json:"brake_bias"`

	// Tyre pressures (kPa)
	TyrePFL float64 `json:"tyre_p_fl"`
	TyrePFR float64 `json:"tyre_p_fr"`
	TyrePRL float64 `json:"tyre_p_rl"`
	TyrePRR float64 `json:"tyre_p_rr"`

	// Tyre temps — centre zone (°C)
	TyreTFL float64 `json:"tyre_t_fl"`
	TyreTFR float64 `json:"tyre_t_fr"`
	TyreTRL float64 `json:"tyre_t_rl"`
	TyreTRR float64 `json:"tyre_t_rr"`

	// Tyre temps — inner/outer (°C)
	TyreTFLInner float64 `json:"tyre_t_fl_inner"`
	TyreTFLOuter float64 `json:"tyre_t_fl_outer"`
	TyreTFRInner float64 `json:"tyre_t_fr_inner"`
	TyreTFROuter float64 `json:"tyre_t_fr_outer"`
	TyreTRLInner float64 `json:"tyre_t_rl_inner"`
	TyreTRLOuter float64 `json:"tyre_t_rl_outer"`
	TyreTRRInner float64 `json:"tyre_t_rr_inner"`
	TyreTRROuter float64 `json:"tyre_t_rr_outer"`

	// Tyre wear (0-1)
	TyreWFL float64 `json:"tyre_w_fl"`
	TyreWFR float64 `json:"tyre_w_fr"`
	TyreWRL float64 `json:"tyre_w_rl"`
	TyreWRR float64 `json:"tyre_w_rr"`

	// Tyre load (N)
	TyreLFL float64 `json:"tyre_l_fl"`
	TyreLFR float64 `json:"tyre_l_fr"`
	TyreLRL float64 `json:"tyre_l_rl"`
	TyreLRR float64 `json:"tyre_l_rr"`

	// Grip fraction (0-1)
	GripFL float64 `json:"grip_fl"`
	GripFR float64 `json:"grip_fr"`
	GripRL float64 `json:"grip_rl"`
	GripRR float64 `json:"grip_rr"`

	// Wheel rotation speeds (rad/s)
	WheelSpFL float64 `json:"wheel_sp_fl"`
	WheelSpFR float64 `json:"wheel_sp_fr"`
	WheelSpRL float64 `json:"wheel_sp_rl"`
	WheelSpRR float64 `json:"wheel_sp_rr"`

	// Engine / drivetrain
	OilTemp   float64 `json:"oil_temp"`
	WaterTemp float64 `json:"water_temp"`
	FuelLevel float64 `json:"fuel_level"`
}

// ExtractTimeSeries builds a downsampled slice of TelemetrySample from TelemetryData.
func (td *TelemetryData) ExtractTimeSeries() []TelemetrySample {
	n := 0
	for _, ch := range td.Channels {
		if len(ch) > n {
			n = len(ch)
		}
	}
	if n == 0 {
		return nil
	}

	step := 1
	timeData := td.Channels[td.TimeCol]
	lapData := td.Channels[td.LapCol]
	speed := firstChannel(td.Channels, "Speed", "Ground_Speed")
	throttle := firstChannel(td.Channels, "Throttle", "Throttle_Pos")
	brake := firstChannel(td.Channels, "Brake", "Brake_Pos")
	rpm := firstChannel(td.Channels, "RPM", "Engine_RPM")
	gear := firstChannel(td.Channels, "Gear")
	lat := firstChannel(td.Channels, "GPS Latitude", "GPS_Latitude", "GPS_Lat", "Latitude", "gLat")
	lon := firstChannel(td.Channels, "GPS Longitude", "GPS_Longitude", "GPS_Lon", "Longitude", "gLon")
	lat, lon = cleanGPSPair(lat, lon)

	// Steering / drivetrain
	steer       := firstChannel(td.Channels, "Steering")
	steerTorque := firstChannel(td.Channels, "Steering_Shaft_Torque")
	clutch      := firstChannel(td.Channels, "Clutch_Pos", "Clutch")

	// G-forces
	gLat  := firstChannel(td.Channels, "G_Force_Lat")
	gLong := firstChannel(td.Channels, "G_Force_Long")
	gVert := firstChannel(td.Channels, "G_Force_Vert")

	// Ride heights
	rideHFL := firstChannel(td.Channels, "Ride_Height_FL")
	rideHFR := firstChannel(td.Channels, "Ride_Height_FR")
	rideHRL := firstChannel(td.Channels, "Ride_Height_RL")
	rideHRR := firstChannel(td.Channels, "Ride_Height_RR")

	// Brake temps & bias
	brakeTFL  := firstChannel(td.Channels, "Brake_Temp_FL")
	brakeTFR  := firstChannel(td.Channels, "Brake_Temp_FR")
	brakeTRL  := firstChannel(td.Channels, "Brake_Temp_RL")
	brakeTRR  := firstChannel(td.Channels, "Brake_Temp_RR")
	brakeBias := firstChannel(td.Channels, "Brake_Bias_Rear")

	// Tyre pressures
	tyrePFL := firstChannel(td.Channels, "Tyre_Pressure_FL")
	tyrePFR := firstChannel(td.Channels, "Tyre_Pressure_FR")
	tyrePRL := firstChannel(td.Channels, "Tyre_Pressure_RL")
	tyrePRR := firstChannel(td.Channels, "Tyre_Pressure_RR")

	// Tyre temps centre
	tyreTFL := firstChannel(td.Channels, "Tyre_Temp_FL_Centre")
	tyreTFR := firstChannel(td.Channels, "Tyre_Temp_FR_Centre")
	tyreTRL := firstChannel(td.Channels, "Tyre_Temp_RL_Centre")
	tyreTRR := firstChannel(td.Channels, "Tyre_Temp_RR_Centre")

	// Tyre temps inner/outer
	tyreTFLInner := firstChannel(td.Channels, "Tyre_Temp_FL_Inner")
	tyreTFLOuter := firstChannel(td.Channels, "Tyre_Temp_FL_Outer")
	tyreTFRInner := firstChannel(td.Channels, "Tyre_Temp_FR_Inner")
	tyreTFROuter := firstChannel(td.Channels, "Tyre_Temp_FR_Outer")
	tyreTRLInner := firstChannel(td.Channels, "Tyre_Temp_RL_Inner")
	tyreTRLOuter := firstChannel(td.Channels, "Tyre_Temp_RL_Outer")
	tyreTRRInner := firstChannel(td.Channels, "Tyre_Temp_RR_Inner")
	tyreTRROuter := firstChannel(td.Channels, "Tyre_Temp_RR_Outer")

	// Tyre wear
	tyreWFL := firstChannel(td.Channels, "Tyre_Wear_FL")
	tyreWFR := firstChannel(td.Channels, "Tyre_Wear_FR")
	tyreWRL := firstChannel(td.Channels, "Tyre_Wear_RL")
	tyreWRR := firstChannel(td.Channels, "Tyre_Wear_RR")

	// Tyre load
	tyreLFL := firstChannel(td.Channels, "Tyre_Load_FL")
	tyreLFR := firstChannel(td.Channels, "Tyre_Load_FR")
	tyreLRL := firstChannel(td.Channels, "Tyre_Load_RL")
	tyreLRR := firstChannel(td.Channels, "Tyre_Load_RR")

	// Grip fraction
	gripFL := firstChannel(td.Channels, "Grip_Fract_FL")
	gripFR := firstChannel(td.Channels, "Grip_Fract_FR")
	gripRL := firstChannel(td.Channels, "Grip_Fract_RL")
	gripRR := firstChannel(td.Channels, "Grip_Fract_RR")

	// Wheel rotation speeds
	wheelSpFL := firstChannel(td.Channels, "Wheel_Rot_Speed_FL")
	wheelSpFR := firstChannel(td.Channels, "Wheel_Rot_Speed_FR")
	wheelSpRL := firstChannel(td.Channels, "Wheel_Rot_Speed_RL")
	wheelSpRR := firstChannel(td.Channels, "Wheel_Rot_Speed_RR")

	// Engine
	oilTemp   := firstChannel(td.Channels, "Eng_Oil_Temp")
	waterTemp := firstChannel(td.Channels, "Eng_Water_Temp")
	fuelLevel := firstChannel(td.Channels, "Fuel_Level")

	safeGet := func(s []float64, i int) float64 {
		if i < len(s) {
			return s[i]
		}
		return 0
	}

	out := make([]TelemetrySample, 0, n/step+1)
	for i := 0; i < n; i += step {
		s := TelemetrySample{
			T:    safeGet(timeData, i),
			Spd:  safeGet(speed, i),
			Thr:  safeGet(throttle, i),
			Brk:  safeGet(brake, i),
			RPM:  safeGet(rpm, i),
			Gear: safeGet(gear, i),
			Lat:  safeGet(lat, i),
			Lon:  safeGet(lon, i),

			Steer:       safeGet(steer, i),
			SteerTorque: safeGet(steerTorque, i),
			Clutch:      safeGet(clutch, i),

			GLat:  safeGet(gLat, i),
			GLong: safeGet(gLong, i),
			GVert: safeGet(gVert, i),

			RideHFL: safeGet(rideHFL, i),
			RideHFR: safeGet(rideHFR, i),
			RideHRL: safeGet(rideHRL, i),
			RideHRR: safeGet(rideHRR, i),

			BrakeTFL:  safeGet(brakeTFL, i),
			BrakeTFR:  safeGet(brakeTFR, i),
			BrakeTRL:  safeGet(brakeTRL, i),
			BrakeTRR:  safeGet(brakeTRR, i),
			BrakeBias: safeGet(brakeBias, i),

			TyrePFL: safeGet(tyrePFL, i),
			TyrePFR: safeGet(tyrePFR, i),
			TyrePRL: safeGet(tyrePRL, i),
			TyrePRR: safeGet(tyrePRR, i),

			TyreTFL: safeGet(tyreTFL, i),
			TyreTFR: safeGet(tyreTFR, i),
			TyreTRL: safeGet(tyreTRL, i),
			TyreTRR: safeGet(tyreTRR, i),

			TyreTFLInner: safeGet(tyreTFLInner, i),
			TyreTFLOuter: safeGet(tyreTFLOuter, i),
			TyreTFRInner: safeGet(tyreTFRInner, i),
			TyreTFROuter: safeGet(tyreTFROuter, i),
			TyreTRLInner: safeGet(tyreTRLInner, i),
			TyreTRLOuter: safeGet(tyreTRLOuter, i),
			TyreTRRInner: safeGet(tyreTRRInner, i),
			TyreTRROuter: safeGet(tyreTRROuter, i),

			TyreWFL: safeGet(tyreWFL, i),
			TyreWFR: safeGet(tyreWFR, i),
			TyreWRL: safeGet(tyreWRL, i),
			TyreWRR: safeGet(tyreWRR, i),

			TyreLFL: safeGet(tyreLFL, i),
			TyreLFR: safeGet(tyreLFR, i),
			TyreLRL: safeGet(tyreLRL, i),
			TyreLRR: safeGet(tyreLRR, i),

			GripFL: safeGet(gripFL, i),
			GripFR: safeGet(gripFR, i),
			GripRL: safeGet(gripRL, i),
			GripRR: safeGet(gripRR, i),

			WheelSpFL: safeGet(wheelSpFL, i),
			WheelSpFR: safeGet(wheelSpFR, i),
			WheelSpRL: safeGet(wheelSpRL, i),
			WheelSpRR: safeGet(wheelSpRR, i),

			OilTemp:   safeGet(oilTemp, i),
			WaterTemp: safeGet(waterTemp, i),
			FuelLevel: safeGet(fuelLevel, i),
		}
		if i < len(lapData) {
			s.Lap = int(lapData[i])
		}
		out = append(out, s)
	}
	return out
}

// LapStats holds per-lap statistics.
type LapStats struct {
	Lap         int     `json:"lap"`
	Duration    float64 `json:"duration"`
	AvgSpeed    float64 `json:"avg_speed"`
	MaxSpeed    float64 `json:"max_speed"`
	AvgThrottle float64 `json:"avg_throttle"`
	AvgBrake    float64 `json:"avg_brake"`
	AvgRPM      float64 `json:"avg_rpm"`
}

// SessionStats holds aggregated session information.
type SessionStats struct {
	CircuitName string     `json:"circuit_name"`
	TotalLaps   int        `json:"total_laps"`
	BestLapTime float64    `json:"best_lap_time"`
	AvgLapTime  float64    `json:"avg_lap_time"`
	Laps        []LapStats `json:"laps"`
}

// SessionStats computes aggregated stats from the telemetry data.
func (td *TelemetryData) SessionStats() SessionStats {
	lapData, ok := td.Channels[td.LapCol]
	timeData, tok := td.Channels[td.TimeCol]
	if !ok || !tok || len(lapData) == 0 {
		return SessionStats{}
	}

	lapTimeData := firstChannel(td.Channels, "Lap_Time", "Lap Time", "LapTime")

	lapTimes := make(map[int][]float64)
	for i, lv := range lapData {
		lap := int(lv)
		if lap <= 0 {
			continue
		}
		if i < len(timeData) {
			lapTimes[lap] = append(lapTimes[lap], timeData[i])
		}
	}

	var laps []LapStats
	best := 0.0
	totalDur := 0.0
	hasValidLap := false

	for lapNum, times := range lapTimes {
		if len(times) < 2 {
			continue
		}
		duration := 0.0
		if lapTimeData != nil {
			startIdx := -1
			endIdx := -1
			for i, lv := range lapData {
				if int(lv) == lapNum {
					if startIdx == -1 {
						startIdx = i
					}
					endIdx = i
				}
			}
			if startIdx >= 0 && endIdx >= startIdx {
				maxLapTime := 0.0
				for i := startIdx; i <= endIdx && i < len(lapTimeData); i++ {
					v := lapTimeData[i]
					if v > maxLapTime {
						maxLapTime = v
					}
				}
				if maxLapTime > 0 {
					duration = maxLapTime
				}
			}
		}

		if duration <= 0 {
			duration = times[len(times)-1] - times[0]
		}
		if duration <= 0 {
			continue
		}

		ls := LapStats{Lap: lapNum, Duration: duration}

		startIdx := -1
		endIdx := -1
		for i, lv := range lapData {
			if int(lv) == lapNum {
				if startIdx == -1 {
					startIdx = i
				}
				endIdx = i
			}
		}
		if startIdx >= 0 && endIdx > startIdx {
			ls.AvgSpeed = avgSlice(td.Channels["Speed"], startIdx, endIdx)
			ls.MaxSpeed = maxSlice(td.Channels["Speed"], startIdx, endIdx)
			ls.AvgThrottle = avgSlice(td.Channels["Throttle"], startIdx, endIdx)
			ls.AvgBrake = avgSlice(td.Channels["Brake"], startIdx, endIdx)
			ls.AvgRPM = avgSlice(td.Channels["RPM"], startIdx, endIdx)
		}

		laps = append(laps, ls)
		totalDur += duration
		if !hasValidLap || duration < best {
			best = duration
			hasValidLap = true
		}
	}

	if len(laps) == 0 {
		return SessionStats{}
	}

	avgLap := totalDur / float64(len(laps))

	return SessionStats{
		TotalLaps:   len(laps),
		BestLapTime: best,
		AvgLapTime:  avgLap,
		Laps:        laps,
	}
}

func firstChannel(channels map[string][]float64, names ...string) []float64 {
	for _, name := range names {
		if data, ok := channels[name]; ok {
			return data
		}
	}
	return nil
}

func cleanGPSPair(latData, lonData []float64) ([]float64, []float64) {
	if latData == nil || lonData == nil {
		return latData, lonData
	}
	n := len(latData)
	if len(lonData) < n {
		n = len(lonData)
	}
	if n < 3 {
		return latData, lonData
	}

	cleanLat := make([]float64, len(latData))
	copy(cleanLat, latData)
	cleanLon := make([]float64, len(lonData))
	copy(cleanLon, lonData)

	isValid := func(lat, lon float64) bool {
		return (lat != 0 || lon != 0) &&
			!math.IsNaN(lat) && !math.IsNaN(lon) &&
			!math.IsInf(lat, 0) && !math.IsInf(lon, 0) &&
			lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180
	}

	lastValid := -1
	for i := 0; i < n; i++ {
		if !isValid(cleanLat[i], cleanLon[i]) {
			if lastValid >= 0 {
				cleanLat[i] = cleanLat[lastValid]
				cleanLon[i] = cleanLon[lastValid]
			} else {
				cleanLat[i] = 0
				cleanLon[i] = 0
			}
			continue
		}
		if lastValid == -1 {
			lastValid = i
			continue
		}
		lastValid = i
	}

	return cleanLat, cleanLon
}

// ExtractGPS returns GPS points from telemetry lat/lon channels.
func (td *TelemetryData) ExtractGPS() []GPSPoint {
	latKeys := []string{"GPS Latitude", "GPS_Latitude", "Latitude", "gLat", "CG_PosY"}
	lonKeys := []string{"GPS Longitude", "GPS_Longitude", "Longitude", "gLon", "CG_PosX"}

	var latData, lonData []float64
	for _, k := range latKeys {
		if d, ok := td.Channels[k]; ok {
			latData = d
			break
		}
	}
	for _, k := range lonKeys {
		if d, ok := td.Channels[k]; ok {
			lonData = d
			break
		}
	}
	if latData == nil || lonData == nil {
		return nil
	}
	latData, lonData = cleanGPSPair(latData, lonData)

	n := len(latData)
	if len(lonData) < n {
		n = len(lonData)
	}

	step := 1
	if n > 2000 {
		step = n / 2000
	}

	var points []GPSPoint
	for i := 0; i < n; i += step {
		if latData[i] != 0 || lonData[i] != 0 {
			points = append(points, GPSPoint{Lat: latData[i], Lon: lonData[i]})
		}
	}
	return points
}

func avgSlice(data []float64, start, end int) float64 {
	if data == nil || start >= len(data) {
		return 0
	}
	if end >= len(data) {
		end = len(data) - 1
	}
	sum := 0.0
	count := 0
	for i := start; i <= end; i++ {
		sum += data[i]
		count++
	}
	if count == 0 {
		return 0
	}
	return sum / float64(count)
}

func maxSlice(data []float64, start, end int) float64 {
	if data == nil || start >= len(data) {
		return 0
	}
	if end >= len(data) {
		end = len(data) - 1
	}
	m := data[start]
	for i := start + 1; i <= end; i++ {
		if data[i] > m {
			m = data[i]
		}
	}
	return m
}
