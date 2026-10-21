package webhooks

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"path/filepath"
	"strings"
	"time"

	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/config"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/models"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/queue"
	"github.com/emersion/go-message/mail"
	"github.com/google/uuid"
)

// Handler processes inbound emails and provider delivery status webhooks.
type Handler struct {
	cfg        *config.Config
	q          *queue.BoltQueue
	dispatcher queue.EventDispatcherInterface
	logger     *slog.Logger
}

// NewHandler creates a new webhook handler.
func NewHandler(cfg *config.Config, q *queue.BoltQueue, dispatcher queue.EventDispatcherInterface, logger *slog.Logger) *Handler {
	return &Handler{
		cfg:        cfg,
		q:          q,
		dispatcher: dispatcher,
		logger:     logger,
	}
}

// ParseRawMIME parses an RFC 5322/2045 raw MIME stream into a normalized InboundMail.
func ParseRawMIME(r io.Reader, maxAttachmentSize int64) (*models.InboundMail, error) {
	mr, err := mail.CreateReader(r)
	if err != nil {
		return nil, fmt.Errorf("failed creating MIME reader: %w", err)
	}
	defer mr.Close()

	inbound := &models.InboundMail{
		ID:          uuid.New().String(),
		Provider:    "mime",
		Headers:     make(map[string]string),
		Attachments: make([]models.Attachment, 0),
		ReceivedAt:  time.Now(),
	}

	// Extract standard headers
	if subject, err := mr.Header.Subject(); err == nil {
		inbound.Subject = subject
	}
	if fromAddrs, err := mr.Header.AddressList("From"); err == nil && len(fromAddrs) > 0 {
		inbound.From = fromAddrs[0].Address
	}
	if toAddrs, err := mr.Header.AddressList("To"); err == nil {
		for _, addr := range toAddrs {
			inbound.To = append(inbound.To, addr.Address)
		}
	}
	if ccAddrs, err := mr.Header.AddressList("Cc"); err == nil {
		for _, addr := range ccAddrs {
			inbound.Cc = append(inbound.Cc, addr.Address)
		}
	}
	if msgID, err := mr.Header.MessageID(); err == nil {
		inbound.MessageID = msgID
	}
	if date, err := mr.Header.Date(); err == nil && !date.IsZero() {
		inbound.ReceivedAt = date
	}

	// Read parts (text, html, attachments)
	var textBody strings.Builder
	var htmlBody strings.Builder

	for {
		part, err := mr.NextPart()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("error reading MIME part: %w", err)
		}

		switch h := part.Header.(type) {
		case *mail.InlineHeader:
			contentType, _, _ := h.ContentType()
			bodyBytes, err := io.ReadAll(part.Body)
			if err != nil {
				return nil, fmt.Errorf("failed reading inline body: %w", err)
			}

			if strings.HasPrefix(strings.ToLower(contentType), "text/html") {
				htmlBody.Write(bodyBytes)
			} else {
				textBody.Write(bodyBytes)
			}

		case *mail.AttachmentHeader:
			filename, _ := h.Filename()
			if filename == "" {
				filename = "attachment.bin"
			}
			filename = filepath.Base(filepath.Clean(filename))

			contentType, _, _ := h.ContentType()
			if contentType == "" {
				contentType = "application/octet-stream"
			}

			dataBytes, err := io.ReadAll(part.Body)
			if err != nil {
				return nil, fmt.Errorf("failed reading attachment body for '%s': %w", filename, err)
			}

			size := int64(len(dataBytes))
			if maxAttachmentSize > 0 && size > maxAttachmentSize {
				return nil, fmt.Errorf("attachment '%s' size %d exceeds limit %d bytes", filename, size, maxAttachmentSize)
			}

			hash := sha256.Sum256(dataBytes)
			inbound.Attachments = append(inbound.Attachments, models.Attachment{
				Filename:    filename,
				ContentType: contentType,
				Size:        size,
				Data:        base64.StdEncoding.EncodeToString(dataBytes),
				SHA256:      hex.EncodeToString(hash[:]),
			})
		}
	}

	inbound.TextBody = textBody.String()
	inbound.HTMLBody = htmlBody.String()

	return inbound, nil
}

// HandleResend processes Resend webhook callbacks.
func (h *Handler) HandleResend(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "failed reading body", http.StatusBadRequest)
		return
	}

	var payload models.ResendWebhookPayload
	if err := json.Unmarshal(body, &payload); err != nil {
		h.logger.Warn("invalid Resend webhook json", "error", err)
		http.Error(w, "invalid json payload", http.StatusBadRequest)
		return
	}

	var mappedState models.MailState
	switch payload.Type {
	case "email.delivered":
		mappedState = models.MailStateDelivered
	case "email.bounced":
		mappedState = models.MailStateBounced
	case "email.complained", "email.failed":
		mappedState = models.MailStateFailed
	case "email.sent":
		mappedState = models.MailStateSent
	default:
		mappedState = models.MailStateSending
	}

	h.logger.Info("received Resend webhook event",
		"type", payload.Type,
		"email_id", payload.Data.EmailID,
		"state", mappedState,
	)

	if h.dispatcher != nil {
		h.dispatcher.Dispatch(r.Context(), models.StatusEvent{
			EventID:   fmt.Sprintf("resend_%d", time.Now().UnixNano()),
			EventType: "mail.status_update",
			Timestamp: time.Now(),
			MessageID: payload.Data.EmailID,
			State:     mappedState,
			Payload:   payload,
		})
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(map[string]any{"status": "ok", "provider": "resend"})
}

