package api

import (
	"log/slog"
	"net/http"

	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/config"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/webhooks"
)

// NewRouter sets up HTTP routes with middleware.
func NewRouter(cfg *config.Config, api *API, webhookHandler *webhooks.Handler, logger *slog.Logger) http.Handler {
	mux := http.NewServeMux()

	// Mail transmission and queries
	mux.HandleFunc("POST /api/v1/mail/send", api.HandleSendMail)
	mux.HandleFunc("GET /api/v1/mail/status/{id}", api.HandleGetStatus)

	// Templates
	mux.HandleFunc("GET /api/v1/mail/templates", api.HandleListTemplates)
	mux.HandleFunc("POST /api/v1/mail/templates", api.HandleRegisterTemplate)

	// Inbound Webhooks
	mux.HandleFunc("POST /api/v1/mail/webhooks/resend", webhookHandler.HandleResend)
	mux.HandleFunc("POST /api/v1/mail/webhooks/brevo", webhookHandler.HandleBrevo)
	mux.HandleFunc("POST /api/v1/mail/webhooks/sendgrid", webhookHandler.HandleSendGrid)
	mux.HandleFunc("POST /api/v1/mail/webhooks/generic", webhookHandler.HandleGeneric)

	// Health and observability
	mux.HandleFunc("GET /health", api.HandleHealth)
	mux.HandleFunc("GET /ready", api.HandleReady)
	mux.HandleFunc("GET /metrics", api.HandleMetrics)

	// Chain middlewares
	handler := AuthMiddleware(cfg.APIKey, mux)
	handler = CorrelationIDMiddleware(handler)
	handler = LoggingMiddleware(logger, handler)
	handler = RecoveryMiddleware(logger, handler)

	return handler
}
