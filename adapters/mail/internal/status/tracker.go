package status

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"time"

	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/config"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/models"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/queue"
)

// Tracker coordinates message status queries and outbound webhook event forwarding.
type Tracker struct {
	cfg        *config.Config
	q          *queue.BoltQueue
	httpClient *http.Client
	logger     *slog.Logger
}

// NewTracker creates a new Tracker instance.
func NewTracker(cfg *config.Config, q *queue.BoltQueue, logger *slog.Logger) *Tracker {
	timeout := cfg.StatusWebhookTimeout
	if timeout <= 0 {
		timeout = 10 * time.Second
	}

	return &Tracker{
		cfg: cfg,
		q:   q,
		httpClient: &http.Client{
			Timeout: timeout,
		},
		logger: logger,
	}
}

// GetStatus returns the current status and metadata of a message.
func (t *Tracker) GetStatus(ctx context.Context, id string) (*models.StatusResponse, error) {
	mail, err := t.q.Get(ctx, id)
	if err != nil {
		return nil, err
	}

	return &models.StatusResponse{
		ID:            mail.ID,
		State:         mail.State,
		CorrelationID: mail.CorrelationID,
		Attempts:      mail.Attempts,
		MaxAttempts:   mail.MaxAttempts,
		LastError:     mail.LastError,
		CreatedAt:     mail.CreatedAt,
		UpdatedAt:     mail.UpdatedAt,
		SentAt:        mail.SentAt,
		Metadata:      mail.Request.Metadata,
		Meta:          mail.Request.Meta,
		CustomData:    mail.Request.CustomData,
	}, nil
}

// Dispatch satisfies queue.EventDispatcherInterface. It forwards webhook events when configured.
func (t *Tracker) Dispatch(ctx context.Context, event models.StatusEvent) {
	if t.cfg.StatusWebhookURL != "" {
		go func(evt models.StatusEvent) {
			_ = t.forwardWebhookWithRetry(context.Background(), evt)
		}(event)
	}
}

func (t *Tracker) forwardWebhookWithRetry(ctx context.Context, event models.StatusEvent) error {
	payloadBytes, err := json.Marshal(event)
	if err != nil {
		t.logger.Error("failed marshaling status event for webhook", "error", err)
		return err
	}

	var lastErr error
	for attempt := 1; attempt <= 3; attempt++ {
		req, err := http.NewRequestWithContext(ctx, http.MethodPost, t.cfg.StatusWebhookURL, bytes.NewReader(payloadBytes))
		if err != nil {
			return err
		}

		req.Header.Set("Content-Type", "application/json")
		if event.CorrelationID != "" {
			req.Header.Set("X-Correlation-ID", event.CorrelationID)
		}

		// Calculate HMAC-SHA256 signature if secret is configured
		if t.cfg.StatusWebhookSecret != "" {
			mac := hmac.New(sha256.New, []byte(t.cfg.StatusWebhookSecret))
			mac.Write(payloadBytes)
			sig := hex.EncodeToString(mac.Sum(nil))
			req.Header.Set("X-VibeCore-Signature", sig)
		}

		resp, err := t.httpClient.Do(req)
		if err == nil {
			resp.Body.Close()
			if resp.StatusCode >= 200 && resp.StatusCode < 300 {
				t.logger.Debug("webhook forwarded successfully", "url", t.cfg.StatusWebhookURL, "event", event.EventType)
				return nil
			}
			lastErr = fmt.Errorf("webhook responded with non-2xx status: %d", resp.StatusCode)
		} else {
			lastErr = err
		}

		time.Sleep(time.Duration(attempt*100) * time.Millisecond)
	}

	t.logger.Warn("status webhook forward failed after retries", "url", t.cfg.StatusWebhookURL, "error", lastErr)
	return lastErr
}
