// Knowledge Engineering Studio — local server.
//
// Copyright (c) 2026 Luka Gale. MIT licence — see LICENSE.
//
// One binary. It embeds the frontend and the sample models, and it writes the
// workspace as plain JSON files into a directory you mount. There are no
// third-party Go dependencies on purpose: `go build` works offline, with no
// module download and no supply chain beyond the standard library.
//
// It binds to loopback by default. This is a single-user tool with no
// authentication, and a tool with no authentication should not be reachable
// from the network unless somebody deliberately says so.
package main

import (
	"embed"
	"bytes"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"path"
	"strconv"
	"strings"
	"syscall"
	"time"

	"kestudio/internal/store"
)

//go:embed all:web
var webFS embed.FS

//go:embed samples/*.json
var sampleFS embed.FS

const version = "0.14.0"

// Samples are embedded rather than mounted so that a fresh container can offer
// them without the user having to supply anything. They are read-only; loading
// one copies it into the workspace, and the copy is what gets edited.
type sampleMeta struct {
	Key        string `json:"key"`
	File       string `json:"file"`
	Name       string `json:"name"`
	Nodes      int    `json:"nodes"`
	Edges      int    `json:"edges"`
	Layers     int    `json:"layers"`
	CrossLayer int    `json:"crossLayer"`
}

type model struct {
	ID     string `json:"id"`
	Name   string `json:"name"`
	Layers []struct {
		ID string `json:"id"`
	} `json:"layers"`
	Nodes []struct {
		ID    string `json:"id"`
		Layer string `json:"layer"`
	} `json:"nodes"`
	Edges []struct {
		From string `json:"from"`
		To   string `json:"to"`
	} `json:"edges"`
}

type server struct {
	db      store.Driver
	dataDir string
	samples []sampleMeta
}

func main() {
	var (
		addr    = flag.String("addr", envOr("KE_ADDR", "127.0.0.1:8080"), "listen address")
		dataDir = flag.String("data", envOr("KE_DATA", "./data"), "workspace directory")
		keep    = flag.Int("keep", envOrInt("KE_KEEP_VERSIONS", 50), "history versions kept per key; 0 keeps all")
	)
	flag.Parse()

	db, err := store.NewLocalFS(*dataDir, *keep)
	if err != nil {
		log.Fatalf("storage: %v", err)
	}
	srv := &server{db: db, dataDir: db.Root}
	if srv.samples, err = loadSampleIndex(); err != nil {
		log.Printf("samples: %v (continuing without them)", err)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/api/info", srv.handleInfo)
	mux.HandleFunc("/api/profiles", srv.handleProfiles)
	mux.HandleFunc("/api/workspace", srv.handleWorkspace)
	mux.HandleFunc("/api/workspace/", srv.handleWorkspaceKey)
	mux.HandleFunc("/api/history/", srv.handleHistory)
	mux.HandleFunc("/api/llm/chat", srv.handleLLM)
	mux.HandleFunc("/api/llm/models", srv.handleLLMModels)
	mux.HandleFunc("/api/samples", srv.handleSamples)
	mux.HandleFunc("/api/samples/", srv.handleSampleFile)
	mux.HandleFunc("/", srv.handleStatic)

	h := &http.Server{
		Addr:              *addr,
		Handler:           logRequests(noStore(mux)),
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       60 * time.Second,
		WriteTimeout:      60 * time.Second,
		IdleTimeout:       120 * time.Second,
	}

	log.Printf("Pennant %s", version)
	log.Printf("  data      %s", srv.dataDir)
	log.Printf("  history   %d versions per key", *keep)
	log.Printf("  samples   %d", len(srv.samples))
	if base := os.Getenv("KE_LLM_BASE_URL"); base != "" {
		log.Printf("  llm       %s (pinned; the page cannot change it)", base)
	}
	if os.Getenv("KE_LLM_KEY") != "" {
		log.Printf("  llm key   present (AI assistance available if enabled in the UI)")
		if os.Getenv("KE_LLM_BASE_URL") == "" {
			log.Printf("  WARNING: KE_LLM_KEY is set without KE_LLM_BASE_URL. AI calls will be")
			log.Printf("           refused, because the key would be sent to whatever address the")
			log.Printf("           page asks for. Pin the endpoint to enable it.")
		}
	}
	log.Printf("  listening http://%s", *addr)
	if !strings.HasPrefix(*addr, "127.0.0.1") && !strings.HasPrefix(*addr, "localhost") {
		log.Printf("  NOTE: bound beyond loopback. There is no authentication in this build;")
		log.Printf("        anyone who can reach this address can read and delete every workspace.")
	}

	go func() {
		if err := h.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("listen: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	<-stop
	log.Print("shutting down")
	_ = h.Close()
}

func envOr(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

func envOrInt(k string, d int) int {
	if v := os.Getenv(k); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return d
}

// ── middleware ──────────────────────────────────────────────────────────────

func logRequests(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		next.ServeHTTP(w, r)
		if strings.HasPrefix(r.URL.Path, "/api/") {
			log.Printf("%s %s %s", r.Method, r.URL.Path, time.Since(start).Round(time.Millisecond))
		}
	})
}

// The workspace must never be served from a cache: a stale models.json read
// after a restore would silently undo the restore.
func noStore(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.HasPrefix(r.URL.Path, "/api/") {
			w.Header().Set("Cache-Control", "no-store")
		}
		next.ServeHTTP(w, r)
	})
}

