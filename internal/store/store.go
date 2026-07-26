// Package store holds the persistence layer for Knowledge Engineering Studio.
//
// Copyright (c) 2026 Luka Gale. MIT licence — see LICENSE.
//
// The Driver interface exists so that the local filesystem is one option rather
// than the only one. It is deliberately small: eight methods, all of them about
// bytes under a name. Anything richer than that (queries, transactions,
// per-field updates) belongs in a database driver, and if that day comes the
// interface should grow on purpose rather than by accident.
//
// Only LocalFS is implemented today. An S3 or Postgres driver would satisfy the
// same interface and the HTTP layer above would not change.
package store

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"
)

// ErrNotFound is returned for a key or profile that does not exist. The HTTP
// layer maps it to 404; every other error becomes a 500.
var ErrNotFound = errors.New("not found")

// Version is a stored value at a point in time.
type Version struct {
	Stamp string `json:"stamp"`
	Bytes int64  `json:"bytes"`
}

// ProfileInfo is what the workspace picker shows before anything is opened.
type ProfileInfo struct {
	Name     string `json:"name"`
	Models   int    `json:"models"`
	Bytes    int64  `json:"bytes"`
	Modified string `json:"modified"`
}

// Driver is the persistence contract.
type Driver interface {
	Profiles() ([]ProfileInfo, error)
	CreateProfile(name string) error
	Workspace(profile string) (map[string]json.RawMessage, error)
	Put(profile, key string, value json.RawMessage) error
	Delete(profile, key string) error
	Purge(profile string) error
	History(profile, key string) ([]Version, error)
	HistoryAt(profile, key, stamp string) (json.RawMessage, error)
}

// Names that become directory or file components are checked against this
// rather than sanitised. Silently rewriting a name the user typed produces a
// workspace under a name they did not choose, which is worse than refusing.
var nameRe = regexp.MustCompile(`^[A-Za-z0-9_-]{1,40}$`)

// ValidName reports whether s is safe to use as a path component.
//
// The regexp already excludes "." and ".." (no dots are permitted at all) and
// every separator on every platform, so path traversal is not reachable from a
// name that passes. The explicit length bound keeps a pathological name from
// blowing the filesystem's own limit.
func ValidName(s string) bool { return nameRe.MatchString(s) }

// LocalFS stores each profile as a directory of JSON files:
//
//	<root>/profiles/<profile>/models.json
//	<root>/profiles/<profile>/perspectives.json
//	<root>/profiles/<profile>/.history/models/20260724T143205Z.json
//
// Plain files on purpose. They can be read, diffed, copied and committed with
// ordinary tools while the application is running, which is most of the reason
// to run this against a volume rather than against localStorage.
type LocalFS struct {
	Root       string
	KeepPerKey int // versions retained per key; <= 0 means keep everything

	mu sync.Mutex // serialises writes; one browser tab does not need more
}

// NewLocalFS prepares root and verifies it can actually be written to. A
// permission problem surfaces here, at startup, rather than on the user's first
// save an hour later.
func NewLocalFS(root string, keep int) (*LocalFS, error) {
	abs, err := filepath.Abs(root)
	if err != nil {
		return nil, err
	}
	if err := os.MkdirAll(filepath.Join(abs, "profiles"), 0o755); err != nil {
		return nil, fmt.Errorf("create %s: %w", abs, err)
	}
	probe := filepath.Join(abs, ".writable")
	if err := os.WriteFile(probe, []byte("ok"), 0o644); err != nil {
		return nil, fmt.Errorf("data directory is not writable: %w", err)
	}
	_ = os.Remove(probe)
	return &LocalFS{Root: abs, KeepPerKey: keep}, nil
}

func (l *LocalFS) profileDir(p string) string { return filepath.Join(l.Root, "profiles", p) }
func (l *LocalFS) keyPath(p, k string) string { return filepath.Join(l.profileDir(p), k+".json") }
func (l *LocalFS) histDir(p, k string) string { return filepath.Join(l.profileDir(p), ".history", k) }

func (l *LocalFS) Profiles() ([]ProfileInfo, error) {
	base := filepath.Join(l.Root, "profiles")
	entries, err := os.ReadDir(base)
	if err != nil {
		if os.IsNotExist(err) {
			return []ProfileInfo{}, nil
		}
		return nil, err
	}
	out := []ProfileInfo{}
	for _, e := range entries {
		if !e.IsDir() || !ValidName(e.Name()) {
			continue
		}
		info := ProfileInfo{Name: e.Name()}
		files, err := os.ReadDir(filepath.Join(base, e.Name()))
		if err != nil {
			continue
		}
		var newest time.Time
		for _, f := range files {
			if f.IsDir() || !strings.HasSuffix(f.Name(), ".json") {
				continue
			}
			fi, err := f.Info()
			if err != nil {
				continue
			}
			info.Bytes += fi.Size()
			if fi.ModTime().After(newest) {
				newest = fi.ModTime()
			}
		}
		if !newest.IsZero() {
			info.Modified = newest.UTC().Format("2006-01-02 15:04")
		}
		info.Models = l.countModels(e.Name())
		out = append(out, info)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Name < out[j].Name })
	return out, nil
}

// countModels reads models.json only far enough to count the array. A corrupt
// or hand-edited file reports zero rather than failing the whole listing —
// the picker is not the right place to surface a parse error.
func (l *LocalFS) countModels(profile string) int {
	b, err := os.ReadFile(l.keyPath(profile, "models"))
	if err != nil {
		return 0
	}
	var arr []json.RawMessage
	if json.Unmarshal(b, &arr) != nil {
		return 0
	}
	return len(arr)
}

