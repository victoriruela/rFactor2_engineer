package parsers

import "errors"

var (
	ErrEmptySetup    = errors.New("svm file is empty or contains no valid setup sections")
	ErrNoChannels    = errors.New("no valid channels found in telemetry file")
	ErrNoHeaders     = errors.New("no headers found in CSV file")
	ErrNoData        = errors.New("telemetry file contains no valid data")
	ErrUnsupportedFmt = errors.New("unsupported telemetry file format")
)