// ── helpers ─────────────────────────────────────────────────────────────────

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	if err := json.NewEncoder(w).Encode(v); err != nil {
		log.Printf("encode: %v", err)
	}
}

func writeRaw(w http.ResponseWriter, b []byte) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	_, _ = w.Write(b)
}

func fail(w http.ResponseWriter, code int, msg string) {
	http.Error(w, msg, code)
}

// profileOf reads and validates the ?profile= parameter. Every workspace call
// carries it; there is no session, so there is nothing else it could come from.
func profileOf(w http.ResponseWriter, r *http.Request) (string, bool) {
	p := r.URL.Query().Get("profile")
	if !store.ValidName(p) {
		fail(w, http.StatusBadRequest, "missing or invalid profile")
		return "", false
	}
	return p, true
}

func mapErr(w http.ResponseWriter, err error) {
	if errors.Is(err, store.ErrNotFound) {
		fail(w, http.StatusNotFound, "not found")
		return
	}
	log.Printf("error: %v", err)
	fail(w, http.StatusInternalServerError, err.Error())
}

// ── handlers ────────────────────────────────────────────────────────────────

func (s *server) handleInfo(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, map[string]any{
		"version":  version,
		"dataDir":  s.dataDir,
		"writable": true, // NewLocalFS refuses to start otherwise
		"samples":  len(s.samples),
		// What the page is allowed to know about AI assistance. Whether a key
		// exists, never the key. "locked" tells the page the endpoint was pinned
		// by whoever runs the server, so it must not offer to change it.
		"llm": map[string]any{
			"keyPresent": os.Getenv("KE_LLM_KEY") != "",
			"baseUrl":    strings.TrimSuffix(os.Getenv("KE_LLM_BASE_URL"), "/"),
			"model":      os.Getenv("KE_LLM_MODEL"),
			"locked":     os.Getenv("KE_LLM_BASE_URL") != "",
		},
	})
}

func (s *server) handleProfiles(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		ps, err := s.db.Profiles()
		if err != nil {
			mapErr(w, err)
			return
		}
		writeJSON(w, ps)

	case http.MethodPost:
		var body struct {
			Name string `json:"name"`
		}
		if err := json.NewDecoder(io.LimitReader(r.Body, 1<<12)).Decode(&body); err != nil {
			fail(w, http.StatusBadRequest, "bad body")
			return
		}
		if !store.ValidName(body.Name) {
			fail(w, http.StatusBadRequest, "name must be 1-40 chars: letters, digits, dash, underscore")
			return
		}
		if err := s.db.CreateProfile(body.Name); err != nil {
			mapErr(w, err)
			return
		}
		writeJSON(w, map[string]string{"name": body.Name})

	default:
		fail(w, http.StatusMethodNotAllowed, "")
	}
}

func (s *server) handleWorkspace(w http.ResponseWriter, r *http.Request) {
	profile, ok := profileOf(w, r)
	if !ok {
		return
	}
	switch r.Method {
	case http.MethodGet:
		ws, err := s.db.Workspace(profile)
		if err != nil {
			mapErr(w, err)
			return
		}
		writeJSON(w, ws)

	case http.MethodDelete:
		if err := s.db.Purge(profile); err != nil {
			mapErr(w, err)
			return
		}
		log.Printf("purged workspace %q", profile)
		writeJSON(w, map[string]bool{"purged": true})

	default:
		fail(w, http.StatusMethodNotAllowed, "")
	}
}

