package queue

import (
	"context"
	"fmt"
	"log/slog"
	"math"
	"sync"
	"time"

	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/config"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/models"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/template"
)

// SenderInterface abstracts email delivery.
type SenderInterface interface {
	Send(ctx context.Context, req *models.SendMailRequest) error
}

// EventDispatcherInterface abstracts event notifications.
type EventDispatcherInterface interface {
	Dispatch(ctx context.Context, event models.StatusEvent)
}

// Processor manages background queue workers and retry scheduling.
type Processor struct {
	cfg        *config.Config
	q          *BoltQueue
	sender     SenderInterface
	tmplEngine *template.Engine
	dispatcher EventDispatcherInterface
	logger     *slog.Logger

	ctx    context.Context
	cancel context.CancelFunc
	wg     sync.WaitGroup
}

// NewProcessor creates a new queue processor instance.
func NewProcessor(
	cfg *config.Config,
	q *BoltQueue,
	sender SenderInterface,
	tmplEngine *template.Engine,
	dispatcher EventDispatcherInterface,
	logger *slog.Logger,
) *Processor {
	ctx, cancel := context.WithCancel(context.Background())
	return &Processor{
		cfg:        cfg,
		q:          q,
		sender:     sender,
		tmplEngine: tmplEngine,
		dispatcher: dispatcher,
		logger:     logger,
		ctx:        ctx,
		cancel:     cancel,
	}
}

// Start launches the background worker pool and crash recovery.
func (p *Processor) Start() error {
	// First: recover any inflight jobs from previous runs
	recovered, err := p.q.RecoverInflight(p.ctx)
	if err != nil {
		p.logger.Error("failed recovering inflight mail items", "error", err)
	} else if recovered > 0 {
		p.logger.Info("recovered inflight mail items after restart", "count", recovered)
	}

	p.logger.Info("starting mail queue processor workers",
		"concurrency", p.cfg.QueueWorkerConcurrency,
		"poll_interval", p.cfg.QueuePollInterval,
	)

	for i := 0; i < p.cfg.QueueWorkerConcurrency; i++ {
		p.wg.Add(1)
		go p.workerLoop(i)
	}

	return nil
}

// Stop gracefully shuts down all queue workers.
func (p *Processor) Stop() {
	p.cancel()
	p.wg.Wait()
	p.logger.Info("mail queue processor stopped")
}

// EnqueueRequest validates, enriches with template if needed, and queues the mail item.
func (p *Processor) EnqueueRequest(ctx context.Context, item *models.QueuedMail) error {
	// If a template is requested, render it now to validate variables early
	if item.Request.Template != "" && p.tmplEngine != nil {
		htmlBody, textBody, err := p.tmplEngine.Render(item.Request.Template, item.Request.TemplateData)
		if err != nil {
			return fmt.Errorf("template rendering error for '%s': %w", item.Request.Template, err)
		}
		item.Request.HTMLBody = htmlBody
		item.Request.TextBody = textBody
	}

	item.State = models.MailStateQueued
	item.CreatedAt = time.Now()
	item.UpdatedAt = time.Now()
	item.MaxAttempts = p.cfg.QueueMaxRetries

	if err := p.q.Enqueue(ctx, item); err != nil {
		return err
	}

	if p.dispatcher != nil {
		p.dispatcher.Dispatch(ctx, models.StatusEvent{
			EventID:       fmt.Sprintf("evt_%d", time.Now().UnixNano()),
			EventType:     "mail.queued",
			Timestamp:     time.Now(),
			MessageID:     item.ID,
			CorrelationID: item.CorrelationID,
			State:         models.MailStateQueued,
			Payload:       item,
		})
	}

	return nil
}

func (p *Processor) workerLoop(workerID int) {
	defer p.wg.Done()

	ticker := time.NewTicker(p.cfg.QueuePollInterval)
	defer ticker.Stop()

	for {
		select {
		case <-p.ctx.Done():
			return
		case <-ticker.C:
			p.processNextBatch()
		}
	}
}