// HandleBrevo processes Brevo transactional webhook events.
func (h *Handler) HandleBrevo(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "failed reading body", http.StatusBadRequest)
		return
	}

	var payload models.BrevoWebhookPayload
	if err := json.Unmarshal(body, &payload); err != nil {
		h.logger.Warn("invalid Brevo webhook json", "error", err)
		http.Error(w, "invalid json payload", http.StatusBadRequest)
		return
	}

	var mappedState models.MailState
	switch strings.ToLower(payload.Event) {
	case "delivered":
		mappedState = models.MailStateDelivered
	case "hard_bounce", "soft_bounce":
		mappedState = models.MailStateBounced
	case "blocked", "spam", "invalid_email":
		mappedState = models.MailStateFailed
	default:
		mappedState = models.MailStateSending
	}

	h.logger.Info("received Brevo webhook event",
		"event", payload.Event,
		"message_id", payload.MessageID,
		"recipient", payload.Email,
		"state", mappedState,
	)

	if h.dispatcher != nil {
		h.dispatcher.Dispatch(r.Context(), models.StatusEvent{
			EventID:   fmt.Sprintf("brevo_%d", time.Now().UnixNano()),
			EventType: "mail.status_update",
			Timestamp: time.Now(),
			MessageID: payload.MessageID,
			State:     mappedState,
			Error:     payload.Reason,
			Payload:   payload,
		})
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(map[string]any{"status": "ok", "provider": "brevo"})
}

// HandleSendGrid processes SendGrid Event and Inbound Parse webhooks.
func (h *Handler) HandleSendGrid(w http.ResponseWriter, r *http.Request) {
	contentType := r.Header.Get("Content-Type")

	// Multipart form is used by SendGrid Inbound Parse
	if strings.HasPrefix(contentType, "multipart/form-data") {
		h.handleSendGridInboundParse(w, r)
		return
	}

	// JSON array is used by SendGrid Event Webhook
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "failed reading body", http.StatusBadRequest)
		return
	}

	var events []models.SendGridEventPayload
	if err := json.Unmarshal(body, &events); err != nil {
		h.logger.Warn("invalid SendGrid webhook json", "error", err)
		http.Error(w, "invalid json payload", http.StatusBadRequest)
		return
	}

	for _, evt := range events {
		var mappedState models.MailState
		switch strings.ToLower(evt.Event) {
		case "delivered":
			mappedState = models.MailStateDelivered
		case "bounce":
			mappedState = models.MailStateBounced
		case "dropped", "deferred":
			mappedState = models.MailStateFailed
		case "processed":
			mappedState = models.MailStateSent
		default:
			mappedState = models.MailStateSending
		}

		h.logger.Info("received SendGrid event",
			"event", evt.Event,
			"msg_id", evt.SGMsgID,
			"recipient", evt.Email,
			"state", mappedState,
		)

		if h.dispatcher != nil {
			h.dispatcher.Dispatch(r.Context(), models.StatusEvent{
				EventID:   fmt.Sprintf("sg_%d", time.Now().UnixNano()),
				EventType: "mail.status_update",
				Timestamp: time.Now(),
				MessageID: evt.SGMsgID,
				State:     mappedState,
				Error:     evt.Reason,
				Payload:   evt,
			})
		}
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(map[string]any{"status": "ok", "events_processed": len(events)})
}

