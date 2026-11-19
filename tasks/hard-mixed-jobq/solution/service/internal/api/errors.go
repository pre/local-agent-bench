package api

import (
	"errors"
	"net/http"

	"example.internal/jobq/internal/store"
)

// Error codes of contract version 2, rule 11.
const (
	codeInvalidArgument    = "invalid_argument"
	codeUnauthenticated    = "unauthenticated"
	codeNotFound           = "not_found"
	codeFailedPrecondition = "failed_precondition"
	codeResourceExhausted  = "resource_exhausted"
	codeInternal           = "internal"
)

var statusOf = map[string]int{
	codeInvalidArgument:    http.StatusBadRequest,
	codeUnauthenticated:    http.StatusUnauthorized,
	codeNotFound:           http.StatusNotFound,
	codeFailedPrecondition: http.StatusConflict,
	codeResourceExhausted:  http.StatusTooManyRequests,
	codeInternal:           http.StatusInternalServerError,
}

type errorBody struct {
	Error errorDetail `json:"error"`
}

type errorDetail struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

// writeError writes the JSON error body of rule 11.
func writeError(w http.ResponseWriter, code, message string) {
	writeJSON(w, statusOf[code], errorBody{errorDetail{Code: code, Message: message}})
}

// writeStoreError maps an error of the store to an error code.
func writeStoreError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, store.ErrNotFound):
		writeError(w, codeNotFound, err.Error())
	case errors.Is(err, store.ErrQueueFull):
		writeError(w, codeResourceExhausted, err.Error())
	case errors.Is(err, store.ErrNotQueued):
		writeError(w, codeFailedPrecondition, err.Error())
	default:
		writeError(w, codeInternal, "internal error")
	}
}
