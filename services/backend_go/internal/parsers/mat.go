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
	miINT8       = 1
	miUINT8      = 2
	miINT16      = 3
	miUINT16     = 4
	miINT32      = 5
	miUINT32     = 6
	miSINGLE     = 7
	miDOUBLE     = 9
	miINT64      = 12
	miUINT64     = 13
	miMATRIX     = 14
	miCOMPRESSED = 15
	miUTF8       = 16

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
//
// Memory strategy: the file is read element-by-element (streaming) so that
// the raw bytes of each element are eligible for GC as soon as parsing
// finishes. Peak RAM ≈ largest_compressed_element × 3 + accumulated_channels,
// instead of whole_file + decompressed_data simultaneously.
func ParseMATFile(path string) (*domain.TelemetryData, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("reading mat file: %w", err)
	}
	defer f.Close()

	// Read 128-byte header.
	// Bytes 124-125: version (0x0100)
	// Bytes 126-127: endian indicator ("IM" = little-endian)
	header := make([]byte, 128)
	if _, err := io.ReadFull(f, header); err != nil {
		return nil, ErrNoData
	}

	endianIndicator := string(header[126:128])
	var order binary.ByteOrder
	if endianIndicator == "IM" {
		order = binary.LittleEndian
	} else {
		order = binary.BigEndian
	}
	header = nil // no longer needed

	channels := make(map[string][]float64)
	tagBuf := make([]byte, 8) // reused across iterations

	for {
		// Read 8-byte tag.
		if _, err := io.ReadFull(f, tagBuf); err != nil {
			break // EOF or truncated file
		}

		tag := readTag(tagBuf, order)
		if tag.dataType == 0 || tag.numBytes == 0 {
			break
		}

		numBytes := int(tag.numBytes)
		// MATLAB Level 5 pads each element to an 8-byte boundary in the file.
		paddedSize := numBytes
		if paddedSize%8 != 0 {
			paddedSize += 8 - paddedSize%8
		}

		// Read the element (including padding) in one allocation.
		// Using a single allocation avoids a second Read call for padding bytes.
		buf := make([]byte, paddedSize)
		if _, err := io.ReadFull(f, buf); err != nil {
			break
		}
		elem := buf[:numBytes] // logical extent, padding is ignored

		switch tag.dataType {
		case miCOMPRESSED:
			decompressed, err := decompressZlib(elem)
			buf = nil  // raw compressed bytes no longer needed
			elem = nil // same backing array
			if err == nil {
				name, values := parseMatrixElement(decompressed, order)
				decompressed = nil // release decompressed bytes
				if name != "" && len(values) > 0 {
					channels[name] = values
				}
			}
		case miMATRIX:
			name, values := parseMatrixElement(elem, order)
			buf = nil
			elem = nil
			if name != "" && len(values) > 0 {
				channels[name] = values
			}
		default:
			buf = nil // skip and discard unknown top-level element types
		}
	}

	if len(channels) == 0 {
		return nil, ErrNoChannels
	}

	// Determine base length (use Session_Elapsed_Time if available).
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

	// Align channels to the base length.
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
	channels = nil // raw channel map no longer needed

	// Apply column renames for consistency.
	renameMap := map[string]string{
		"GPS_Latitude":            "GPS Latitude",
		"GPS_Longitude":           "GPS Longitude",
		"Throttle_Pos":            "Throttle",
		"Brake_Pos":               "Brake",
		"Steering_Wheel_Position": "Steering",
		"Engine_RPM":              "RPM",
		"Ground_Speed":            "Speed",
	}
	for old, new := range renameMap {
		if v, ok := aligned[old]; ok {
			aligned[new] = v
			delete(aligned, old)
		}
	}

	td := &domain.TelemetryData{Channels: aligned}
	detectSpecialColumns(td)

	// Apply gentle GPS smoothing: only rolling mean, no outlier removal.
	// rFactor2 GPS is synthetic (simulation), so there are no real GPS spikes to remove.
	// Outlier removal with 1.5*std would incorrectly clip legitimate track corners.
	for _, col := range []string{"GPS Latitude", "GPS Longitude"} {
		if gpsData, ok := td.Channels[col]; ok {
			td.Channels[col] = rollingMean(gpsData, 11)
		}
	}

	// Filter incomplete laps.
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
	flagsEnd := offset + int(tag.numBytes)
	if flagsEnd > len(data) {
		return "", nil
	}
	arrayClass := data[offset] & 0xFF
	offset = align8(flagsEnd)

	// Dimensions subelement
	if offset+8 > len(data) {
		return "", nil
	}
	elementCount, nextOffset, ok := parseDimensions(data, order, offset)
	if !ok {
		return "", nil
	}
	offset = nextOffset

	// Name subelement
	name, nextOffset, ok := parseNameElement(data, order, offset)
	if !ok || name == "" {
		return "", nil
	}
	offset = nextOffset

	var values []float64
	if arrayClass == mxSTRUCT_CLASS {
		if name == "Session_Elapsed_Time" {
			values = extractStructFieldValues(data[offset:], order, elementCount, "Time")
			if len(values) == 0 {
				values = extractStructFieldValues(data[offset:], order, elementCount, "Value")
			}
		} else {
			values = extractStructFieldValues(data[offset:], order, elementCount, "Value")
		}
	} else {
		values = extractNumericData(data[offset:], order)
	}

	return name, values
}

