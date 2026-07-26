// Package llm talks to any OpenAI-compatible chat endpoint on behalf of the
// browser, so that the API key stays on this side of the wire.
//
// Copyright (c) 2026 Luka Gale. MIT licence — see LICENSE.
//
// Why "OpenAI-compatible" and not "LiteLLM": LiteLLM, Ollama, vLLM and
// OpenRouter all speak the same two endpoints this package needs
// (GET /v1/models, POST /v1/chat/completions). Targeting the shape instead of
// the product is less code and covers more ground. With LiteLLM in front, adding
// a provider — after burning a free tier, say — is an edit to LiteLLM's own
// model_list, and nothing here changes.
//
// The API key is never persisted through the workspace store. That store
// archives every write to .history/<key>/<stamp>.json and exists precisely so
// the files can be diffed and committed with ordinary tools; a key written there
// ends up in a commit and in every retained version. The key comes from the
// environment (a Secret, in a cluster) and lives only in memory.
//
// NOT COMPILED: written without a Go toolchain to hand. Run `gofmt -l`,
// `go vet ./...` and `go build ./...` before trusting it.
package llm

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Limits. Deliberately conservative; a browser is not a trusted caller even when
// it is the only caller.
const (
	maxRequestBytes  = 128 << 10 // 128 KiB of JSON from the browser
	maxResponseBytes = 8 << 20   // 8 MiB from the provider
	modelCacheTTL    = 5 * time.Minute
	defaultTimeout   = 90 // seconds; LLM calls are slow and that is normal
)

var (
	// ErrDisabled means no endpoint is configured. Not an error condition: AI
	// assistance is optional and the studio works without it.
	ErrDisabled = errors.New("ai assistance is not configured")
	// ErrBadRequest is anything the caller can fix by asking differently.
	ErrBadRequest = errors.New("bad request")
)

// Config holds the settings a user may change from the profile panel. None of
// these are secret. The key is not here, and there is no field for it, so it
// cannot be leaked by serialising this struct.
type Config struct {
	Enabled        bool    `json:"enabled"`
	BaseURL        string  `json:"baseUrl"`        // e.g. http://litellm:4000
	Model          string  `json:"model"`          // a model_name alias on the proxy
	TimeoutSeconds int     `json:"timeoutSeconds"` // 5..600
	MaxTokens      int     `json:"maxTokens"`      // 0 = let the provider decide
	Temperature    float64 `json:"temperature"`    // 0..2
}

func (c Config) timeout() time.Duration {
	s := c.TimeoutSeconds
	if s <= 0 {
		s = defaultTimeout
	}
	if s > 600 {
		s = 600
	}
	return time.Duration(s) * time.Second
}

// validate rejects a configuration rather than repairing it, for the same reason
// store.ValidName refuses odd names instead of sanitising them: a silently
// rewritten setting is a setting the user did not choose.
func (c Config) validate() error {
	if !c.Enabled {
		return nil
	}
	if strings.TrimSpace(c.BaseURL) == "" {
		return fmt.Errorf("%w: base URL is required when AI assistance is on", ErrBadRequest)
	}
	u, err := url.Parse(c.BaseURL)
	if err != nil {
		return fmt.Errorf("%w: base URL does not parse: %v", ErrBadRequest, err)
	}
	if u.Scheme != "http" && u.Scheme != "https" {
		return fmt.Errorf("%w: base URL scheme must be http or https", ErrBadRequest)
	}
	if u.Host == "" {
		return fmt.Errorf("%w: base URL has no host", ErrBadRequest)
	}
	if c.Temperature < 0 || c.Temperature > 2 {
		return fmt.Errorf("%w: temperature must be between 0 and 2", ErrBadRequest)
	}
	if c.MaxTokens < 0 {
		return fmt.Errorf("%w: maxTokens cannot be negative", ErrBadRequest)
	}
	return nil
}

// Status is what the profile panel is allowed to see. It reports whether a key
// is present, never what it is.
type Status struct {
	Config
	KeyPresent bool     `json:"keyPresent"`
	KeySource  string   `json:"keySource"` // "environment" or ""
	Models     []string `json:"models,omitempty"`
	LastError  string   `json:"lastError,omitempty"`
}

