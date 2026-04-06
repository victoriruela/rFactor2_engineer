package parsers

import (
	"bytes"
	"compress/zlib"
	"encoding/binary"
	"fmt"
	"io"
	"math"
	"os"
	"strings"

	"github.com/viciruela/rfactor2-engineer/internal/domain"
)

// MATLAB Level 5 data type constants
const (
	miINT8    = 1
	miUINT8   = 2
	miINT16   = 3
	miUINT16  = 4
	miINT32   = 5
	miUINT32  = 6
	miSINGLE  = 7
	miDOUBLE  = 9
	miINT64   = 12
	miUINT64  = 13
	miMATRIX  = 14
	miCOMPRESSED = 15
	miUTF8    = 16

	mxDOUBLE_CLASS = 6
	mxSINGLE_CLASS = 7
	mxINT8_CLASS   = 8
	mxUINT8_CLASS  = 9
	mxINT16_CLASS  = 10
	mxUINT16_CLASS = 11
	mxINT32_CLASS  = 12
	mxUINT32_CLASS = 13
	mxINT64_CLASS  = 14
	mxUINT64_CLASS = 15
	mxSTRUCT_CLASS = 2
)

// ParseMATFile parses a MATLAB Level 5 .mat file exported from MoTeC i2.
// Extracts numeric channels and aligns them to the base length.
func ParseMATFile(path string) (*domain.TelemetryData, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("reading mat file: %w", err)
	}

	if len(data) < 128 {
		return nil, ErrNoData
	}

	// Skip 128-byte header
	// Bytes 124-125: version (0x0100)
	// Bytes 126-127: endian indicator ("IM" = little-endian)
	endianIndicator := string(data[126:128])
	var order binary.ByteOrder
	if endianIndicator == "IM" {
		order = binary.LittleEndian
	} else {
		order = binary.BigEndian
	}

	channels := make(map[string][]float64)
	offset := 128

	for offset < len(data) {
		if offset+8 > len(data) {
			break
		}

		tag := readTag(data[offset:], order)
		offset += 8

		if tag.dataType == 0 || tag.numBytes == 0 {
			break
		}

		elementEnd := offset + int(tag.numBytes)
		// Pad to 8-byte boundary
		paddedEnd := elementEnd
		if paddedEnd%8 != 0 {
			paddedEnd += 8 - paddedEnd%8
		}

		if elementEnd > len(data) {
			break
		}

		elementData := data[offset:elementEnd]

		if tag.dataType == miCOMPRESSED {
			decompressed, err := decompressZlib(elementData)
			if err == nil {
				name, values := parseMatrixElement(decompressed, order)
				if name != "" && len(values) > 0 {
					channels[name] = values
				}
			}
		} else if tag.dataType == miMATRIX {
			name, values := parseMatrixElement(elementData, order)
			if name != "" && len(values) > 0 {
				channels[name] = values
			}
		}

		offset = paddedEnd
	}

	if len(channels) == 0 {
		return nil, ErrNoChannels
	}

	// Determine base length (use Session_Elapsed_Time if available)
	baseLen := 0
	if v, ok := channels["Session_Elapsed_Time"]; ok {
		baseLen = len(v)
	} else {
		for _, v := range channels {
			if len(v) > baseLen {
				baseLen = len(v)
			}
		}
	}

	// Align channels
	aligned := make(map[string][]float64)
	for name, vals := range channels {
		if len(vals) == baseLen {
			aligned[name] = vals
		} else if len(vals) > baseLen {
			aligned[name] = vals[:baseLen]
		} else {
			padded := make([]float64, baseLen)
			copy(padded, vals)
			for i := len(vals); i < baseLen; i++ {
				padded[i] = math.NaN()
			}
			aligned[name] = padded
		}
	}

	// Apply column renames for consistency
	renameMap := map[string]string{
		"GPS_Latitude":              "GPS Latitude",
		"GPS_Longitude":             "GPS Longitude",
		"Throttle_Pos":              "Throttle",
		"Brake_Pos":                 "Brake",
		"Steering_Wheel_Position":   "Steering",
		"Engine_RPM":                "RPM",
		"Ground_Speed":              "Speed",
	}
	for old, new := range renameMap {
		if v, ok := aligned[old]; ok {
			aligned[new] = v
			delete(aligned, old)
		}
	}

	td := &domain.TelemetryData{Channels: aligned}
	detectSpecialColumns(td)

	// Apply GPS smoothing
	for _, col := range []string{"GPS Latitude", "GPS Longitude"} {
		if data, ok := td.Channels[col]; ok {
			td.Channels[col] = SmoothGPS(data)
		}
	}

	// Filter incomplete laps
	FilterIncompleteLaps(td)

	return td, nil
}

type tagInfo struct {
	dataType uint32
	numBytes uint32
}

func readTag(data []byte, order binary.ByteOrder) tagInfo {
	if len(data) < 8 {
		return tagInfo{}
	}
	dt := order.Uint32(data[0:4])
	nb := order.Uint32(data[4:8])

	// Check for small data element format (SDE)
	if dt>>16 != 0 {
		// SDE: upper 16 bits of dt = num bytes, lower 16 = data type
		return tagInfo{
			dataType: dt & 0xFFFF,
			numBytes: dt >> 16,
		}
	}

	return tagInfo{dataType: dt, numBytes: nb}
}

