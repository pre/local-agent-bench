package store

import (
	"errors"
	"testing"
	"time"
)

func TestCreateGetPage(t *testing.T) {
	s := New(10)
	var ids []string
	for i := 0; i < 5; i++ {
		job, err := s.Create([]string{"true"}, time.Second)
		if err != nil {
			t.Fatal(err)
		}
		ids = append(ids, job.ID)
	}
	if ids[0] == ids[1] {
		t.Fatalf("same ID %v", ids[0])
	}
	got, err := s.Get(ids[3])
	if err != nil || got.Seq != 4 || got.Timeout != time.Second {
		t.Fatalf("got %+v, %v", got, err)
	}
	page, more := s.Page(0, 2)
	if len(page) != 2 || !more || page[0].ID != ids[0] {
		t.Fatalf("page 1: %+v %v", page, more)
	}
	page, more = s.Page(2, 3)
	if len(page) != 3 || more || page[2].ID != ids[4] {
		t.Fatalf("page 2: %+v %v", page, more)
	}
}

func TestQueueLimit(t *testing.T) {
	s := New(1)
	a, err := s.Create([]string{"true"}, time.Second)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := s.Create([]string{"true"}, time.Second); !errors.Is(err, ErrQueueFull) {
		t.Fatalf("got %v, want ErrQueueFull", err)
	}
	if _, err := s.Cancel(a.ID); err != nil {
		t.Fatal(err)
	}
	if _, err := s.Create([]string{"true"}, time.Second); err != nil {
		t.Fatalf("after cancel: %v", err)
	}
}

func TestCancel(t *testing.T) {
	s := New(10)
	a, _ := s.Create([]string{"true"}, time.Second)
	job, err := s.Cancel(a.ID)
	if err != nil || job.State != Cancelled {
		t.Fatalf("got %+v, %v", job, err)
	}
	if _, err := s.Cancel(a.ID); !errors.Is(err, ErrNotQueued) {
		t.Fatalf("second cancel: %v", err)
	}
	if _, err := s.Cancel("j-missing"); !errors.Is(err, ErrNotFound) {
		t.Fatalf("unknown job: %v", err)
	}
}