func (s *server) handleWorkspaceKey(w http.ResponseWriter, r *http.Request) {
	profile, ok := profileOf(w, r)
	if !ok {
		return
	}
	key := strings.TrimPrefix(r.URL.Path, "/api/workspace/")
	if !store.ValidName(key) {
		fail(w, http.StatusBadRequest, "invalid key")
		return
	}
	switch r.Method {
	case http.MethodPut, http.MethodPost: // POST for sendBeacon, which cannot send PUT
		var body struct {
			Value json.RawMessage `json:"value"`
		}
		// 32 MB ceiling. Generous for a knowledge model and small enough that a
		// runaway client cannot exhaust memory.
		if err := json.NewDecoder(io.LimitReader(r.Body, 32<<20)).Decode(&body); err != nil {
			fail(w, http.StatusBadRequest, "bad body: "+err.Error())
			return
		}
		if len(body.Value) == 0 {
			fail(w, http.StatusBadRequest, "missing value")
			return
		}
		if err := s.db.Put(profile, key, body.Value); err != nil {
			mapErr(w, err)
			return
		}
		writeJSON(w, map[string]any{"key": key, "bytes": len(body.Value)})

	case http.MethodDelete:
		if err := s.db.Delete(profile, key); err != nil {
			mapErr(w, err)
			return
		}
		writeJSON(w, map[string]bool{"deleted": true})

	default:
		fail(w, http.StatusMethodNotAllowed, "")
	}
}

// /api/history/{key}            → list of versions
// /api/history/{key}/{stamp}    → the value at that version
func (s *server) handleHistory(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		fail(w, http.StatusMethodNotAllowed, "")
		return
	}
	profile, ok := profileOf(w, r)
	if !ok {
		return
	}
	rest := strings.TrimPrefix(r.URL.Path, "/api/history/")
	parts := strings.SplitN(rest, "/", 2)
	key := parts[0]
	if !store.ValidName(key) {
		fail(w, http.StatusBadRequest, "invalid key")
		return
	}
	if len(parts) == 1 || parts[1] == "" {
		vs, err := s.db.History(profile, key)
		if err != nil {
			mapErr(w, err)
			return
		}
		writeJSON(w, vs)
		return
	}
	v, err := s.db.HistoryAt(profile, key, parts[1])
	if err != nil {
		mapErr(w, err)
		return
	}
	writeRaw(w, v)
}

// llmEndpoint decides where an outbound call is allowed to go.
//
// The rule exists because of what this handler does with KE_LLM_KEY: it attaches
// it as a bearer token to whatever address it is given. When the browser chooses
// that address, "give me a completion" becomes "post my server's API key to a
// host of your choosing" — and there is no authentication in front of this
// process, so the browser is not a trusted caller.
//
//	KE_LLM_BASE_URL set   the only address this process will talk to; whatever
//	                      the page sends is ignored.
//	key set, no pin       refused. There is a credential to lose and nowhere
//	                      safe to send it.
//	no key                the typed address is used. There is nothing to steal,
//	                      and this is the ordinary case: Ollama on your own
//	                      machine, no key at all.
//
// It is not a general SSRF fix — a pinned endpoint is still an outbound call —
// but it removes the credential from the attacker's reach, which is the part
// that cannot be undone once it has happened.
func llmEndpoint(requested string) (string, error) {
	if pinned := strings.TrimSuffix(os.Getenv("KE_LLM_BASE_URL"), "/"); pinned != "" {
		return pinned, nil
	}
	if os.Getenv("KE_LLM_KEY") != "" {
		return "", errors.New("KE_LLM_KEY is set but KE_LLM_BASE_URL is not: pin the endpoint so the key can only be sent there")
	}
	if requested == "" {
		return "", errors.New("baseUrl is required")
	}
	return strings.TrimSuffix(requested, "/"), nil
}

// llmURL keeps the call to http(s) with a host. A typed address is a deliberate
// outbound call; it should not become a way to reach other schemes.
func llmURL(base string) (*url.URL, error) {
	u, err := url.Parse(base)
	if err != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Host == "" {
		return nil, errors.New("endpoint must be an http or https URL")
	}
	return u, nil
}

