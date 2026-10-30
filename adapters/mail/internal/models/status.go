package models

import (
	"time"
)

// MailState indicates the processing state of an outgoing message.
type MailState string

const (
	MailStateQueued    MailState = "QUEUED"
	MailStateSending   MailState = "SENDING"
	MailStateSent      MailState = "SENT"
	MailStateDelivered MailState = "DELIVERED"
	MailStateFailed    MailState = "FAILED"
	MailStateBounced   MailState = "BOUNCED"
)

// QueuedMail represents an email stored in the persistent retry queue.
type QueuedMail struct {
	ID             string          `json:"id"`
	IdempotencyKey string          `json:"idempotency_key,omitempty"`
	CorrelationID  string          `json:"correlation_id,omitempty"`
	Request        SendMailRequest `json:"request"`
	State          MailState       `json:"state"`
	Attempts       int             `json:"attempts"`
	MaxAttempts    int             `json:"max_attempts"`
	NextAttemptAt  time.Time       `json:"next_attempt_at"`
	LastError      string          `json:"last_error,omitempty"`
	CreatedAt      time.Time       `json:"created_at"`
	UpdatedAt      time.Time       `json:"updated_at"`
	SentAt         *time.Time      `json:"sent_at,omitempty"`
}

// StatusResponse is returned by GET /api/v1/mail/status/{id}.
type StatusResponse struct {
	ID             string         `json:"id"`
	State          MailState      `json:"state"`
	CorrelationID  string         `json:"correlation_id,omitempty"`
	Attempts       int            `json:"attempts"`
	MaxAttempts    int            `json:"max_attempts"`
	LastError      string         `json:"last_error,omitempty"`
	CreatedAt      time.Time      `json:"created_at"`
	UpdatedAt      time.Time      `json:"updated_at"`
	SentAt         *time.Time     `json:"sent_at,omitempty"`
	Metadata       map[string]any `json:"metadata,omitempty"`
	Meta           map[string]any `json:"meta,omitempty"`
	CustomData     map[string]any `json:"custom_data,omitempty"`
}

// StatusEvent is dispatched to the STATUS_WEBHOOK_URL on lifecycle state changes.
type StatusEvent struct {
	EventID       string    `json:"event_id"`
	EventType     string    `json:"event_type"` // mail.queued, mail.sent, mail.failed, mail.bounced, mail.inbound
	Timestamp     time.Time `json:"timestamp"`
	MessageID     string    `json:"message_id"`
	CorrelationID string    `json:"correlation_id,omitempty"`
	State         MailState `json:"state,omitempty"`
	Error         string    `json:"error,omitempty"`
	Payload       any       `json:"payload,omitempty"`
}
