# 🗺️ TaggerNews Master Roadmap

> **Architecture:** Microservices (Rust Scraper + C++ Server)  
> **Goal:** Showcase Modern C++ Systems Programming & Rust Async Safety

---

## 📋 Overview

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4
  MVP       Infra       Rust        C++       Extensions
 Python    Docker     Scraper     Server      Advanced
```

### Legend: Code Origin

| Icon | Meaning |
|------|---------|
| 🧠 | **Human-Written** - No AI coding tools (Copilot, Claude, ChatGPT, etc.) |
| 🤖 | **AI-Assisted** - Generated/assisted by AI coding tools |
| 📦 | **Library** - Using existing third-party libraries |

---

## 🐍 Phase 0: Python MVP (Baseline)

> **Goal**: Rapidly validate business logic  
> **Code Origin**: 🤖 AI-Assisted (speed matters for MVP)  
> **Estimated Time**: 1-2 weeks

- [ ] **Scraper MVP**
    - [ ] 🤖 Use `requests` to fetch HN Firebase API
    - [ ] 🤖 Call OpenAI API for summarization
    - [ ] 🤖 SQLAlchemy for PostgreSQL storage
- [ ] **Server MVP**
    - [ ] 🤖 FastAPI for JSON API
    - [ ] 🤖 HTMX frontend
    - [ ] 🤖 Basic pagination and search

---

## 🏛️ Phase 1: Infrastructure & Orchestration

> **Repository**: `TaggerNews` (this repo)  
> **Code Origin**: 🤖 AI-Assisted (boilerplate/config)  
> **Estimated Time**: 1 week

### Database Design

- [ ] 🤖 Design `database/init.sql`
    - [ ] `stories`, `comments`, `summaries`, `tags` tables
    - [ ] Indexes for query optimization

### Docker Orchestration

- [ ] 🤖 Create `docker-compose.yml`
- [ ] 🤖 Health checks and restart policies

### Observability

- [ ] 🤖 Prometheus + Grafana configuration

---

## 🦀 Phase 2: Rust Async Scraper

> **Repository**: `taggernews-scraper-rs`  
> **Estimated Time**: 3-4 weeks

### 2.1 🧠 Networking Layer (Human-Written)

> **No AI tools allowed.** This demonstrates genuine understanding of Rust async.

- [ ] **🧠 Custom Future Implementation**
    - [ ] Use `TcpStream` to establish connections
    - [ ] Implement custom `Future` to poll socket data
    - [ ] Deep understanding of `Poll`, `Context`, `Pin`

- [ ] **🧠 HTTPS Support**
    - [ ] 📦 Use `rustls` library (don't roll crypto)
    - [ ] 🧠 Wrap TLS Stream in custom connection logic
    - [ ] 🧠 Handle certificate validation flow

- [ ] **🧠 HTTP/1.1 Parsing**
    - [ ] Status Line parsing
    - [ ] Header parsing (case-insensitive)
    - [ ] Body handling (Content-Length / Chunked)

- [ ] **🧠 Robustness**
    - [ ] Exponential Backoff retry logic
    - [ ] Rate limit handling
    - [ ] Graceful timeout handling

### 2.2 🤖 Boilerplate (AI-Assisted)

- [ ] 🤖 Cargo.toml configuration
- [ ] 🤖 Test scaffolding
- [ ] 🤖 CLI argument parsing
- [ ] 🤖 Logging setup

### 2.3 Data Pipeline

- [ ] 📦 JSON parsing with `serde_json`
- [ ] 📦 Async database with `sqlx`
- [ ] 🤖 OpenAI API integration

### Interview Talking Points 🎯

| Topic | What You Can Discuss |
|-------|---------------------|
| Async Internals | Why `MutexGuard` can't be held across `await` |
| Custom Future | How you implemented `poll()` manually |
| Error Handling | How `Result<T, E>` enforces safety |

---

## ⚡ Phase 3: High-Performance C++ Server

> **Repository**: `taggernews-server-cpp`  
> **Target**: C10k Problem Solver  
> **Estimated Time**: 4-6 weeks

### 3.1 🧠 Core Networking (Human-Written)

> **No AI tools allowed.** This is the core showcase of systems programming skills.

- [ ] **🧠 Socket Programming**
    - [ ] `socket()`, `bind()`, `listen()`, `accept()`
    - [ ] `O_NONBLOCK` non-blocking mode
    - [ ] `SO_REUSEADDR`, `SO_REUSEPORT`

- [ ] **🧠 epoll Event Loop**
    - [ ] `epoll_create1()`, `epoll_ctl()`, `epoll_wait()`
    - [ ] Edge Triggered vs Level Triggered
    - [ ] Main event dispatch loop

- [ ] **🧠 Connection Management**
    - [ ] State machine (Reading → Processing → Writing)
    - [ ] Keep-Alive connection reuse
    - [ ] Timeout detection and cleanup

### 3.2 🧠 Thread Pool (Human-Written)

- [ ] **🧠 Design & Implementation**
    - [ ] Fixed Worker Threads
    - [ ] Thread-safe Task Queue
    - [ ] Graceful shutdown
    - [ ] `std::jthread` + `std::stop_token` (C++20)

### 3.3 🧠 HTTP Processing (Human-Written)

- [ ] **🧠 Zero-Copy Parsing**
    - [ ] Heavy `std::string_view` usage
    - [ ] Avoid `std::string` copies
    - [ ] TCP packet fragmentation handling

- [ ] **🧠 Request Parser**
    - [ ] Method, Path, Version parsing
    - [ ] Header parsing
    - [ ] Query String decoding

- [ ] **🧠 Response Builder**
    - [ ] Status Line, Headers, Body

### 3.4 🧠 Application Layer (Human-Written)

- [ ] **🧠 URL Router**
    - [ ] Trie-based routing
    - [ ] Path parameter extraction

- [ ] **🧠 + 📦 Database Access**
    - [ ] 📦 Use `libpq` library
    - [ ] 🧠 Connection pool wrapper
    - [ ] 🧠 Prepared statements handling

### 3.5 🤖 Boilerplate (AI-Assisted)

- [ ] 🤖 CMakeLists.txt
- [ ] 🤖 Dockerfile
- [ ] 🤖 Test scaffolding
- [ ] 🤖 CI/CD pipeline

### Interview Talking Points 🎯

| Topic | What You Can Discuss |
|-------|---------------------|
| Reactor Pattern | Edge vs Level Triggered differences |
| Memory Layout | How Object Pool prevents fragmentation |
| Modern C++ | `std::move`, `unique_ptr`, RAII |
| Concurrency | Why you chose specific lock types |

---

## 🟣 Phase 4: Extensions

> **Estimated Time**: 2-4 weeks (optional)

### 🧠 Thread-Safe LRU Cache (Human-Written)

- [ ] 🧠 `unordered_map` + doubly-linked list
- [ ] 🧠 O(1) get/put operations
- [ ] 🧠 `std::shared_mutex` for concurrency
- [ ] 🧠 Integration with server

### 🧠 Custom Agent Framework (Human-Written)

> Replace LangGraph with hand-written state machine

- [ ] 🧠 Rust: `enum` + `match` state machine
- [ ] 🧠 C++: `std::variant` + `std::visit`
- [ ] 🤖 API integration boilerplate

---


## 🎯 Definition of Done

- [ ] Scraper reliably fetches HN Top Stories
- [ ] Server handles 10k concurrent connections
- [ ] p99 latency < 5ms
- [ ] Docker Compose one-click deployment

---

<p align="center">
  <b>🧠 Systems Code: Pure Human | 🤖 Boilerplate: AI-Assisted</b>
</p>
