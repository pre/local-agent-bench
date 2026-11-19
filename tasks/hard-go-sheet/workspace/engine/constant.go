package engine

import (
	"math"
	"strconv"
	"strings"

	"example.com/sheet/value"
)

// parseConstant reads an input that is not a formula: a number, TRUE or
// FALSE (not case sensitive), or else a text. A leading apostrophe makes the
// rest a text: "'12" is the text "12".
func parseConstant(input string) value.Value {
	if strings.HasPrefix(input, "'") {
		return value.Text(input[1:])
	}
	trimmed := strings.TrimSpace(input)
	if f, err := strconv.ParseFloat(trimmed, 64); err == nil && !math.IsInf(f, 0) && !math.IsNaN(f) && !strings.ContainsAny(trimmed, "xXpP_") {
		return value.Number(f)
	}
	switch strings.ToUpper(trimmed) {
	case "TRUE":
		return value.Boolean(true)
	case "FALSE":
		return value.Boolean(false)
	}
	return value.Text(input)
}