// handleLLMModels asks the endpoint which models it will accept.
//
// Every OpenAI-compatible server answers GET /models. Behind LiteLLM the answer
// is its own model_list, so a provider added there — a new key after a free tier
// runs out, a different vendor, a local model — appears in the page's model list
// with no change to this build.
func (s *server) handleLLMModels(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		fail(w, http.StatusMethodNotAllowed, "")
		return
	}
	base, err := llmEndpoint(r.URL.Query().Get("baseUrl"))
	if err != nil {
		fail(w, http.StatusBadRequest, err.Error())
		return
	}
	u, err := llmURL(base)
	if err != nil {
		fail(w, http.StatusBadRequest, err.Error())
		return
	}

	req, err := http.NewRequestWithContext(r.Context(), http.MethodGet, base+"/models", nil)
	if err != nil {
		fail(w, http.StatusBadRequest, err.Error())
		return
	}
	req.Header.Set("Accept", "application/json")
	if key := os.Getenv("KE_LLM_KEY"); key != "" {
		req.Header.Set("Authorization", "Bearer "+key)
	}

	client := &http.Client{Timeout: 20 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		fail(w, http.StatusBadGateway, "could not reach "+u.Host+": "+err.Error())
		return
	}
	defer resp.Body.Close()

	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if resp.StatusCode >= 400 {
		fail(w, http.StatusBadGateway, "endpoint returned "+resp.Status+": "+string(raw[:min(len(raw), 300)]))
		return
	}
	var parsed struct {
		Data []struct {
			ID string `json:"id"`
		} `json:"data"`
	}
	if err := json.Unmarshal(raw, &parsed); err != nil {
		fail(w, http.StatusBadGateway, "endpoint did not answer with a model list")
		return
	}
	names := make([]string, 0, len(parsed.Data))
	for _, m := range parsed.Data {
		if m.ID != "" {
			names = append(names, m.ID)
		}
	}
	log.Printf("llm %s models=%d", u.Host, len(names))
	writeJSON(w, map[string]any{"models": names})
}

// handleLLM forwards a chat request to an OpenAI-compatible endpoint.
//
// It exists so the API key never reaches the browser. The page supplies the
// address and the model; the key comes from KE_LLM_KEY in this process's
// environment and is never returned, logged or echoed back.
//
// This is the only outbound network call anywhere in the application, it is
// only reachable when the user has switched AI assistance on in the UI, and
// nothing else in the build depends on it working.
func (s *server) handleLLM(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		fail(w, http.StatusMethodNotAllowed, "")
		return
	}
	var body struct {
		BaseURL     string            `json:"baseUrl"`
		Model       string            `json:"model"`
		Temperature float64           `json:"temperature"`
		Messages    []json.RawMessage `json:"messages"`
	}
	if err := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&body); err != nil {
		fail(w, http.StatusBadRequest, "bad body")
		return
	}
	if body.Model == "" || len(body.Messages) == 0 {
		fail(w, http.StatusBadRequest, "model and messages are both required")
		return
	}
	base, err := llmEndpoint(body.BaseURL)
	if err != nil {
		fail(w, http.StatusBadRequest, err.Error())
		return
	}
	u, err := llmURL(base)
	if err != nil {
		fail(w, http.StatusBadRequest, err.Error())
		return
	}

	payload, _ := json.Marshal(map[string]any{
		"model":       body.Model,
		"temperature": body.Temperature,
		"messages":    body.Messages,
	})
	endpoint := base + "/chat/completions"

	req, err := http.NewRequestWithContext(r.Context(), http.MethodPost, endpoint, bytes.NewReader(payload))
	if err != nil {
		fail(w, http.StatusBadRequest, err.Error())
		return
	}
	req.Header.Set("Content-Type", "application/json")
	if key := os.Getenv("KE_LLM_KEY"); key != "" {
		req.Header.Set("Authorization", "Bearer "+key)
	}

	client := &http.Client{Timeout: 120 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		// The address, not the key: the key is never in an error path.
		fail(w, http.StatusBadGateway, "could not reach "+u.Host+": "+err.Error())
		return
	}
	defer resp.Body.Close()

	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 8<<20))
	if resp.StatusCode >= 400 {
		fail(w, http.StatusBadGateway, "endpoint returned "+resp.Status+": "+string(raw[:min(len(raw), 400)]))
		return
	}

	// Unwrap to the one field the page wants, so a change of provider shape does
	// not become a change in the frontend.
	var parsed struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.Unmarshal(raw, &parsed); err != nil || len(parsed.Choices) == 0 {
		fail(w, http.StatusBadGateway, "endpoint answered in a shape this build does not recognise")
		return
	}
	log.Printf("llm %s model=%s ok", u.Host, body.Model)
	writeJSON(w, map[string]string{"content": parsed.Choices[0].Message.Content})
}

func (s *server) handleSamples(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, s.samples)
}

