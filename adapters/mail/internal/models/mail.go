package models

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"path/filepath"
	"strings"
	"time"
)

// Attachment represents an email attachment (inbound or outbound).
type Attachment struct {
	Filename    string `json:"filename"`
	ContentType string `json:"content_type"`
	Size        int64  `json:"size"`
	Data        string `json:"data"` // Base64 encoded
	SHA256      string `json:"sha256,omitempty"`
}

// ValidateAndSanitize checks attachment validity and computes SHA256 checksum.
func (a *Attachment) ValidateAndSanitize(maxSizeBytes int64) ([]byte, error) {
	// Sanitize filename: remove directory traversal attempts
	cleaned := filepath.Base(filepath.Clean(a.Filename))
	if cleaned == "." || cleaned == "/" || cleaned == "" {
		cleaned = "attachment"
	}
	a.Filename = cleaned

	if a.ContentType == "" {
		a.ContentType = "application/octet-stream"
	}

	decoded, err := base64.StdEncoding.DecodeString(a.Data)
	if err != nil {
		return nil, fmt.Errorf("invalid base64 encoding for attachment '%s': %w", a.Filename, err)
	}

	size := int64(len(decoded))
	if maxSizeBytes > 0 && size > maxSizeBytes {
		return nil, fmt.Errorf("attachment '%s' exceeds maximum allowed size (%d > %d bytes)", a.Filename, size, maxSizeBytes)
	}

	a.Size = size
	hash := sha256.Sum256(decoded)
	a.SHA256 = hex.EncodeToString(hash[:])

	return decoded, nil
}

// SendMailRequest defines the payload accepted by POST /api/v1/mail/send.
type SendMailRequest struct {
	From         string            `json:"from,omitempty"`
	FromName     string            `json:"from_name,omitempty"`
	To           []string          `json:"to"`
	Cc           []string          `json:"cc,omitempty"`
	Bcc          []string          `json:"bcc,omitempty"`
	ReplyTo      string            `json:"reply_to,omitempty"`
	Subject      string            `json:"subject"`
	TextBody     string            `json:"text_body,omitempty"`
	HTMLBody     string            `json:"html_body,omitempty"`
	Template     string            `json:"template,omitempty"`
	TemplateData map[string]any    `json:"template_data,omitempty"`
	Attachments  []Attachment      `json:"attachments,omitempty"`
	Headers      map[string]string `json:"headers,omitempty"`
	Tags         []string          `json:"tags,omitempty"`
	Metadata     map[string]any    `json:"metadata,omitempty"`
	Meta         map[string]any    `json:"meta,omitempty"`
	CustomData   map[string]any    `json:"custom_data,omitempty"`
}

// Validate validates the outgoing mail request.
func (r *SendMailRequest) Validate(maxAttachmentSize int64) error {
	if len(r.To) == 0 {
		return errors.New("'to' must contain at least one recipient email address")
	}

	for _, recipient := range r.To {
		if strings.TrimSpace(recipient) == "" {
			return errors.New("recipient address in 'to' cannot be empty")
		}
	}

	if strings.TrimSpace(r.Subject) == "" {
		return errors.New("'subject' cannot be empty")
	}

	if r.Template == "" && strings.TrimSpace(r.TextBody) == "" && strings.TrimSpace(r.HTMLBody) == "" {
		return errors.New("must provide either 'template', 'text_body', or 'html_body'")
	}

	var totalSize int64
	for i := range r.Attachments {
		raw, err := r.Attachments[i].ValidateAndSanitize(maxAttachmentSize)
		if err != nil {
			return err
		}
		totalSize += int64(len(raw))
		if maxAttachmentSize > 0 && totalSize > maxAttachmentSize {
			return fmt.Errorf("cumulative attachment size exceeds limit of %d bytes", maxAttachmentSize)
		}
	}

	return nil
}

// InboundMail represents a normalized email received via IMAP or Webhooks.
type InboundMail struct {
	ID          string            `json:"id"`
	Provider    string            `json:"provider"` // imap, resend, brevo, sendgrid, generic
	MessageID   string            `json:"message_id"`
	From        string            `json:"from"`
	To          []string          `json:"to"`
	Cc          []string          `json:"cc,omitempty"`
	Subject     string            `json:"subject"`
	TextBody    string            `json:"text_body"`
	HTMLBody    string            `json:"html_body,omitempty"`
	Attachments []Attachment      `json:"attachments,omitempty"`
	Headers     map[string]string `json:"headers,omitempty"`
	RawMIME     string            `json:"raw_mime,omitempty"`
	ReceivedAt  time.Time         `json:"received_at"`
	Meta        map[string]any    `json:"meta,omitempty"`
	CustomData  map[string]any    `json:"custom_data,omitempty"`
}
