package api

import (
	"context"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
)

type correlationIDKeyType string

const CorrelationIDKey correlationIDKeyType = "correlation_id"

// CorrelationIDMiddleware ensures every request has an X-Correlation-ID.
func CorrelationIDMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		corrID := r.Header.Get("X-Correlation-ID")
		if corrID == "" {
			corrID = "corr_" + uuid.New().String()
		}

		ctx := context.WithValue(r.Context(), CorrelationIDKey, corrID)
		w.Header().Set("X-Correlation-ID", corrID)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// AuthMiddleware validates the X-API-Key header against the configured API key.
func AuthMiddleware(apiKey string, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Public endpoints that bypass API key check:
		path := r.URL.Path
		if path == "/health" || path == "/ready" || path == "/metrics" || strings.HasPrefix(path, "/api/v1/mail/webhooks/") {
			next.ServeHTTP(w, r)
			return
		}

		if apiKey != "" {
			reqKey := r.Header.Get("X-API-Key")
			if reqKey == "" {
				// Also allow Bearer token
				authHeader := r.Header.Get("Authorization")
				if strings.HasPrefix(authHeader, "Bearer ") {
					reqKey = strings.TrimPrefix(authHeader, "Bearer ")
				}
			}

			if reqKey != apiKey {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusUnauthorized)
				_, _ = w.Write([]byte(`{"error":"UNAUTHORIZED","message":"invalid or missing X-API-Key header"}`))
				return
			}
		}

		next.ServeHTTP(w, r)
	})
}

// LoggingMiddleware logs request details and duration using structured logging.
func LoggingMiddleware(logger *slog.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rw := &responseWriter{ResponseWriter: w, statusCode: http.StatusOK}

		next.ServeHTTP(rw, r)

		corrID, _ := r.Context().Value(CorrelationIDKey).(string)
		logger.Info("http request",
			"method", r.Method,
			"path", r.URL.Path,
			"status", rw.statusCode,
			"duration_ms", time.Since(start).Milliseconds(),
			"correlation_id", corrID,
			"remote_addr", r.RemoteAddr,
		)
	})
}

// RecoveryMiddleware catches panics and returns a structured 500 error.
func RecoveryMiddleware(logger *slog.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if rec := recover(); rec != nil {
				corrID, _ := r.Context().Value(CorrelationIDKey).(string)
				logger.Error("panic recovered in http handler",
					"panic", rec,
					"path", r.URL.Path,
					"correlation_id", corrID,
				)
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusInternalServerError)
				_, _ = w.Write([]byte(`{"error":"INTERNAL_ERROR","message":"an unexpected error occurred"}`))
			}
		}()
		next.ServeHTTP(w, r)
	})
}

type responseWriter struct {
	http.ResponseWriter
	statusCode int
}

func (rw *responseWriter) WriteHeader(code int) {
	rw.statusCode = code
	rw.ResponseWriter.WriteHeader(code)
}