func (l *LocalFS) CreateProfile(name string) error {
	if !ValidName(name) {
		return fmt.Errorf("invalid profile name")
	}
	return os.MkdirAll(l.profileDir(name), 0o755)
}

func (l *LocalFS) Workspace(profile string) (map[string]json.RawMessage, error) {
	if !ValidName(profile) {
		return nil, fmt.Errorf("invalid profile name")
	}
	dir := l.profileDir(profile)
	entries, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, ErrNotFound
		}
		return nil, err
	}
	out := map[string]json.RawMessage{}
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		key := strings.TrimSuffix(e.Name(), ".json")
		if !ValidName(key) {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			continue
		}
		// A file that will not parse is skipped, not fatal. Losing one key beats
		// refusing to open the workspace at all, and the file is still on disk
		// for the user to inspect.
		if !json.Valid(b) {
			continue
		}
		out[key] = json.RawMessage(b)
	}
	return out, nil
}

// Put writes the value and lands a timestamped copy in .history/.
//
// The write is atomic: a temp file in the same directory, then rename. A crash
// mid-write leaves the previous version intact rather than a truncated file,
// which matters because the previous version is the user's work.
func (l *LocalFS) Put(profile, key string, value json.RawMessage) error {
	if !ValidName(profile) || !ValidName(key) {
		return fmt.Errorf("invalid profile or key name")
	}
	if !json.Valid(value) {
		return fmt.Errorf("value is not valid JSON")
	}
	l.mu.Lock()
	defer l.mu.Unlock()

	if err := os.MkdirAll(l.profileDir(profile), 0o755); err != nil {
		return err
	}
	final := l.keyPath(profile, key)

	tmp, err := os.CreateTemp(l.profileDir(profile), "."+key+".*.tmp")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	defer os.Remove(tmpName) // no-op once the rename has succeeded

	if _, err := tmp.Write(value); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if err := os.Rename(tmpName, final); err != nil {
		return err
	}
	return l.archive(profile, key, value)
}

func (l *LocalFS) archive(profile, key string, value json.RawMessage) error {
	dir := l.histDir(profile, key)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	stamp := time.Now().UTC().Format("20060102T150405Z")
	path := filepath.Join(dir, stamp+".json")
	// Same second, same file: two saves inside one second collapse into one
	// version rather than failing. That is the right trade — a debounced client
	// can legitimately produce two writes a few hundred milliseconds apart.
	if err := os.WriteFile(path, value, 0o644); err != nil {
		return err
	}
	return l.prune(dir)
}

func (l *LocalFS) prune(dir string) error {
	if l.KeepPerKey <= 0 {
		return nil
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return err
	}
	names := []string{}
	for _, e := range entries {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".json") {
			names = append(names, e.Name())
		}
	}
	if len(names) <= l.KeepPerKey {
		return nil
	}
	sort.Strings(names) // stamps are lexicographically ordered by design
	for _, n := range names[:len(names)-l.KeepPerKey] {
		_ = os.Remove(filepath.Join(dir, n))
	}
	return nil
}

func (l *LocalFS) Delete(profile, key string) error {
	if !ValidName(profile) || !ValidName(key) {
		return fmt.Errorf("invalid profile or key name")
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	err := os.Remove(l.keyPath(profile, key))
	if err != nil && os.IsNotExist(err) {
		return nil // deleting what is already gone is a success
	}
	return err
}

// Purge removes the whole profile directory, history included. A purge that
// leaves .history/ behind is not a purge, and the confirmation dialogue in the
// UI promises that it does not.
func (l *LocalFS) Purge(profile string) error {
	if !ValidName(profile) {
		return fmt.Errorf("invalid profile name")
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	if err := os.RemoveAll(l.profileDir(profile)); err != nil {
		return err
	}
	return os.MkdirAll(l.profileDir(profile), 0o755)
}

func (l *LocalFS) History(profile, key string) ([]Version, error) {
	if !ValidName(profile) || !ValidName(key) {
		return nil, fmt.Errorf("invalid profile or key name")
	}
	entries, err := os.ReadDir(l.histDir(profile, key))
	if err != nil {
		if os.IsNotExist(err) {
			return []Version{}, nil
		}
		return nil, err
	}
	out := []Version{}
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		fi, err := e.Info()
		if err != nil {
			continue
		}
		out = append(out, Version{Stamp: strings.TrimSuffix(e.Name(), ".json"), Bytes: fi.Size()})
	}
	// Newest first: the version you want is almost always the last one written.
	sort.Slice(out, func(i, j int) bool { return out[i].Stamp > out[j].Stamp })
	return out, nil
}

var stampRe = regexp.MustCompile(`^[0-9]{8}T[0-9]{6}Z$`)

func (l *LocalFS) HistoryAt(profile, key, stamp string) (json.RawMessage, error) {
	if !ValidName(profile) || !ValidName(key) || !stampRe.MatchString(stamp) {
		return nil, fmt.Errorf("invalid profile, key or stamp")
	}
	b, err := os.ReadFile(filepath.Join(l.histDir(profile, key), stamp+".json"))
	if err != nil {
		if os.IsNotExist(err) {
			return nil, ErrNotFound
		}
		return nil, err
	}
	return json.RawMessage(b), nil
}
