// Package policy holds the rules for a rolling upgrade.
package policy

import (
	"fmt"

	"example.com/rollout/internal/inventory"
)

// Canary selects the nodes that are upgraded first, in a batch of their own.
type Canary struct {
	// Selector selects the nodes that can be canaries.
	Selector string `json:"selector"`
	// Count is the number of canaries. 0 means no canary batch.
	Count int `json:"count"`
}

// Policy holds the rules for a rolling upgrade.
type Policy struct {
	// Selector selects the nodes to upgrade. Empty selects all nodes.
	Selector string `json:"selector"`
	// Exclude selects nodes that are never upgraded, for example the
	// control plane. Empty excludes no node.
	Exclude string `json:"exclude"`
	// Canary is the canary batch.
	Canary Canary `json:"canary"`
	// MaxBatchSize is the largest number of nodes in one batch.
	MaxBatchSize int `json:"maxBatchSize"`
	// MaxUnavailablePerRack is the largest number of nodes of one rack in
	// one batch.
	MaxUnavailablePerRack int `json:"maxUnavailablePerRack"`
}

// Selectors holds the parsed selectors of a policy.
type Selectors struct {
	Select  inventory.Selector
	Exclude inventory.Selector
	Canary  inventory.Selector
}

// Check returns an error if a value of the policy is not valid.
func (p *Policy) Check() error {
	switch {
	case p.MaxBatchSize < 1:
		return fmt.Errorf("maxBatchSize must be 1 or more, not %d", p.MaxBatchSize)
	case p.MaxUnavailablePerRack < 1:
		return fmt.Errorf("maxUnavailablePerRack must be 1 or more, not %d", p.MaxUnavailablePerRack)
	case p.Canary.Count < 0:
		return fmt.Errorf("canary.count must not be negative")
	case p.Canary.Count > p.MaxBatchSize:
		return fmt.Errorf("canary.count %d is more than maxBatchSize %d", p.Canary.Count, p.MaxBatchSize)
	}
	_, err := p.Parse()
	return err
}

// Parse parses the selectors of the policy.
func (p *Policy) Parse() (Selectors, error) {
	var s Selectors
	var err error
	if s.Select, err = inventory.ParseSelector(p.Selector); err != nil {
		return s, fmt.Errorf("selector: %w", err)
	}
	if s.Exclude, err = inventory.ParseSelector(p.Exclude); err != nil {
		return s, fmt.Errorf("exclude: %w", err)
	}
	if s.Canary, err = inventory.ParseSelector(p.Canary.Selector); err != nil {
		return s, fmt.Errorf("canary.selector: %w", err)
	}
	return s, nil
}