func align8(offset int) int {
	if offset%8 != 0 {
		offset += 8 - offset%8
	}
	return offset
}

func parseDimensions(data []byte, order binary.ByteOrder, offset int) (int, int, bool) {
	if offset+8 > len(data) {
		return 0, offset, false
	}

	tag := readTag(data[offset:], order)
	offset += 8
	end := offset + int(tag.numBytes)
	if end > len(data) {
		return 0, offset, false
	}

	count := 1
	for index := offset; index+4 <= end; index += 4 {
		dim := int(order.Uint32(data[index : index+4]))
		if dim > 0 {
			count *= dim
		}
	}
	if count == 0 {
		count = 1
	}

	return count, align8(end), true
}

func parseNameElement(data []byte, order binary.ByteOrder, offset int) (string, int, bool) {
	if offset+8 > len(data) {
		return "", offset, false
	}

	tag := readTag(data[offset:], order)
	rawDT := order.Uint32(data[offset : offset+4])

	// Small data element format.
	if rawDT>>16 != 0 {
		numBytes := int(rawDT >> 16)
		if offset+4+numBytes > len(data) {
			return "", offset, false
		}
		name := strings.TrimRight(string(data[offset+4:offset+4+numBytes]), "\x00")
		return name, offset + 8, true
	}

	offset += 8
	end := offset + int(tag.numBytes)
	if end > len(data) {
		return "", offset, false
	}

	name := strings.TrimRight(string(data[offset:end]), "\x00")
	return name, align8(end), true
}

func extractStructFieldValues(data []byte, order binary.ByteOrder, elementCount int, fieldName string) []float64 {
	offset := 0
	fieldNameLength, nextOffset, ok := parseFieldNameLength(data, order, offset)
	if !ok {
		return nil
	}
	offset = nextOffset

	fieldNames, nextOffset, ok := parseFieldNames(data, order, offset, fieldNameLength)
	if !ok || len(fieldNames) == 0 {
		return nil
	}
	offset = nextOffset

	if elementCount <= 0 {
		elementCount = 1
	}

	for elementIndex := 0; elementIndex < elementCount; elementIndex++ {
		for _, currentField := range fieldNames {
			if offset+8 > len(data) {
				return nil
			}

			tag := readTag(data[offset:], order)
			offset += 8
			end := offset + int(tag.numBytes)
			if end > len(data) {
				return nil
			}

			if currentField == fieldName && tag.dataType == miMATRIX {
				if values := parseUnnamedMatrix(data[offset:end], order); len(values) > 0 {
					return values
				}
			}

			offset = align8(end)
		}
	}

	return nil
}

func parseFieldNameLength(data []byte, order binary.ByteOrder, offset int) (int, int, bool) {
	if offset+8 > len(data) {
		return 0, offset, false
	}

	rawDT := order.Uint32(data[offset : offset+4])
	if rawDT>>16 != 0 {
		fieldNameLength := int(order.Uint32(data[offset+4 : offset+8]))
		if fieldNameLength <= 0 {
			return 0, offset, false
		}
		return fieldNameLength, offset + 8, true
	}

	tag := readTag(data[offset:], order)
	offset += 8
	end := offset + int(tag.numBytes)
	if end > len(data) || tag.numBytes < 4 {
		return 0, offset, false
	}

	fieldNameLength := int(order.Uint32(data[offset : offset+4]))
	if fieldNameLength <= 0 {
		return 0, offset, false
	}

	return fieldNameLength, end, true
}

func parseFieldNames(data []byte, order binary.ByteOrder, offset, fieldNameLength int) ([]string, int, bool) {
	if offset+8 > len(data) {
		return nil, offset, false
	}

	tag := readTag(data[offset:], order)
	offset += 8
	end := offset + int(tag.numBytes)
	if end > len(data) || fieldNameLength <= 0 {
		return nil, offset, false
	}

	rawNames := data[offset:end]
	fieldCount := len(rawNames) / fieldNameLength
	if fieldCount == 0 {
		return nil, offset, false
	}

	fieldNames := make([]string, 0, fieldCount)
	for index := 0; index < fieldCount; index++ {
		start := index * fieldNameLength
		name := strings.TrimRight(string(rawNames[start:start+fieldNameLength]), "\x00")
		fieldNames = append(fieldNames, name)
	}

	return fieldNames, align8(end), true
}

func parseUnnamedMatrix(data []byte, order binary.ByteOrder) []float64 {
	if len(data) < 16 {
		return nil
	}

	offset := 0
	tag := readTag(data[offset:], order)
	offset += 8
	if tag.numBytes < 8 {
		return nil
	}
	end := offset + int(tag.numBytes)
	if end > len(data) {
		return nil
	}
	arrayClass := data[offset] & 0xFF
	offset = align8(end)

	_, nextOffset, ok := parseDimensions(data, order, offset)
	if !ok {
		return nil
	}
	offset = nextOffset

	_, nextOffset, ok = parseNameElement(data, order, offset)
	if !ok {
		return nil
	}
	offset = nextOffset

	if arrayClass == mxSTRUCT_CLASS {
		return extractStructFieldValues(data[offset:], order, 1, "Value")
	}

	return extractNumericData(data[offset:], order)
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