func decompressZlib(data []byte) ([]byte, error) {
	r, err := zlib.NewReader(bytes.NewReader(data))
	if err != nil {
		return nil, err
	}
	defer r.Close()
	return io.ReadAll(r)
}

func parseMatrixElement(data []byte, order binary.ByteOrder) (string, []float64) {
	if len(data) < 16 {
		return "", nil
	}

	offset := 0

	// Array flags subelement
	tag := readTag(data[offset:], order)
	offset += 8
	if tag.numBytes < 8 {
		return "", nil
	}
	// Read array class from flags
	// arrayClass := data[offset] & 0xFF
	flagsEnd := offset + int(tag.numBytes)
	if flagsEnd%8 != 0 {
		flagsEnd += 8 - flagsEnd%8
	}
	offset = flagsEnd

	// Dimensions subelement
	if offset+8 > len(data) {
		return "", nil
	}
	dimTag := readTag(data[offset:], order)
	offset += 8
	dimEnd := offset + int(dimTag.numBytes)
	if dimEnd%8 != 0 {
		dimEnd += 8 - dimEnd%8
	}
	if dimEnd > len(data) {
		return "", nil
	}
	offset = dimEnd

	// Name subelement
	if offset+8 > len(data) {
		return "", nil
	}

	nameTag := readTag(data[offset:], order)
	var name string

	// Check for SDE
	if nameTag.dataType>>16 != 0 || (nameTag.numBytes <= 4 && nameTag.dataType != 0) {
		// Small data element: name is in the tag itself or immediately after
		rawDT := order.Uint32(data[offset : offset+4])
		if rawDT>>16 != 0 {
			// SDE format
			nb := rawDT >> 16
			if nb <= 4 {
				name = strings.TrimRight(string(data[offset+4:offset+4+int(nb)]), "\x00")
			}
			offset += 8
		} else {
			offset += 8
			nameEnd := offset + int(nameTag.numBytes)
			if nameEnd > len(data) {
				return "", nil
			}
			name = strings.TrimRight(string(data[offset:nameEnd]), "\x00")
			if nameEnd%8 != 0 {
				nameEnd += 8 - nameEnd%8
			}
			offset = nameEnd
		}
	} else {
		offset += 8
		nameEnd := offset + int(nameTag.numBytes)
		if nameEnd > len(data) {
			return "", nil
		}
		name = strings.TrimRight(string(data[offset:nameEnd]), "\x00")
		if nameEnd%8 != 0 {
			nameEnd += 8 - nameEnd%8
		}
		offset = nameEnd
	}

	if name == "" {
		return "", nil
	}

	// Remaining data: look for numeric data subelement
	values := extractNumericData(data[offset:], order)

	return name, values
}

func extractNumericData(data []byte, order binary.ByteOrder) []float64 {
	if len(data) < 8 {
		return nil
	}

	tag := readTag(data, order)
	offset := 8
	numBytes := int(tag.numBytes)

	if offset+numBytes > len(data) {
		numBytes = len(data) - offset
	}

	switch tag.dataType {
	case miDOUBLE:
		count := numBytes / 8
		values := make([]float64, count)
		for i := 0; i < count; i++ {
			bits := order.Uint64(data[offset+i*8 : offset+i*8+8])
			values[i] = math.Float64frombits(bits)
		}
		return values

	case miSINGLE:
		count := numBytes / 4
		values := make([]float64, count)
		for i := 0; i < count; i++ {
			bits := order.Uint32(data[offset+i*4 : offset+i*4+4])
			values[i] = float64(math.Float32frombits(bits))
		}
		return values

	case miINT32:
		count := numBytes / 4
		values := make([]float64, count)
		for i := 0; i < count; i++ {
			v := int32(order.Uint32(data[offset+i*4 : offset+i*4+4]))
			values[i] = float64(v)
		}
		return values

	case miUINT32:
		count := numBytes / 4
		values := make([]float64, count)
		for i := 0; i < count; i++ {
			v := order.Uint32(data[offset+i*4 : offset+i*4+4])
			values[i] = float64(v)
		}
		return values

	case miINT16:
		count := numBytes / 2
		values := make([]float64, count)
		for i := 0; i < count; i++ {
			v := int16(order.Uint16(data[offset+i*2 : offset+i*2+2]))
			values[i] = float64(v)
		}
		return values

	case miUINT16:
		count := numBytes / 2
		values := make([]float64, count)
		for i := 0; i < count; i++ {
			v := order.Uint16(data[offset+i*2 : offset+i*2+2])
			values[i] = float64(v)
		}
		return values

	case miINT8:
		values := make([]float64, numBytes)
		for i := 0; i < numBytes; i++ {
			values[i] = float64(int8(data[offset+i]))
		}
		return values

	case miUINT8:
		values := make([]float64, numBytes)
		for i := 0; i < numBytes; i++ {
			values[i] = float64(data[offset+i])
		}
		return values
	}

	return nil
}
