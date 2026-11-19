package store

import (
	"errors"
	"testing"
)

func TestCreateGetList(t *testing.T) {
	s := New(10)
	a, err := s.Create([]string{"echo", "a"}, 30)
	if err != nil {
		t.Fatal(err)
	}
	b, err := s.Create([]string{"echo", "b"}, 60)
	if err != nil {
		t.Fatal(err)
	}
	if a.ID == b.ID {
		t.Fatalf("same ID %v", a.ID)
	}
	got, err := s.Get(b.ID)
	if err != nil {
		t.Fatal(err)
	}
	if got.TimeoutSeconds != 60 || got.State != Queued {
		t.Fatalf("got %+v", got)
	}
	list := s.List()
	if len(list) != 2 || list[0].ID != a.ID || list[1].ID != b.ID {
		t.Fatalf("list %+v", list)
	}
}

func TestQueueLimit(t *testing.T) {
	s := New(1)
	a, err := s.Create([]string{"true"}, 1)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := s.Create([]string{"true"}, 1); !errors.Is(err, ErrQueueFull) {
		t.Fatalf("got %v, want ErrQueueFull", err)
	}
	if _, err := s.Cancel(a.ID); err != nil {
		t.Fatal(err)
	}
	if _, err := s.Create([]string{"true"}, 1); err != nil {
		t.Fatalf("after cancel: %v", err)
	}
}

func TestCancel(t *testing.T) {
	s := New(10)
	a, _ := s.Create([]string{"true"}, 1)
	job, err := s.Cancel(a.ID)
	if err != nil || job.State != Cancelled {
		t.Fatalf("got %+v, %v", job, err)
	}
	if _, err := s.Cancel(a.ID); !errors.Is(err, ErrNotQueued) {
		t.Fatalf("second cancel: %v", err)
	}
	if _, err := s.Cancel(999); !errors.Is(err, ErrNotFound) {
		t.Fatalf("unknown job: %v", err)
	}
}
