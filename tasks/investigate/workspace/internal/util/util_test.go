package util

import (
	"reflect"
	"testing"
)

func TestFilter(t *testing.T) {
	got := Filter([]int{1, 2, 3, 4, 5, 6}, func(v int) bool { return v%2 == 0 })
	if want := []int{2, 4, 6}; !reflect.DeepEqual(got, want) {
		t.Errorf("got %v, want %v", got, want)
	}
	if got := Filter([]int{1, 3}, func(v int) bool { return v%2 == 0 }); len(got) != 0 {
		t.Errorf("got %v, want empty", got)
	}
}

func TestChunk(t *testing.T) {
	got := Chunk([]int{1, 2, 3, 4, 5}, 2)
	want := [][]int{{1, 2}, {3, 4}, {5}}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("got %v, want %v", got, want)
	}
	if got := Chunk([]int{}, 3); len(got) != 0 {
		t.Errorf("empty: got %v", got)
	}
}

func TestStringSet(t *testing.T) {
	s := NewStringSet("b", "a")
	s.Add("c")
	if !s.Has("a") || s.Has("x") {
		t.Error("Has")
	}
	if got := s.Sorted(); !reflect.DeepEqual(got, []string{"a", "b", "c"}) {
		t.Errorf("Sorted = %v", got)
	}
}
