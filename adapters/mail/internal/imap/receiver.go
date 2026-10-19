package imap

import (
	"bytes"
	"context"
	"crypto/tls"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/config"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/models"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/queue"
	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/webhooks"
	"github.com/emersion/go-imap/v2"
	"github.com/emersion/go-imap/v2/imapclient"
)

// Receiver polls an IMAP mailbox and listens for incoming emails via IMAP IDLE.
type Receiver struct {
	cfg        *config.Config
	dispatcher queue.EventDispatcherInterface
	logger     *slog.Logger

	ctx    context.Context
	cancel context.CancelFunc
	wg     sync.WaitGroup
	mu     sync.Mutex
	client *imapclient.Client
}

// NewReceiver creates a new IMAP receiver.
func NewReceiver(cfg *config.Config, dispatcher queue.EventDispatcherInterface, logger *slog.Logger) *Receiver {
	ctx, cancel := context.WithCancel(context.Background())
	return &Receiver{
		cfg:        cfg,
		dispatcher: dispatcher,
		logger:     logger,
		ctx:        ctx,
		cancel:     cancel,
	}
}

// Start begins the IMAP polling and IDLE loop in a background goroutine.
func (r *Receiver) Start() error {
	if !r.cfg.IMAPEnabled {
		r.logger.Info("IMAP receiver is disabled via configuration (IMAP_ENABLED=false)")
		return nil
	}

	if r.cfg.IMAPHost == "" {
		r.logger.Warn("IMAP host is empty; skipping IMAP receiver startup")
		return nil
	}

	r.logger.Info("starting IMAP receiver",
		"host", r.cfg.IMAPHost,
		"port", r.cfg.IMAPPort,
		"mailbox", r.cfg.IMAPMailbox,
		"idle", r.cfg.IMAPIdleEnabled,
	)

	r.wg.Add(1)
	go r.runLoop()
	return nil
}

// Stop gracefully terminates the IMAP receiver and disconnects.
func (r *Receiver) Stop() {
	r.cancel()

	r.mu.Lock()
	if r.client != nil {
		_ = r.client.Close()
	}
	r.mu.Unlock()

	r.wg.Wait()
	r.logger.Info("IMAP receiver stopped")
}

func (r *Receiver) runLoop() {
	defer r.wg.Done()

	backoff := 2 * time.Second
	for {
		select {
		case <-r.ctx.Done():
			return
		default:
			err := r.connectAndListen()
			if err != nil && r.ctx.Err() == nil {
				r.logger.Error("IMAP connection error; reconnecting with backoff", "error", err, "backoff", backoff)
				select {
				case <-time.After(backoff):
					backoff *= 2
					if backoff > 60*time.Second {
						backoff = 60 * time.Second
					}
				case <-r.ctx.Done():
					return
				}
			} else {
				backoff = 2 * time.Second
			}
		}
	}
}