// ConfigStore persists the non-secret settings. Implement it over the existing
// workspace driver if you want per-profile settings; pass nil to keep the
// configuration in memory for the process lifetime.
type ConfigStore interface {
	LoadLLMConfig() (Config, error)
	SaveLLMConfig(Config) error
}

// Provider is safe for concurrent use.
type Provider struct {
	mu        sync.RWMutex
	cfg       Config
	key       string
	models    []string
	fetchedAt time.Time
	lastErr   string

	store ConfigStore
	hc    *http.Client
}

// New builds a Provider from the environment, then overlays anything the store
// has saved. Environment supplies the secret; the store supplies preferences.
//
//	KE_LLM_BASE_URL  http://litellm:4000
//	KE_LLM_KEY       sk-...            (LiteLLM master or virtual key)
//	KE_LLM_MODEL     default
//	KE_LLM_TIMEOUT   90                (seconds)
func New(store ConfigStore) *Provider {
	cfg := Config{
		BaseURL:        strings.TrimRight(os.Getenv("KE_LLM_BASE_URL"), "/"),
		Model:          os.Getenv("KE_LLM_MODEL"),
		TimeoutSeconds: defaultTimeout,
		Temperature:    0.2, // this tool extracts claims; it should not improvise
	}
	if v := os.Getenv("KE_LLM_TIMEOUT"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			cfg.TimeoutSeconds = n
		}
	}
	cfg.Enabled = cfg.BaseURL != ""

	p := &Provider{
		cfg:   cfg,
		key:   os.Getenv("KE_LLM_KEY"),
		store: store,
	}
	// One client, reused: a fresh http.Client per request leaks connections.
	// The default client has no timeout at all, which is how a hung provider
	// pins a goroutine and a browser request forever.
	// Timeout is a hard ceiling only. The real per-call deadline is the request
	// context, because mutating http.Client.Timeout after SetConfig while another
	// goroutine sits inside Do() is a data race.
	p.hc = &http.Client{
		Timeout: 610 * time.Second,
		Transport: &http.Transport{
			MaxIdleConns:        8,
			IdleConnTimeout:     60 * time.Second,
			TLSHandshakeTimeout: 10 * time.Second,
		},
	}
	if store != nil {
		if saved, err := store.LoadLLMConfig(); err == nil && saved.BaseURL != "" {
			saved.Enabled = saved.Enabled && (saved.BaseURL != "")
			p.cfg = saved
		}
	}
	return p
}

// Status reports the redacted configuration.
func (p *Provider) Status() Status {
	p.mu.RLock()
	defer p.mu.RUnlock()
	src := ""
	if p.key != "" {
		src = "environment"
	}
	return Status{
		Config:     p.cfg,
		KeyPresent: p.key != "",
		KeySource:  src,
		Models:     append([]string(nil), p.models...),
		LastError:  p.lastErr,
	}
}

// SetConfig replaces the non-secret settings.
func (p *Provider) SetConfig(next Config) error {
	if err := next.validate(); err != nil {
		return err
	}
	next.BaseURL = strings.TrimRight(next.BaseURL, "/")

	p.mu.Lock()
	p.cfg = next
	p.models = nil // force rediscovery against the new endpoint
	p.fetchedAt = time.Time{}
	p.lastErr = ""
	store := p.store
	p.mu.Unlock()

	if store != nil {
		return store.SaveLLMConfig(next)
	}
	return nil
}

func (p *Provider) snapshot() (Config, string) {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return p.cfg, p.key
}

func (p *Provider) note(err error) {
	p.mu.Lock()
	if err == nil {
		p.lastErr = ""
	} else {
		p.lastErr = err.Error()
	}
	p.mu.Unlock()
}

