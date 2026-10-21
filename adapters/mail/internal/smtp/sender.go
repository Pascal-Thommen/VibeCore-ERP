package smtp

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/base64"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/config"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/models"
	"github.com/wneessen/go-mail"
)

// SMTPSender implements email dispatching over SMTP using standard-compliant go-mail.
type SMTPSender struct {
	cfg    *config.Config
	client *mail.Client
}

// NewSMTPSender creates a configured SMTPSender instance.
func NewSMTPSender(cfg *config.Config) (*SMTPSender, error) {
	timeout := cfg.SMTPConnectTimeout
	if timeout <= 0 {
		timeout = 10 * time.Second
	}

	opts := []mail.Option{
		mail.WithPort(cfg.SMTPPort),
		mail.WithTimeout(timeout),
	}

	// Configure TLS Policy
	switch strings.ToLower(cfg.SMTPTLSPolicy) {
	case "mandatory":
		opts = append(opts, mail.WithTLSPolicy(mail.TLSMandatory))
	case "none":
		opts = append(opts, mail.WithTLSPolicy(mail.NoTLS))
	default:
		// Opportunistic / STARTTLS
		opts = append(opts, mail.WithTLSPolicy(mail.TLSOpportunistic))
	}

	// Skip certificate verification in test/dev if needed, but allow secure TLS by default
	if cfg.Environment == "test" || cfg.Environment == "development" {
		opts = append(opts, mail.WithTLSConfig(&tls.Config{
			InsecureSkipVerify: true, // for local self-signed or mock mailhog/mailpit
		}))
	}

	// Authentication
	if cfg.SMTPUsername != "" {
		opts = append(opts,
			mail.WithSMTPAuth(mail.SMTPAuthPlain),
			mail.WithUsername(cfg.SMTPUsername),
			mail.WithPassword(cfg.SMTPPassword),
		)
	}

	client, err := mail.NewClient(cfg.SMTPHost, opts...)
	if err != nil {
		return nil, fmt.Errorf("failed creating SMTP client for host '%s': %w", cfg.SMTPHost, err)
	}

	return &SMTPSender{
		cfg:    cfg,
		client: client,
	}, nil
}

// BuildMessage constructs a go-mail Msg from SendMailRequest.
func (s *SMTPSender) BuildMessage(req *models.SendMailRequest) (*mail.Msg, error) {
	msg := mail.NewMsg()

	// Sender (From)
	fromEmail := req.From
	if fromEmail == "" {
		fromEmail = s.cfg.SMTPFromEmail
	}
	fromName := req.FromName
	if fromName == "" {
		fromName = s.cfg.SMTPFromName
	}

	if fromName != "" {
		if err := msg.FromFormat(fromName, fromEmail); err != nil {
			return nil, fmt.Errorf("invalid from address '%s <%s>': %w", fromName, fromEmail, err)
		}
	} else {
		if err := msg.From(fromEmail); err != nil {
			return nil, fmt.Errorf("invalid from address '%s': %w", fromEmail, err)
		}
	}

	// Recipients (To)
	if len(req.To) == 0 {
		return nil, errors.New("at least one 'to' recipient address is required")
	}
	if err := msg.To(req.To...); err != nil {
		return nil, fmt.Errorf("invalid 'to' recipients: %w", err)
	}

	// Carbon Copy (Cc)
	if len(req.Cc) > 0 {
		if err := msg.Cc(req.Cc...); err != nil {
			return nil, fmt.Errorf("invalid 'cc' recipients: %w", err)
		}
	}

	// Blind Carbon Copy (Bcc)
	if len(req.Bcc) > 0 {
		if err := msg.Bcc(req.Bcc...); err != nil {
			return nil, fmt.Errorf("invalid 'bcc' recipients: %w", err)
		}
	}

	// Reply-To
	if req.ReplyTo != "" {
		if err := msg.ReplyTo(req.ReplyTo); err != nil {
			return nil, fmt.Errorf("invalid 'reply_to' address '%s': %w", req.ReplyTo, err)
		}
	}

	// Subject
	msg.Subject(req.Subject)

	// Custom Headers
	for k, v := range req.Headers {
		msg.SetGenHeader(mail.Header(k), v)
	}

	// Bodies
	hasText := req.TextBody != ""
	hasHTML := req.HTMLBody != ""

	if hasText && hasHTML {
		msg.SetBodyString(mail.TypeTextPlain, req.TextBody)
		msg.AddAlternativeString(mail.TypeTextHTML, req.HTMLBody)
	} else if hasHTML {
		msg.SetBodyString(mail.TypeTextHTML, req.HTMLBody)
	} else if hasText {
		msg.SetBodyString(mail.TypeTextPlain, req.TextBody)
	} else {
		return nil, errors.New("mail has neither text nor html content")
	}

	// Attachments
	for _, att := range req.Attachments {
		decoded, err := base64.StdEncoding.DecodeString(att.Data)
		if err != nil {
			return nil, fmt.Errorf("failed decoding attachment '%s': %w", att.Filename, err)
		}

		opts := []mail.FileOption{}
		if att.ContentType != "" {
			opts = append(opts, mail.WithFileContentType(mail.ContentType(att.ContentType)))
		}

		if err := msg.AttachReader(att.Filename, bytes.NewReader(decoded), opts...); err != nil {
			return nil, fmt.Errorf("failed attaching '%s': %w", att.Filename, err)
		}
	}

	return msg, nil
}

// Send delivers the email to the SMTP server.
func (s *SMTPSender) Send(ctx context.Context, req *models.SendMailRequest) error {
	msg, err := s.BuildMessage(req)
	if err != nil {
		return fmt.Errorf("failed building email message: %w", err)
	}

	if err := s.client.DialAndSendWithContext(ctx, msg); err != nil {
		return fmt.Errorf("smtp delivery error: %w", err)
	}

	return nil
}