func (r *Receiver) connectAndListen() error {
	addr := fmt.Sprintf("%s:%d", r.cfg.IMAPHost, r.cfg.IMAPPort)
	opts := &imapclient.Options{}

	if r.cfg.Environment == "test" || r.cfg.Environment == "development" {
		opts.TLSConfig = &tls.Config{InsecureSkipVerify: true}
	}

	var client *imapclient.Client
	var err error

	if r.cfg.IMAPUseTLS {
		client, err = imapclient.DialTLS(addr, opts)
	} else {
		client, err = imapclient.DialInsecure(addr, opts)
	}

	if err != nil {
		return fmt.Errorf("failed connecting to IMAP server at '%s': %w", addr, err)
	}

	r.mu.Lock()
	r.client = client
	r.mu.Unlock()

	defer func() {
		_ = client.Close()
		r.mu.Lock()
		r.client = nil
		r.mu.Unlock()
	}()

	// Login
	if r.cfg.IMAPUsername != "" {
		if err := client.Login(r.cfg.IMAPUsername, r.cfg.IMAPPassword).Wait(); err != nil {
			return fmt.Errorf("IMAP login failed: %w", err)
		}
	}

	// Select mailbox
	mailbox := r.cfg.IMAPMailbox
	if mailbox == "" {
		mailbox = "INBOX"
	}

	selectData, err := client.Select(mailbox, nil).Wait()
	if err != nil {
		return fmt.Errorf("failed selecting mailbox '%s': %w", mailbox, err)
	}

	r.logger.Info("selected IMAP mailbox", "mailbox", mailbox, "num_messages", selectData.NumMessages)

	// Fetch any existing unseen messages first
	if err := r.fetchUnseenMessages(client); err != nil {
		r.logger.Warn("initial unseen message fetch error", "error", err)
	}

	// Loop with IDLE or Poll
	for {
		select {
		case <-r.ctx.Done():
			return nil
		default:
			if r.cfg.IMAPIdleEnabled {
				idleCmd, err := client.Idle()
				if err != nil {
					r.logger.Warn("IMAP IDLE not supported or failed; falling back to periodic poll", "error", err)
					time.Sleep(r.cfg.IMAPPollInterval)
				} else {
					// Wait for poll interval or context cancel, then close IDLE and fetch new messages
					select {
					case <-r.ctx.Done():
						_ = idleCmd.Close()
						return nil
					case <-time.After(r.cfg.IMAPPollInterval):
						_ = idleCmd.Close()
					}
				}
			} else {
				select {
				case <-r.ctx.Done():
					return nil
				case <-time.After(r.cfg.IMAPPollInterval):
				}
			}

			// Fetch unseen messages
			if err := r.fetchUnseenMessages(client); err != nil {
				return err
			}
		}
	}
}

func (r *Receiver) fetchUnseenMessages(client *imapclient.Client) error {
	criteria := &imap.SearchCriteria{
		NotFlag: []imap.Flag{imap.FlagSeen},
	}

	searchRes, err := client.UIDSearch(criteria, nil).Wait()
	if err != nil {
		return fmt.Errorf("failed searching unseen messages: %w", err)
	}

	uids := searchRes.AllUIDs()
	if len(uids) == 0 {
		return nil
	}

	r.logger.Info("found unseen IMAP messages", "count", len(uids))

	fetchOptions := &imap.FetchOptions{
		BodySection: []*imap.FetchItemBodySection{
			{}, // entire RFC822 message
		},
		Envelope: true,
		Flags:    true,
	}

	for _, uid := range uids {
		numSet := imap.UIDSet{imap.UIDRange{Start: uid, Stop: uid}}
		fetchCmd := client.Fetch(numSet, fetchOptions)

		for {
			msg := fetchCmd.Next()
			if msg == nil {
				break
			}

			var rawMsg bytes.Buffer
			for {
				item := msg.Next()
				if item == nil {
					break
				}
				if bodySection, ok := item.(imapclient.FetchItemDataBodySection); ok {
					_, _ = rawMsg.ReadFrom(bodySection.Literal)
				}
			}

			if rawMsg.Len() > 0 {
				inbound, err := webhooks.ParseRawMIME(&rawMsg, r.cfg.MaxAttachmentSizeBytes)
				if err != nil {
					r.logger.Warn("failed parsing incoming IMAP email", "uid", uid, "error", err)
					continue
				}
				inbound.Provider = "imap"

				r.logger.Info("successfully ingested incoming IMAP email",
					"uid", uid,
					"from", inbound.From,
					"subject", inbound.Subject,
					"attachments_count", len(inbound.Attachments),
				)

				if r.dispatcher != nil {
					r.dispatcher.Dispatch(r.ctx, models.StatusEvent{
						EventID:   fmt.Sprintf("imap_%d", time.Now().UnixNano()),
						EventType: "mail.inbound",
						Timestamp: time.Now(),
						MessageID: inbound.ID,
						Payload:   inbound,
					})
				}

				if r.cfg.IMAPMarkAsSeen {
					storeFlags := &imap.StoreFlags{
						Op:     imap.StoreFlagsAdd,
						Flags:  []imap.Flag{imap.FlagSeen},
						Silent: true,
					}
					_ = client.Store(numSet, storeFlags, nil).Close()
				}
			}
		}

		if err := fetchCmd.Close(); err != nil {
			r.logger.Warn("error closing fetch command", "uid", uid, "error", err)
		}
	}

	return nil
}