func (p *Provider) request(ctx context.Context, method, path string, body []byte) (*http.Request, error) {
	cfg, key := p.snapshot()
	if !cfg.Enabled || cfg.BaseURL == "" {
		return nil, ErrDisabled
	}
	var rdr io.Reader
	if body != nil {
		rdr = bytes.NewReader(body)
	}
	req, err := http.NewRequestWithContext(ctx, method, cfg.BaseURL+path, rdr)
	if err != nil {
		return nil, err
	}
	if key != "" {
		req.Header.Set("Authorization", "Bearer "+key)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	req.Header.Set("Accept", "application/json")
	return req, nil
}

// Models lists the model aliases the endpoint exposes, cached briefly.
// GET /v1/models is the OpenAI-compatible listing; LiteLLM also serves
// /v1/model/info with richer detail, which is not needed for a dropdown.
func (p *Provider) Models(ctx context.Context) ([]string, error) {
	p.mu.RLock()
	fresh := time.Since(p.fetchedAt) < modelCacheTTL && len(p.models) > 0
	cached := append([]string(nil), p.models...)
	p.mu.RUnlock()
	if fresh {
		return cached, nil
	}

	req, err := p.request(ctx, http.MethodGet, "/v1/models", nil)
	if err != nil {
		return nil, err
	}
	resp, err := p.hc.Do(req)
	if err != nil {
		p.note(err)
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		err = fmt.Errorf("model list: provider returned %s", resp.Status)
		p.note(err)
		return nil, err
	}
	var payload struct {
		Data []struct {
			ID string `json:"id"`
		} `json:"data"`
	}
	if err := json.NewDecoder(io.LimitReader(resp.Body, maxResponseBytes)).Decode(&payload); err != nil {
		p.note(err)
		return nil, fmt.Errorf("model list: %w", err)
	}
	names := make([]string, 0, len(payload.Data))
	for _, m := range payload.Data {
		if m.ID != "" {
			names = append(names, m.ID)
		}
	}

	p.mu.Lock()
	p.models = names
	p.fetchedAt = time.Now()
	p.lastErr = ""
	p.mu.Unlock()
	return names, nil
}

// Message is one turn. Content is a plain string: the multimodal content-array
// form is not accepted, because nothing in this tool sends images yet and every
// accepted shape is a shape that has to be validated.
type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// Ask is what the browser may send. Note what is absent: no base URL, no key, no
// arbitrary provider parameters. If the browser could set the base URL, this
// process would be an open HTTP proxy sitting inside the namespace, and no
// NetworkPolicy would notice, because the egress really is from this pod.
type Ask struct {
	Model    string    `json:"model,omitempty"`
	Messages []Message `json:"messages"`
	Stream   bool      `json:"stream,omitempty"`
}

func (a Ask) validate() error {
	if len(a.Messages) == 0 {
		return fmt.Errorf("%w: messages is empty", ErrBadRequest)
	}
	if len(a.Messages) > 64 {
		return fmt.Errorf("%w: too many messages", ErrBadRequest)
	}
	for i, m := range a.Messages {
		switch m.Role {
		case "system", "user", "assistant":
		default:
			return fmt.Errorf("%w: message %d has role %q", ErrBadRequest, i, m.Role)
		}
		if m.Content == "" {
			return fmt.Errorf("%w: message %d has no content", ErrBadRequest, i)
		}
	}
	return nil
}

// resolveModel picks the model and refuses one the endpoint does not advertise.
// If discovery fails the configured default is used, so a proxy that blocks
// /v1/models does not take chat down with it.
func (p *Provider) resolveModel(ctx context.Context, want string) (string, error) {
	cfg, _ := p.snapshot()
	if want == "" {
		if cfg.Model == "" {
			return "", fmt.Errorf("%w: no model requested and no default configured", ErrBadRequest)
		}
		return cfg.Model, nil
	}
	known, err := p.Models(ctx)
	if err != nil || len(known) == 0 {
		if cfg.Model != "" {
			return cfg.Model, nil
		}
		return "", fmt.Errorf("%w: cannot verify model %q", ErrBadRequest, want)
	}
	for _, k := range known {
		if k == want {
			return want, nil
		}
	}
	return "", fmt.Errorf("%w: model %q is not available on this endpoint", ErrBadRequest, want)
}

func (p *Provider) buildBody(model string, ask Ask, stream bool) ([]byte, error) {
	cfg, _ := p.snapshot()
	payload := map[string]any{
		"model":       model,
		"messages":    ask.Messages,
		"temperature": cfg.Temperature,
		"stream":      stream,
	}
	if cfg.MaxTokens > 0 {
		payload["max_tokens"] = cfg.MaxTokens
	}
	return json.Marshal(payload)
}

// Reply is the flattened non-streaming answer, plus the numbers the profile
// panel shows. "The free tier ran out" should read as a 429 naming the provider,
// not as "AI failed".
type Reply struct {
	Model            string `json:"model"`
	Text             string `json:"text"`
	FinishReason     string `json:"finishReason,omitempty"`
	PromptTokens     int    `json:"promptTokens"`
	CompletionTokens int    `json:"completionTokens"`
	LatencyMillis    int64  `json:"latencyMs"`
}

// Chat performs one non-streaming completion.
func (p *Provider) Chat(ctx context.Context, ask Ask) (*Reply, error) {
	if err := ask.validate(); err != nil {
		return nil, err
	}
	if _, ok := ctx.Deadline(); !ok {
		cfg, _ := p.snapshot()
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, cfg.timeout())
		defer cancel()
	}
	model, err := p.resolveModel(ctx, ask.Model)
	if err != nil {
		return nil, err
	}
	body, err := p.buildBody(model, ask, false)
	if err != nil {
		return nil, err
	}
	req, err := p.request(ctx, http.MethodPost, "/v1/chat/completions", body)
	if err != nil {
		return nil, err
	}

	started := time.Now()
	resp, err := p.hc.Do(req)
	if err != nil {
		p.note(err)
		return nil, err
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(io.LimitReader(resp.Body, maxResponseBytes))
	if err != nil {
		p.note(err)
		return nil, err
	}
	if resp.StatusCode != http.StatusOK {
		err = fmt.Errorf("provider %s: %s", resp.Status, providerMessage(raw))
		p.note(err)
		return nil, err
	}

	var payload struct {
		Model   string `json:"model"`
		Choices []struct {
			Message      Message `json:"message"`
			FinishReason string  `json:"finish_reason"`
		} `json:"choices"`
		Usage struct {
			PromptTokens     int `json:"prompt_tokens"`
			CompletionTokens int `json:"completion_tokens"`
		} `json:"usage"`
	}
	if err := json.Unmarshal(raw, &payload); err != nil {
		p.note(err)
		return nil, fmt.Errorf("provider sent something that is not a completion: %w", err)
	}
	if len(payload.Choices) == 0 {
		err = errors.New("provider returned no choices")
		p.note(err)
		return nil, err
	}
	p.note(nil)
	return &Reply{
		Model:            payload.Model,
		Text:             payload.Choices[0].Message.Content,
		FinishReason:     payload.Choices[0].FinishReason,
		PromptTokens:     payload.Usage.PromptTokens,
		CompletionTokens: payload.Usage.CompletionTokens,
		LatencyMillis:    time.Since(started).Milliseconds(),
	}, nil
}

// providerMessage digs the human-readable part out of an error body without
// echoing the whole thing back to the browser.
func providerMessage(raw []byte) string {
	var e struct {
		Error struct {
			Message string `json:"message"`
			Type    string `json:"type"`
		} `json:"error"`
		Detail string `json:"detail"`
	}
	if json.Unmarshal(raw, &e) == nil {
		if e.Error.Message != "" {
			return truncate(e.Error.Message, 300)
		}
		if e.Detail != "" {
			return truncate(e.Detail, 300)
		}
	}
	return truncate(strings.TrimSpace(string(raw)), 200)
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}

// Stream proxies a streaming completion to w as server-sent events. Without
// this, a long answer looks like a frozen UI.
func (p *Provider) Stream(ctx context.Context, w http.ResponseWriter, ask Ask) error {
	if err := ask.validate(); err != nil {
		return err
	}
	flusher, ok := w.(http.Flusher)
	if !ok {
		return errors.New("this server cannot stream (no Flusher); use the non-streaming endpoint")
	}
	model, err := p.resolveModel(ctx, ask.Model)
	if err != nil {
		return err
	}
	body, err := p.buildBody(model, ask, true)
	if err != nil {
		return err
	}
	req, err := p.request(ctx, http.MethodPost, "/v1/chat/completions", body)
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "text/event-stream")

	resp, err := p.hc.Do(req)
	if err != nil {
		p.note(err)
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 64<<10))
		err = fmt.Errorf("provider %s: %s", resp.Status, providerMessage(raw))
		p.note(err)
		return err
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("X-Accel-Buffering", "no") // some proxies buffer SSE to death
	w.WriteHeader(http.StatusOK)
	flusher.Flush()

	// Line-oriented copy so each chunk reaches the browser as it arrives.
	// Cannot use io.Copy: that buffers, which is exactly what streaming is for.
	br := bufio.NewReaderSize(resp.Body, 8<<10)
	for {
		select {
		case <-ctx.Done():
			return ctx.Err() // browser went away; stop paying for tokens
		default:
		}
		line, err := br.ReadBytes('\n')
		if len(line) > 0 {
			if _, werr := w.Write(line); werr != nil {
				return werr
			}
			flusher.Flush()
		}
		if err != nil {
			if errors.Is(err, io.EOF) {
				p.note(nil)
				return nil
			}
			p.note(err)
			return err
		}
	}
}

