package inventory

// Health is the result of the last health check of a node.
type Health string

const (
	HealthOK       Health = "ok"
	HealthDegraded Health = "degraded"
	HealthFailed   Health = "failed"
)

// Node is one node of the cluster.
type Node struct {
	Name   string            `json:"name"`
	Rack   string            `json:"rack"`
	Labels map[string]string `json:"labels,omitempty"`
	Health Health            `json:"health,omitempty"`
}

// Label returns the value of the label key and whether the node has it.
func (n Node) Label(key string) (string, bool) {
	v, ok := n.Labels[key]
	return v, ok
}