func (p *Processor) processNextBatch() {
	items, err := p.q.ClaimPending(p.ctx, 5)
	if err != nil {
		p.logger.Error("failed claiming pending mails from queue", "error", err)
		return
	}

	for _, item := range items {
		select {
		case <-p.ctx.Done():
			return
		default:
			p.processItem(item)
		}
	}
}

func (p *Processor) processItem(item *models.QueuedMail) {
	p.logger.Info("attempting to deliver email",
		"mail_id", item.ID,
		"correlation_id", item.CorrelationID,
		"attempt", item.Attempts,
		"max_attempts", item.MaxAttempts,
		"recipients", item.Request.To,
	)

	sendTimeout := p.cfg.SMTPSendTimeout
	if sendTimeout <= 0 {
		sendTimeout = 30 * time.Second
	}
	sendCtx, sendCancel := context.WithTimeout(p.ctx, sendTimeout)
	defer sendCancel()

	err := p.sender.Send(sendCtx, &item.Request)
	now := time.Now()

	if err == nil {
		// Delivery succeeded
		item.State = models.MailStateSent
		item.SentAt = &now
		item.LastError = ""
		item.UpdatedAt = now

		if err := p.q.Update(p.ctx, item); err != nil {
			p.logger.Error("failed updating sent status", "mail_id", item.ID, "error", err)
		}

		p.logger.Info("email delivered successfully",
			"mail_id", item.ID,
			"correlation_id", item.CorrelationID,
			"attempts", item.Attempts,
		)

		if p.dispatcher != nil {
			p.dispatcher.Dispatch(p.ctx, models.StatusEvent{
				EventID:       fmt.Sprintf("evt_%d", now.UnixNano()),
				EventType:     "mail.sent",
				Timestamp:     now,
				MessageID:     item.ID,
				CorrelationID: item.CorrelationID,
				State:         models.MailStateSent,
				Payload:       item,
			})
		}
		return
	}

	// Delivery failed
	item.LastError = err.Error()
	p.logger.Warn("delivery attempt failed",
		"mail_id", item.ID,
		"attempt", item.Attempts,
		"error", err,
	)

	maxAttempts := item.MaxAttempts
	if maxAttempts <= 0 {
		maxAttempts = p.cfg.QueueMaxRetries
		if maxAttempts <= 0 {
			maxAttempts = 5
		}
	}

	if item.Attempts >= maxAttempts {
		// Dead Letter Queue: Max retries exceeded
		item.State = models.MailStateFailed
		item.UpdatedAt = now
		_ = p.q.Update(p.ctx, item)

		p.logger.Error("email permanently failed after max retries",
			"mail_id", item.ID,
			"attempts", item.Attempts,
			"error", err,
		)

		if p.dispatcher != nil {
			p.dispatcher.Dispatch(p.ctx, models.StatusEvent{
				EventID:       fmt.Sprintf("evt_%d", now.UnixNano()),
				EventType:     "mail.failed",
				Timestamp:     now,
				MessageID:     item.ID,
				CorrelationID: item.CorrelationID,
				State:         models.MailStateFailed,
				Error:         err.Error(),
				Payload:       item,
			})
		}
		return
	}

	// Schedule exponential backoff retry
	backoff := p.calculateBackoff(item.Attempts)
	item.State = models.MailStateQueued
	item.NextAttemptAt = now.Add(backoff)
	item.UpdatedAt = now
	_ = p.q.Update(p.ctx, item)

	p.logger.Info("scheduled email retry with exponential backoff",
		"mail_id", item.ID,
		"backoff", backoff,
		"next_attempt_at", item.NextAttemptAt,
	)
}

func (p *Processor) calculateBackoff(attempt int) time.Duration {
	mult := math.Pow(2, float64(attempt-1))
	backoff := time.Duration(float64(p.cfg.QueueBaseBackoff) * mult)
	if backoff > p.cfg.QueueMaxBackoff {
		backoff = p.cfg.QueueMaxBackoff
	}
	return backoff
}
