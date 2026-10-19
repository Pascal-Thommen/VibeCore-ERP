package queue

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/Pascal-Thommen/VibeCore-ERP/adapters/mail/internal/models"
	bolt "go.etcd.io/bbolt"
)

var (
	bucketMails       = []byte("queued_mails")
	bucketIdempotency = []byte("idempotency")
)

// ErrNotFound indicates an item was not located in the queue database.
var ErrNotFound = errors.New("mail item not found in queue")

// ErrDuplicateIdempotency indicates an item with the same idempotency key was already queued.
var ErrDuplicateIdempotency = errors.New("idempotency key already exists")

// BoltQueue implements a durable, ACID-compliant persistent queue backed by bbolt.
type BoltQueue struct {
	db *bolt.DB
	mu sync.RWMutex
}

// NewBoltQueue opens or creates a bbolt database at dbPath and initializes buckets.
func NewBoltQueue(dbPath string) (*BoltQueue, error) {
	dir := filepath.Dir(dbPath)
	if dir != "" && dir != "." {
		if err := os.MkdirAll(dir, 0755); err != nil {
			return nil, fmt.Errorf("failed creating directory for queue database '%s': %w", dir, err)
		}
	}

	db, err := bolt.Open(dbPath, 0600, &bolt.Options{Timeout: 5 * time.Second})
	if err != nil {
		return nil, fmt.Errorf("failed opening bbolt queue database at '%s': %w", dbPath, err)
	}

	err = db.Update(func(tx *bolt.Tx) error {
		if _, err := tx.CreateBucketIfNotExists(bucketMails); err != nil {
			return err
		}
		if _, err := tx.CreateBucketIfNotExists(bucketIdempotency); err != nil {
			return err
		}
		return nil
	})
	if err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("failed creating buckets in queue database: %w", err)
	}

	return &BoltQueue{db: db}, nil
}

// Enqueue stores a new mail item atomically, associating idempotency key if provided.
func (q *BoltQueue) Enqueue(ctx context.Context, item *models.QueuedMail) error {
	q.mu.Lock()
	defer q.mu.Unlock()

	return q.db.Update(func(tx *bolt.Tx) error {
		bMails := tx.Bucket(bucketMails)
		bIdem := tx.Bucket(bucketIdempotency)

		if item.IdempotencyKey != "" {
			existingID := bIdem.Get([]byte(item.IdempotencyKey))
			if existingID != nil {
				return ErrDuplicateIdempotency
			}
		}

		data, err := json.Marshal(item)
		if err != nil {
			return fmt.Errorf("failed serializing queued mail: %w", err)
		}

		if err := bMails.Put([]byte(item.ID), data); err != nil {
			return err
		}

		if item.IdempotencyKey != "" {
			if err := bIdem.Put([]byte(item.IdempotencyKey), []byte(item.ID)); err != nil {
				return err
			}
		}

		return nil
	})
}

// Get retrieves a queued mail by ID.
func (q *BoltQueue) Get(ctx context.Context, id string) (*models.QueuedMail, error) {
	q.mu.RLock()
	defer q.mu.RUnlock()

	var item *models.QueuedMail
	err := q.db.View(func(tx *bolt.Tx) error {
		b := tx.Bucket(bucketMails)
		data := b.Get([]byte(id))
		if data == nil {
			return ErrNotFound
		}

		item = &models.QueuedMail{}
		return json.Unmarshal(data, item)
	})

	if err != nil {
		return nil, err
	}
	return item, nil
}

// GetByIdempotencyKey retrieves a queued mail using its idempotency key.
func (q *BoltQueue) GetByIdempotencyKey(ctx context.Context, key string) (*models.QueuedMail, error) {
	q.mu.RLock()
	defer q.mu.RUnlock()

	var item *models.QueuedMail
	err := q.db.View(func(tx *bolt.Tx) error {
		bIdem := tx.Bucket(bucketIdempotency)
		mailID := bIdem.Get([]byte(key))
		if mailID == nil {
			return ErrNotFound
		}

		bMails := tx.Bucket(bucketMails)
		data := bMails.Get(mailID)
		if data == nil {
			return ErrNotFound
		}

		item = &models.QueuedMail{}
		return json.Unmarshal(data, item)
	})

	if err != nil {
		return nil, err
	}
	return item, nil
}

