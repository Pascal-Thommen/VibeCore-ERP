package models

import "time"

// ResendWebhookPayload represents events received from Resend webhooks.
type ResendWebhookPayload struct {
	Type      string `json:"type"` // e.g. "email.sent", "email.delivered", "email.bounced"
	CreatedAt string `json:"created_at"`
	Data      struct {
		EmailID   string   `json:"email_id"`
		From      string   `json:"from"`
		To        []string `json:"to"`
		Subject   string   `json:"subject"`
		CreatedAt string   `json:"created_at"`
		Status    string   `json:"status"`
	} `json:"data"`
}

// BrevoWebhookPayload represents transactional delivery events from Brevo.
type BrevoWebhookPayload struct {
	Event     string    `json:"event"` // e.g. "delivered", "hard_bounce", "soft_bounce", "blocked", "spam"
	Email     string    `json:"email"`
	MessageID string    `json:"message-id"`
	Date      string    `json:"date"`
	Reason    string    `json:"reason,omitempty"`
	Tag       string    `json:"tag,omitempty"`
	Ts        int64     `json:"ts,omitempty"`
}

// SendGridEventPayload represents delivery events from SendGrid.
type SendGridEventPayload struct {
	Event     string `json:"event"` // e.g. "processed", "dropped", "delivered", "bounce", "deferred"
	Email     string `json:"email"`
	SGEventID string `json:"sg_event_id"`
	SGMsgID   string `json:"sg_message_id"`
	Reason    string `json:"reason,omitempty"`
	Status    string `json:"status,omitempty"`
	Timestamp int64  `json:"timestamp"`
}

// GenericInboundRequest represents a generic JSON payload for inbound email ingestion.
type GenericInboundRequest struct {
	From        string            `json:"from"`
	To          []string          `json:"to"`
	Cc          []string          `json:"cc,omitempty"`
	Subject     string            `json:"subject"`
	TextBody    string            `json:"text_body"`
	HTMLBody    string            `json:"html_body,omitempty"`
	Headers     map[string]string `json:"headers,omitempty"`
	Attachments []Attachment      `json:"attachments,omitempty"`
	RawMIME     string            `json:"raw_mime,omitempty"` // Base64 or plain string
	ReceivedAt  *time.Time        `json:"received_at,omitempty"`
}