/* ------------------------------------------------------------------ handlers */

// Routes registers the endpoints. Mount them behind the same authentication
// middleware as everything else; /api/info is the only endpoint that stays open,
// because the readiness and liveness probes call it.
//
//	mux.Handle("/api/ai/", llmProvider.Routes())
func (p *Provider) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/ai/config", p.handleConfig)
	mux.HandleFunc("/api/ai/models", p.handleModels)
	mux.HandleFunc("/api/ai/test", p.handleTest)
	mux.HandleFunc("/api/ai/complete", p.handleComplete)
	return mux
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

// statusFor maps an error to a code once, in one place, the way store.ErrNotFound
// is mapped to 404 in the HTTP layer.
func statusFor(err error) int {
	switch {
	case errors.Is(err, ErrDisabled):
		return http.StatusServiceUnavailable
	case errors.Is(err, ErrBadRequest):
		return http.StatusBadRequest
	case errors.Is(err, context.DeadlineExceeded):
		return http.StatusGatewayTimeout
	default:
		return http.StatusBadGateway // the failure is upstream, not here
	}
}

func fail(w http.ResponseWriter, err error) {
	writeJSON(w, statusFor(err), map[string]string{"error": err.Error()})
}

func decode(w http.ResponseWriter, r *http.Request, dst any) error {
	dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, maxRequestBytes))
	dec.DisallowUnknownFields() // a typo'd field is a bug, not a default
	if err := dec.Decode(dst); err != nil {
		return fmt.Errorf("%w: %v", ErrBadRequest, err)
	}
	return nil
}