func (s *server) handleSampleFile(w http.ResponseWriter, r *http.Request) {
	name := strings.TrimPrefix(r.URL.Path, "/api/samples/")
	// path.Base collapses any traversal attempt to a bare filename before it is
	// used, and the embedded FS is read-only regardless.
	name = path.Base(name)
	if !strings.HasSuffix(name, ".json") {
		fail(w, http.StatusBadRequest, "not a sample")
		return
	}
	b, err := sampleFS.ReadFile("samples/" + name)
	if err != nil {
		fail(w, http.StatusNotFound, "no such sample")
		return
	}
	writeRaw(w, b)
}

// handleStatic serves the embedded frontend. Anything unrecognised falls back
// to index.html so that a deep link like /#/build survives a page reload.
func (s *server) handleStatic(w http.ResponseWriter, r *http.Request) {
	sub, err := fs.Sub(webFS, "web")
	if err != nil {
		fail(w, http.StatusInternalServerError, err.Error())
		return
	}
	p := strings.TrimPrefix(path.Clean(r.URL.Path), "/")
	if p == "" || p == "." {
		p = "index.html"
	}
	f, err := sub.Open(p)
	if err != nil {
		// Fall back to index.html ONLY for route-like paths, so a deep link such
		// as /#/build survives a reload.
		//
		// It used to fall back for everything, which meant a missing asset was
		// answered with the HTML page under a 200 and the wrong Content-Type.
		// A stylesheet served as text/html is silently discarded by the browser,
		// so a single absent CSS file would take out every icon in the interface
		// with nothing in the log to say so. An asset that is not there must 404
		// and be visible in the network tab.
		if path.Ext(p) != "" {
			fail(w, http.StatusNotFound, "no such file: "+p)
			return
		}
		p = "index.html"
		if f, err = sub.Open(p); err != nil {
			fail(w, http.StatusNotFound, "not found")
			return
		}
	}
	defer f.Close()

	// Vendored assets are content-addressed by version in practice: they change
	// only when the image is rebuilt, so a long cache is safe. index.html is not.
	if strings.HasPrefix(p, "vendor/") {
		w.Header().Set("Cache-Control", "public, max-age=604800")
	} else {
		w.Header().Set("Cache-Control", "no-cache")
	}
	if ct := contentType(p); ct != "" {
		w.Header().Set("Content-Type", ct)
	}

	if rs, ok := f.(io.ReadSeeker); ok {
		st, err := f.Stat()
		if err == nil {
			http.ServeContent(w, r, p, st.ModTime(), rs)
			return
		}
	}
	_, _ = io.Copy(w, f)
}

func contentType(p string) string {
	switch {
	case strings.HasSuffix(p, ".html"):
		return "text/html; charset=utf-8"
	case strings.HasSuffix(p, ".js"):
		return "text/javascript; charset=utf-8"
	case strings.HasSuffix(p, ".css"):
		return "text/css; charset=utf-8"
	case strings.HasSuffix(p, ".json"):
		return "application/json; charset=utf-8"
	case strings.HasSuffix(p, ".woff2"):
		return "font/woff2"
	case strings.HasSuffix(p, ".svg"):
		return "image/svg+xml"
	}
	return ""
}

// loadSampleIndex reads every embedded sample once at startup and precomputes
// the counts the landing page shows, so that page does not have to parse three
// models to print three numbers.
func loadSampleIndex() ([]sampleMeta, error) {
	entries, err := sampleFS.ReadDir("samples")
	if err != nil {
		return nil, err
	}
	out := []sampleMeta{}
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		b, err := sampleFS.ReadFile("samples/" + e.Name())
		if err != nil {
			continue
		}
		var m model
		if err := json.Unmarshal(b, &m); err != nil {
			log.Printf("sample %s: %v", e.Name(), err)
			continue
		}
		layerOf := map[string]string{}
		for _, n := range m.Nodes {
			layerOf[n.ID] = n.Layer
		}
		cross := 0
		for _, ed := range m.Edges {
			a, aok := layerOf[ed.From]
			b2, bok := layerOf[ed.To]
			if aok && bok && a != b2 {
				cross++
			}
		}
		out = append(out, sampleMeta{
			Key:        strings.SplitN(strings.TrimSuffix(e.Name(), ".json"), "-", 2)[0],
			File:       e.Name(),
			Name:       m.Name,
			Nodes:      len(m.Nodes),
			Edges:      len(m.Edges),
			Layers:     len(m.Layers),
			CrossLayer: cross,
		})
	}
	if len(out) == 0 {
		return out, fmt.Errorf("no samples embedded")
	}
	return out, nil
}
