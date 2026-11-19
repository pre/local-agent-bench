package policy

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
)

// Default is the policy when no policy file is given.
var Default = Policy{
	Exclude:               "role=control",
	MaxBatchSize:          4,
	MaxUnavailablePerRack: 1,
}

// Load reads a policy from a JSON file. Unknown keys are errors. Values
// that the file does not set keep the values of Default.
func Load(path string) (*Policy, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	p := Default
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&p); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	if err := p.Check(); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	return &p, nil
}
