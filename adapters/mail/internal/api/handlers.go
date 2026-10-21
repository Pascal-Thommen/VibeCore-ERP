package api

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"runtime"
	"time"

	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/config"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/models"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/queue"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/status"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/template"
	"github.com/google/uuid"
)

// API holds references to all sub-services for request handling.
type API struct {
	cfg        *config.Config
	q          *queue.BoltQueue
	proc       *queue.Processor
	tracker    *status.Tracker
	tmplEngine *template.Engine
	logger     *slog.Logger
	startTime  time.Time
}

// NewAPI initializes the API service.
func NewAPI(
	cfg *config.Config,
	q *queue.BoltQueue,
	proc *queue.Processor,
	tracker *status.Tracker,
	tmplEngine *template.Engine,
	logger *slog.Logger,
) *API {
	return &API{
		cfg:        cfg,
		q:          q,
		proc:       proc,
		tracker:    tracker,
		tmplEngine: tmplEngine,
		logger:     logger,
		startTime:  time.Now(),
	}
}

func (a *API) writeJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(data)
}

func (a *API) writeError(w http.ResponseWriter, status int, code, message string) {
	a.writeJSON(w, status, map[string]string{
		"error":   code,
		"message": message,
	})
}

// HandleSendMail processes POST /api/v1/mail/send.
func (a *API) HandleSendMail(w http.ResponseWriter, r *http.Request) {
	corrID, _ := r.Context().Value(CorrelationIDKey).(string)
	idempotencyKey := r.Header.Get("Idempotency-Key")

	// If idempotency key provided, check if already recorded
	if idempotencyKey != "" {
		existing, err := a.q.GetByIdempotencyKey(r.Context(), idempotencyKey)
		if err == nil && existing != nil {
			a.logger.Info("idempotent request detected; returning existing status",
				"idempotency_key", idempotencyKey,
				"mail_id", existing.ID,
			)
			a.writeJSON(w, http.StatusOK, map[string]any{
				"id":              existing.ID,
				"state":           existing.State,
				"correlation_id":  existing.CorrelationID,
				"idempotency_key": idempotencyKey,
				"duplicate":       true,
			})
			return
		}
	}

	body, err := io.ReadAll(r.Body)
	if err != nil {
		a.writeError(w, http.StatusBadRequest, "BAD_REQUEST", "failed reading request body")
		return
	}

	var req models.SendMailRequest
	if err := json.Unmarshal(body, &req); err != nil {
		a.writeError(w, http.StatusBadRequest, "INVALID_JSON", fmt.Sprintf("invalid json payload: %v", err))
		return
	}

	if err := req.Validate(a.cfg.MaxAttachmentSizeBytes); err != nil {
		a.writeError(w, http.StatusUnprocessableEntity, "VALIDATION_FAILED", err.Error())
		return
	}

	mailID := "mail_" + uuid.New().String()
	queuedMail := &models.QueuedMail{
		ID:             mailID,
		IdempotencyKey: idempotencyKey,
		CorrelationID:  corrID,
		Request:        req,
	}

	if err := a.proc.EnqueueRequest(r.Context(), queuedMail); err != nil {
		if errors.Is(err, queue.ErrDuplicateIdempotency) {
			if existing, getErr := a.q.GetByIdempotencyKey(r.Context(), idempotencyKey); getErr == nil && existing != nil {
				a.writeJSON(w, http.StatusOK, map[string]any{
					"id":              existing.ID,
					"state":           existing.State,
					"correlation_id":  existing.CorrelationID,
					"idempotency_key": idempotencyKey,
					"duplicate":       true,
				})
				return
			}
		}
		a.logger.Error("failed enqueuing mail item", "mail_id", mailID, "error", err)
		a.writeError(w, http.StatusInternalServerError, "QUEUE_ERROR", fmt.Sprintf("failed to queue mail: %v", err))
		return
	}

	a.writeJSON(w, http.StatusAccepted, map[string]any{
		"id":             mailID,
		"state":          models.MailStateQueued,
		"correlation_id": corrID,
		"status_url":     fmt.Sprintf("/api/v1/mail/status/%s", mailID),
	})
}

