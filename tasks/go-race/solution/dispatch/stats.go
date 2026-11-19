package dispatch

import "time"

// Stats holds the counters of a Dispatcher.
type Stats struct {
	// Submitted is the number of jobs that Submit accepted.
	Submitted int
	// Succeeded is the number of jobs whose last attempt returned nil.
	Succeeded int
	// Failed is the number of jobs that failed in all attempts.
	Failed int
	// Retried is the number of attempts after the first one, over all jobs.
	Retried int
	// PerNode holds the counters for each node name of the jobs.
	PerNode map[string]*NodeStats
}

// NodeStats holds the counters of the jobs of one node.
type NodeStats struct {
	Submitted int
	Succeeded int
	Failed    int
	Retried   int
	// Busy is the sum of the run time of all attempts on the node.
	Busy time.Duration
}

// InFlight returns the number of jobs that are accepted but not finished.
func (s Stats) InFlight() int {
	return s.Submitted - s.Succeeded - s.Failed
}

func (s *Stats) node(name string) *NodeStats {
	ns, ok := s.PerNode[name]
	if !ok {
		ns = &NodeStats{}
		s.PerNode[name] = ns
	}
	return ns
}

func (s *Stats) recordSubmit(node string) {
	s.Submitted++
	s.node(node).Submitted++
}

func (s *Stats) recordAttempt(node string, elapsed time.Duration) {
	s.node(node).Busy += elapsed
}

func (s *Stats) recordResult(node string, ok bool) {
	ns := s.node(node)
	if ok {
		s.Succeeded++
		ns.Succeeded++
	} else {
		s.Failed++
		ns.Failed++
	}
}

func (s *Stats) recordRetry(node string) {
	s.Retried++
	s.node(node).Retried++
}

// clone returns a copy of s for callers that do not hold the lock.
func (s *Stats) clone() Stats {
	c := *s
	c.PerNode = make(map[string]*NodeStats, len(s.PerNode))
	for name, ns := range s.PerNode {
		nsCopy := *ns
		c.PerNode[name] = &nsCopy
	}
	return c
}
