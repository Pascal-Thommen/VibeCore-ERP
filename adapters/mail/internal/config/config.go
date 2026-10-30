package config

import (
	"os"
	"strconv"
	"strings"
	"time"
)

// Config holds all configuration parameters for the mail microservice.
type Config struct {
	// Server settings
	Host        string
	Port        int
	APIKey      string
	Environment string
	LogLevel    string

	// SMTP settings
	SMTPHost           string
	SMTPPort           int
	SMTPUsername       string
	SMTPPassword       string
	SMTPFromEmail      string
	SMTPFromName       string
	SMTPTLSPolicy      string // "mandatory", "opportunistic", "none"
	SMTPConnectTimeout time.Duration
	SMTPSendTimeout    time.Duration

	// IMAP settings
	IMAPEnabled      bool
	IMAPHost         string
	IMAPPort         int
	IMAPUsername     string
	IMAPPassword     string
	IMAPUseTLS       bool
	IMAPMailbox      string
	IMAPPollInterval time.Duration
	IMAPMarkAsSeen   bool

	// Queue & Persistence settings
	QueueDBPath            string
	QueueMaxRetries        int
	QueueBaseBackoff       time.Duration
	QueueMaxBackoff        time.Duration
	QueueWorkerConcurrency int
	QueuePollInterval      time.Duration

	// Attachment limits
	MaxAttachmentSizeBytes int64

	// Status & Inbound Event Webhook Forwarding
	StatusWebhookURL     string
	StatusWebhookSecret  string
	StatusWebhookTimeout time.Duration
}

// LoadFromEnv loads configuration from environment variables with sensible defaults.
func LoadFromEnv() *Config {
	return &Config{
		Host:        getEnv("HOST", "0.0.0.0"),
		Port:        getEnvAsInt("PORT", 8025),
		APIKey:      getEnv("MAIL_API_KEY", ""),
		Environment: getEnv("ENVIRONMENT", "development"),
		LogLevel:    getEnv("LOG_LEVEL", "info"),

		SMTPHost:           getEnv("SMTP_HOST", "127.0.0.1"),
		SMTPPort:           getEnvAsInt("SMTP_PORT", 1025),
		SMTPUsername:       getEnv("SMTP_USERNAME", ""),
		SMTPPassword:       getEnv("SMTP_PASSWORD", ""),
		SMTPFromEmail:      getEnv("SMTP_FROM_EMAIL", "noreply@vibecore.local"),
		SMTPFromName:       getEnv("SMTP_FROM_NAME", "VibeCore ERP"),
		SMTPTLSPolicy:      strings.ToLower(getEnv("SMTP_TLS_POLICY", "opportunistic")),
		SMTPConnectTimeout: getEnvAsDuration("SMTP_CONNECT_TIMEOUT", 10*time.Second),
		SMTPSendTimeout:    getEnvAsDuration("SMTP_SEND_TIMEOUT", 30*time.Second),

		IMAPEnabled:      getEnvAsBool("IMAP_ENABLED", false),
		IMAPHost:         getEnv("IMAP_HOST", ""),
		IMAPPort:         getEnvAsInt("IMAP_PORT", 993),
		IMAPUsername:     getEnv("IMAP_USERNAME", ""),
		IMAPPassword:     getEnv("IMAP_PASSWORD", ""),
		IMAPUseTLS:       getEnvAsBool("IMAP_USE_TLS", true),
		IMAPMailbox:      getEnv("IMAP_MAILBOX", "INBOX"),
		IMAPPollInterval: getEnvAsDuration("IMAP_POLL_INTERVAL", 30*time.Second),
		IMAPMarkAsSeen:   getEnvAsBool("IMAP_MARK_AS_SEEN", true),

		QueueDBPath:            getEnv("QUEUE_DB_PATH", "data/mail_queue.db"),
		QueueMaxRetries:        getEnvAsInt("QUEUE_MAX_RETRIES", 5),
		QueueBaseBackoff:       getEnvAsDuration("QUEUE_BASE_BACKOFF", 2*time.Second),
		QueueMaxBackoff:        getEnvAsDuration("QUEUE_MAX_BACKOFF", 60*time.Second),
		QueueWorkerConcurrency: getEnvAsInt("QUEUE_WORKER_CONCURRENCY", 2),
		QueuePollInterval:      getEnvAsDuration("QUEUE_POLL_INTERVAL", 1*time.Second),

		MaxAttachmentSizeBytes: int64(getEnvAsInt("MAX_ATTACHMENT_SIZE_MB", 25)) * 1024 * 1024,

		StatusWebhookURL:     getEnv("STATUS_WEBHOOK_URL", ""),
		StatusWebhookSecret:  getEnv("STATUS_WEBHOOK_SECRET", ""),
		StatusWebhookTimeout: getEnvAsDuration("STATUS_WEBHOOK_TIMEOUT", 10*time.Second),
	}
}

func getEnv(key, defaultVal string) string {
	if val, ok := os.LookupEnv(key); ok && val != "" {
		return val
	}
	return defaultVal
}

func getEnvAsInt(key string, defaultVal int) int {
	if valStr, ok := os.LookupEnv(key); ok && valStr != "" {
		if val, err := strconv.Atoi(valStr); err == nil {
			return val
		}
	}
	return defaultVal
}

func getEnvAsBool(key string, defaultVal bool) bool {
	if valStr, ok := os.LookupEnv(key); ok && valStr != "" {
		if val, err := strconv.ParseBool(valStr); err == nil {
			return val
		}
	}
	return defaultVal
}

func getEnvAsDuration(key string, defaultVal time.Duration) time.Duration {
	if valStr, ok := os.LookupEnv(key); ok && valStr != "" {
		if val, err := time.ParseDuration(valStr); err == nil {
			return val
		}
	}
	return defaultVal
}
