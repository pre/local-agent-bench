package health

import (
	"reflect"
	"testing"

	"example.com/rollout/internal/inventory"
)

func TestSplit(t *testing.T) {
	nodes := []inventory.Node{
		{Name: "a", Health: inventory.HealthOK},
		{Name: "b", Health: inventory.HealthFailed},
		{Name: "c", Health: inventory.HealthDegraded},
	}
	ok, skipped := Split(nodes)
	if got := inventory.Names(ok); !reflect.DeepEqual(got, []string{"a", "c"}) {
		t.Errorf("ok = %v", got)
	}
	if got := inventory.Names(skipped); !reflect.DeepEqual(got, []string{"b"}) {
		t.Errorf("skipped = %v", got)
	}
}