func (p *Provider) handleConfig(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		writeJSON(w, http.StatusOK, p.Status())
	case http.MethodPut:
		var next Config
		if err := decode(w, r, &next); err != nil {
			fail(w, err)
			return
		}
		if err := p.SetConfig(next); err != nil {
			fail(w, err)
			return
		}
		writeJSON(w, http.StatusOK, p.Status())
	default:
		w.Header().Set("Allow", "GET, PUT")
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

func (p *Provider) handleModels(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", "GET")
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 20*time.Second)
	defer cancel()
	models, err := p.Models(ctx)
	if err != nil {
		fail(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"models": models})
}

// handleTest is the button in the profile panel. It says which endpoint, which
// model, and how long, so a misconfiguration is diagnosable without logs.
func (p *Provider) handleTest(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "POST")
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 60*time.Second)
	defer cancel()

	reply, err := p.Chat(ctx, Ask{Messages: []Message{
		{Role: "user", Content: "Reply with the single word: ready"},
	}})
	if err != nil {
		fail(w, err)
		return
	}
	cfg, _ := p.snapshot()
	writeJSON(w, http.StatusOK, map[string]any{
		"ok":        true,
		"endpoint":  cfg.BaseURL,
		"model":     reply.Model,
		"latencyMs": reply.LatencyMillis,
		"reply":     strings.TrimSpace(reply.Text),
	})
}

func (p *Provider) handleComplete(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "POST")
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var ask Ask
	if err := decode(w, r, &ask); err != nil {
		fail(w, err)
		return
	}

	cfg, _ := p.snapshot()
	// r.Context() is cancelled when the browser disconnects, so a closed tab
	// cancels the upstream call instead of burning tokens on nobody.
	ctx, cancel := context.WithTimeout(r.Context(), cfg.timeout())
	defer cancel()

	if ask.Stream {
		if err := p.Stream(ctx, w, ask); err != nil {
			// Headers may already be sent; there is no honest way to change the
			// status now, so report in-band and let the client show it.
			if !errors.Is(err, context.Canceled) {
				fmt.Fprintf(w, "event: error\ndata: %s\n\n", strings.ReplaceAll(err.Error(), "\n", " "))
				if f, ok := w.(http.Flusher); ok {
					f.Flush()
				}
			}
		}
		return
	}

	reply, err := p.Chat(ctx, ask)
	if err != nil {
		fail(w, err)
		return
	}
	writeJSON(w, http.StatusOK, reply)
}