// Update updates an existing mail record atomically.
func (q *BoltQueue) Update(ctx context.Context, item *models.QueuedMail) error {
	q.mu.Lock()
	defer q.mu.Unlock()

	return q.db.Update(func(tx *bolt.Tx) error {
		b := tx.Bucket(bucketMails)
		if b.Get([]byte(item.ID)) == nil {
			return ErrNotFound
		}

		item.UpdatedAt = time.Now()
		data, err := json.Marshal(item)
		if err != nil {
			return fmt.Errorf("failed serializing queued mail: %w", err)
		}

		return b.Put([]byte(item.ID), data)
	})
}

// ClaimPending atomically finds pending mails, marks them SENDING, and returns them.
func (q *BoltQueue) ClaimPending(ctx context.Context, limit int) ([]*models.QueuedMail, error) {
	q.mu.Lock()
	defer q.mu.Unlock()

	var claimed []*models.QueuedMail
	now := time.Now()

	err := q.db.Update(func(tx *bolt.Tx) error {
		b := tx.Bucket(bucketMails)
		c := b.Cursor()

		for k, v := c.First(); k != nil; k, v = c.Next() {
			var m models.QueuedMail
			if err := json.Unmarshal(v, &m); err != nil {
				continue
			}

			if m.State == models.MailStateQueued && (m.NextAttemptAt.IsZero() || m.NextAttemptAt.Before(now) || m.NextAttemptAt.Equal(now)) {
				m.State = models.MailStateSending
				m.Attempts++
				m.UpdatedAt = now

				data, err := json.Marshal(m)
				if err != nil {
					return err
				}
				if err := b.Put(k, data); err != nil {
					return err
				}

				claimed = append(claimed, &m)
				if limit > 0 && len(claimed) >= limit {
					break
				}
			}
		}
		return nil
	})

	if err != nil {
		return nil, err
	}
	return claimed, nil
}

// GetPending returns mail items ready for transmission (status QUEUED and next_attempt_at <= now).
func (q *BoltQueue) GetPending(ctx context.Context, limit int) ([]*models.QueuedMail, error) {
	q.mu.RLock()
	defer q.mu.RUnlock()

	var pending []*models.QueuedMail
	now := time.Now()

	err := q.db.View(func(tx *bolt.Tx) error {
		b := tx.Bucket(bucketMails)
		c := b.Cursor()

		for k, v := c.First(); k != nil; k, v = c.Next() {
			var m models.QueuedMail
			if err := json.Unmarshal(v, &m); err != nil {
				continue
			}

			if m.State == models.MailStateQueued && (m.NextAttemptAt.IsZero() || m.NextAttemptAt.Before(now) || m.NextAttemptAt.Equal(now)) {
				pending = append(pending, &m)
				if limit > 0 && len(pending) >= limit {
					break
				}
			}
		}
		return nil
	})

	if err != nil {
		return nil, err
	}
	return pending, nil
}

// RecoverInflight resets any items left in 'SENDING' state (from a crash or sudden restart) back to 'QUEUED'.
func (q *BoltQueue) RecoverInflight(ctx context.Context) (int, error) {
	q.mu.Lock()
	defer q.mu.Unlock()

	recovered := 0
	err := q.db.Update(func(tx *bolt.Tx) error {
		b := tx.Bucket(bucketMails)
		c := b.Cursor()

		for k, v := c.First(); k != nil; k, v = c.Next() {
			var m models.QueuedMail
			if err := json.Unmarshal(v, &m); err != nil {
				continue
			}

			if m.State == models.MailStateSending {
				m.State = models.MailStateQueued
				m.UpdatedAt = time.Now()
				data, err := json.Marshal(m)
				if err != nil {
					return err
				}
				if err := b.Put(k, data); err != nil {
					return err
				}
				recovered++
			}
		}
		return nil
	})

	return recovered, err
}

// Close closes the underlying bbolt database safely.
func (q *BoltQueue) Close() error {
	q.mu.Lock()
	defer q.mu.Unlock()
	return q.db.Close()
}
