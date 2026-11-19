package api

import (
	"errors"
	"net/http"

	"example.internal/jobq/internal/store"
)

// writeError writes a plain text error (contract v1).
func writeError(w http.ResponseWriter, status int, message string) {
	http.Error(w, message, status)
}

// writeStoreError maps an error of the store to an HTTP status.
func writeStoreError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, store.ErrNotFound):
		writeError(w, http.StatusNotFound, err.Error())
	case errors.Is(err, store.ErrQueueFull):
		writeError(w, http.StatusTooManyRequests, err.Error())
	case errors.Is(err, store.ErrNotQueued):
		writeError(w, http.StatusConflict, err.Error())
	default:
		writeError(w, http.StatusInternalServerError, "internal error")
	}
}