// HandleGetStatus processes GET /api/v1/mail/status/{id}.
func (a *API) HandleGetStatus(w http.ResponseWriter, r *http.Request) {
	mailID := r.PathValue("id")
	if mailID == "" {
		a.writeError(w, http.StatusBadRequest, "MISSING_ID", "mail id path parameter is required")
		return
	}

	resp, err := a.tracker.GetStatus(r.Context(), mailID)
	if err != nil {
		if errors.Is(err, queue.ErrNotFound) {
			a.writeError(w, http.StatusNotFound, "NOT_FOUND", fmt.Sprintf("email '%s' not found", mailID))
			return
		}
		a.writeError(w, http.StatusInternalServerError, "DB_ERROR", err.Error())
		return
	}

	a.writeJSON(w, http.StatusOK, resp)
}

// HandleListTemplates processes GET /api/v1/mail/templates.
func (a *API) HandleListTemplates(w http.ResponseWriter, r *http.Request) {
	templates := a.tmplEngine.List()
	a.writeJSON(w, http.StatusOK, map[string]any{
		"templates": templates,
		"count":     len(templates),
	})
}

// HandleRegisterTemplate processes POST /api/v1/mail/templates.
func (a *API) HandleRegisterTemplate(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Name string `json:"name"`
		HTML string `json:"html"`
		Text string `json:"text"`
	}

	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		a.writeError(w, http.StatusBadRequest, "INVALID_JSON", err.Error())
		return
	}

	if body.Name == "" || (body.HTML == "" && body.Text == "") {
		a.writeError(w, http.StatusUnprocessableEntity, "VALIDATION_FAILED", "name and at least one template body (html or text) required")
		return
	}

	if err := a.tmplEngine.Register(body.Name, body.HTML, body.Text); err != nil {
		a.writeError(w, http.StatusBadRequest, "TEMPLATE_PARSE_ERROR", err.Error())
		return
	}

	a.writeJSON(w, http.StatusCreated, map[string]string{
		"name":    body.Name,
		"status":  "registered",
		"message": "template compiled and ready for use",
	})
}

// HandleHealth processes GET /health (Liveness).
func (a *API) HandleHealth(w http.ResponseWriter, r *http.Request) {
	a.writeJSON(w, http.StatusOK, map[string]any{
		"status":    "healthy",
		"service":   "vibecore-mail-adapter",
		"timestamp": time.Now().UTC(),
		"uptime":    time.Since(a.startTime).String(),
	})
}

// HandleReady processes GET /ready (Readiness).
func (a *API) HandleReady(w http.ResponseWriter, r *http.Request) {
	// Verify persistent queue database is accessible
	_, err := a.q.Get(r.Context(), "non_existent_ping")
	if err != nil && !errors.Is(err, queue.ErrNotFound) {
		a.writeJSON(w, http.StatusServiceUnavailable, map[string]any{
			"status": "degraded",
			"error":  "queue database error: " + err.Error(),
		})
		return
	}

	a.writeJSON(w, http.StatusOK, map[string]any{
		"status":    "ready",
		"service":   "vibecore-mail-adapter",
		"database":  "connected",
		"smtp_host": a.cfg.SMTPHost,
		"timestamp": time.Now().UTC(),
	})
}

// HandleMetrics processes GET /metrics (Runtime observability & resource consumption).
func (a *API) HandleMetrics(w http.ResponseWriter, r *http.Request) {
	var mem runtime.MemStats
	runtime.ReadMemStats(&mem)

	pending, _ := a.q.GetPending(r.Context(), 100)

	a.writeJSON(w, http.StatusOK, map[string]any{
		"service":            "vibecore-mail-adapter",
		"uptime_seconds":     time.Since(a.startTime).Seconds(),
		"goroutines":         runtime.NumGoroutine(),
		"pending_queue_jobs": len(pending),
		"memory": map[string]any{
			"alloc_bytes":       mem.Alloc,
			"alloc_mb":          float64(mem.Alloc) / (1024 * 1024),
			"total_alloc_mb":    float64(mem.TotalAlloc) / (1024 * 1024),
			"sys_mb":            float64(mem.Sys) / (1024 * 1024),
			"heap_inuse_mb":     float64(mem.HeapInuse) / (1024 * 1024),
			"under_20mb_target": float64(mem.Alloc)/(1024*1024) < 20.0,
		},
	})
}