func (h *Handler) handleSendGridInboundParse(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseMultipartForm(int64(h.cfg.MaxAttachmentSizeBytes)); err != nil {
		http.Error(w, fmt.Sprintf("failed parsing multipart form: %v", err), http.StatusBadRequest)
		return
	}

	inbound := &models.InboundMail{
		ID:         uuid.New().String(),
		Provider:   "sendgrid_inbound",
		From:       r.FormValue("from"),
		Subject:    r.FormValue("subject"),
		TextBody:   r.FormValue("text"),
		HTMLBody:   r.FormValue("html"),
		ReceivedAt: time.Now(),
	}

	if toStr := r.FormValue("to"); toStr != "" {
		inbound.To = strings.Split(toStr, ",")
	}

	// Extract attached files
	if r.MultipartForm != nil && r.MultipartForm.File != nil {
		for _, fheaders := range r.MultipartForm.File {
			for _, fh := range fheaders {
				f, err := fh.Open()
				if err != nil {
					continue
				}
				data, _ := io.ReadAll(f)
				f.Close()

				hash := sha256.Sum256(data)
				inbound.Attachments = append(inbound.Attachments, models.Attachment{
					Filename:    filepath.Base(fh.Filename),
					ContentType: fh.Header.Get("Content-Type"),
					Size:        int64(len(data)),
					Data:        base64.StdEncoding.EncodeToString(data),
					SHA256:      hex.EncodeToString(hash[:]),
				})
			}
		}
	}

	h.logger.Info("received SendGrid inbound email", "from", inbound.From, "subject", inbound.Subject, "attachments", len(inbound.Attachments))

	if h.dispatcher != nil {
		h.dispatcher.Dispatch(r.Context(), models.StatusEvent{
			EventID:   fmt.Sprintf("inbound_%d", time.Now().UnixNano()),
			EventType: "mail.inbound",
			Timestamp: time.Now(),
			MessageID: inbound.ID,
			Payload:   inbound,
		})
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(map[string]any{"status": "received", "id": inbound.ID})
}

// HandleGeneric accepts direct JSON or raw MIME emails.
func (h *Handler) HandleGeneric(w http.ResponseWriter, r *http.Request) {
	contentType := r.Header.Get("Content-Type")

	// Raw MIME ingestion (message/rfc822 or text/plain with raw MIME)
	if strings.HasPrefix(contentType, "message/rfc822") || strings.HasPrefix(contentType, "text/plain") {
		inbound, err := ParseRawMIME(r.Body, h.cfg.MaxAttachmentSizeBytes)
		if err != nil {
			http.Error(w, fmt.Sprintf("invalid raw MIME: %v", err), http.StatusBadRequest)
			return
		}
		inbound.Provider = "generic_mime"
		h.dispatchInbound(r.Context(), w, inbound)
		return
	}

	// Standard JSON payload
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "failed reading body", http.StatusBadRequest)
		return
	}

	var req models.GenericInboundRequest
	if err := json.Unmarshal(body, &req); err != nil {
		http.Error(w, "invalid json: "+err.Error(), http.StatusBadRequest)
		return
	}

	// If RawMIME field is populated, parse that
	if req.RawMIME != "" {
		var mimeReader io.Reader
		// Check if Base64
		if rawDecoded, err := base64.StdEncoding.DecodeString(req.RawMIME); err == nil {
			mimeReader = bytes.NewReader(rawDecoded)
		} else {
			mimeReader = strings.NewReader(req.RawMIME)
		}

		inbound, err := ParseRawMIME(mimeReader, h.cfg.MaxAttachmentSizeBytes)
		if err != nil {
			http.Error(w, "failed parsing raw_mime: "+err.Error(), http.StatusBadRequest)
			return
		}
		inbound.Provider = "generic_json_raw_mime"
		h.dispatchInbound(r.Context(), w, inbound)
		return
	}

	// Structured fields
	inbound := &models.InboundMail{
		ID:          uuid.New().String(),
		Provider:    "generic_json",
		From:        req.From,
		To:          req.To,
		Cc:          req.Cc,
		Subject:     req.Subject,
		TextBody:    req.TextBody,
		HTMLBody:    req.HTMLBody,
		Headers:     req.Headers,
		Attachments: req.Attachments,
		ReceivedAt:  time.Now(),
	}

	if req.ReceivedAt != nil {
		inbound.ReceivedAt = *req.ReceivedAt
	}

	// Sanitize and validate any attachments
	for i := range inbound.Attachments {
		if _, err := inbound.Attachments[i].ValidateAndSanitize(h.cfg.MaxAttachmentSizeBytes); err != nil {
			http.Error(w, fmt.Sprintf("invalid attachment '%s': %v", inbound.Attachments[i].Filename, err), http.StatusBadRequest)
			return
		}
	}

	h.dispatchInbound(r.Context(), w, inbound)
}

func (h *Handler) dispatchInbound(ctx context.Context, w http.ResponseWriter, inbound *models.InboundMail) {
	h.logger.Info("inbound email processed",
		"id", inbound.ID,
		"provider", inbound.Provider,
		"from", inbound.From,
		"subject", inbound.Subject,
		"attachments_count", len(inbound.Attachments),
	)

	if h.dispatcher != nil {
		h.dispatcher.Dispatch(ctx, models.StatusEvent{
			EventID:   fmt.Sprintf("inbound_%d", time.Now().UnixNano()),
			EventType: "mail.inbound",
			Timestamp: time.Now(),
			MessageID: inbound.ID,
			Payload:   inbound,
		})
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"status":      "received",
		"id":          inbound.ID,
		"subject":     inbound.Subject,
		"from":        inbound.From,
		"attachments": len(inbound.Attachments),
	})
}
