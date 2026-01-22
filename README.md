# 🏷️ TaggerNews (IronHN)

> **A Modern Hacker News Aggregator with AI-Powered Summaries**

[![Rust](https://img.shields.io/badge/Rust-Scraper-orange?logo=rust)](https://www.rust-lang.org/)
[![C++](https://img.shields.io/badge/C++20-Server-blue?logo=cplusplus)](https://isocpp.org/)
[![Python](https://img.shields.io/badge/Python-MVP-yellow?logo=python)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Database-336791?logo=postgresql)](https://www.postgresql.org/)

---

## 🎯 Project Vision

TaggerNews is a technical showcase project demonstrating **modern systems programming skills** by building a Hacker News aggregator:

- **Rust Async Programming** - Safe, high-concurrency data scraping
- **C++ Systems Programming** - High-performance web server
- **LLM Integration** - AI-powered content summarization & tagging

---

## ⚙️ Code Origin: Human-Written vs AI-Assisted

> **Core Philosophy:** Critical infrastructure is written by hand. Boilerplate can be AI-assisted.

### 🧠 Human-Written Code (No AI Assistance)

These components are **intentionally coded without AI tools** (no Copilot, no Claude, no ChatGPT) to demonstrate genuine understanding:

| Component | Language | Why No AI |
|-----------|----------|-----------|
| **Async HTTP Client** | Rust | Must understand `Future`, `Poll`, `Pin`, `Context` |
| **epoll Event Loop** | C++ | Core Linux systems knowledge |
| **Thread Pool** | C++ | Concurrency primitives mastery |
| **HTTP Parser** | C++ | Zero-copy memory optimization |
| **LRU Cache** | C++ | Classic data structure + thread safety |
| **URL Router** | C++ | Algorithm design skills |
| **Connection State Machine** | C++ | Protocol handling logic |
| **SQL Triggers** | SQL | Database event-driven logic + data integrity |

### 🤖 AI-Assisted Code

These components are developed **with AI coding assistants** (Copilot, Claude, etc.) since they're mostly boilerplate or configuration:

| Component | Rationale |
|-----------|-----------|
| **CI/CD pipelines** | YAML configuration |
| **Frontend (HTMX)** | UI markup |
| **Test scaffolding** | Setup code is boilerplate |
| **OpenAI API integration** | Standard REST calls |
| **Build system (CMake/Cargo)** | Configuration files |

### 📦 Libraries Used

| Category | Library | Rationale |
|----------|---------|-----------|
| **TLS/Crypto** | `rustls` | Never roll your own crypto |
| **JSON** | `serde_json`, `nlohmann/json` | Well-tested, performant |
| **Database** | `sqlx`, `libpq` | Protocol complexity |
| **Async Runtime** | `tokio` | Scheduler is not our focus |

---

## 🏛️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        TaggerNews System                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────┐         ┌─────────────────┐                 │
│  │   HN Firebase   │         │   OpenAI API    │                 │
│  │      API        │         │  (Summarizer)   │                 │
│  └────────┬────────┘         └────────┬────────┘                 │
│           │                           │                           │
│           ▼                           ▼                           │
│  ┌────────────────────────────────────────────────────┐          │
│  │         🦀 Rust Scraper Service                    │          │
│  │  ┌──────────────────────────────────────────────┐  │          │
│  │  │ 🧠 HUMAN-WRITTEN:                            │  │          │
│  │  │   • Async HTTP Client (Custom Future)        │  │          │
│  │  │   • TLS Stream Wrapping                      │  │          │
│  │  │   • Exponential Backoff Logic                │  │          │
│  │  │ 🤖 AI-ASSISTED: Config, Tests, API calls     │  │          │
│  │  └──────────────────────────────────────────────┘  │          │
│  └────────────────────┬───────────────────────────────┘          │
│                       │                                           │
│                       ▼                                           │
│  ┌────────────────────────────────────────────────┐                  │
│  │            🐘 PostgreSQL                       │                  │
│  │  stories │ comments │ summaries │ tags         │                  │
│  └────────────────────┬───────────────────────────┘                  │
│                       │                                           │
│                       ▼                                           │
│  ┌────────────────────────────────────────────────────┐          │
│  │         ⚡ C++ Web Server                          │          │
│  │  ┌──────────────────────────────────────────────┐  │          │
│  │  │ 🧠 HUMAN-WRITTEN:                            │  │          │
│  │  │   • epoll Event Loop                         │  │          │
│  │  │   • Thread Pool                              │  │          │
│  │  │   • Zero-Copy HTTP Parser                    │  │          │
│  │  │   • LRU Cache                                │  │          │
│  │  │   • URL Router                               │  │          │
│  │  │ 🤖 AI-ASSISTED: CMake, Dockerfile            │  │          │
│  │  └──────────────────────────────────────────────┘  │          │
│  └────────────────────┬───────────────────────────────┘          │
│                       │                                           │
│                       ▼                                           │
│  ┌────────────────────────────────────────────────┐                  │
│  │          🌐 Frontend (🤖 AI-Assisted)          │                  │
│  │              HTMX + Minimal JS                 │                  │
│  └────────────────────────────────────────────────┘                  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎓 Technical Showcase

### Why This Tech Stack?

| Component | Language | Rationale |
|-----------|----------|-----------|
| **Scraper** | Rust 🦀 | Memory safety for parsing untrusted data; `async/await` for I/O-bound tasks |
| **Web Server** | C++ ⚡ | Homage to Nginx/Envoy; demonstrates `epoll`, syscalls, memory layout |
| **MVP** | Python 🐍 | Rapid prototyping to establish data flow |

### Interview Talking Points

#### Rust Scraper (🧠 Human-Written Core)

| Concept | Implementation | Why It Matters |
|---------|---------------|----------------|
| **Async Internals** | Custom `Future` with manual polling | Explain why `MutexGuard` can't be held across `await` |
| **Memory Safety** | `Result<T, E>` everywhere | Forces handling all error paths |
| **HTTPS** | Manual TLS stream with rustls | Challenging but high-value |

#### C++ Server (🧠 Human-Written Core)

| Concept | Implementation | Why It Matters |
|---------|---------------|----------------|
| **Reactor Pattern** | Hand-written epoll loop | Like Node.js/Nginx core |
| **ET vs LT** | Edge-Triggered epoll | Deep Linux knowledge |
| **Memory Layout** | Object Pool for requests | Avoiding fragmentation |
| **Modern C++** | `std::move`, `unique_ptr`, `string_view` | Practical move semantics |

---

## 📁 Repository Structure

```
TaggerNews/                    # 🎛️ Infrastructure (You are here)
├── docker-compose.yml         # 🤖 AI-Assisted
├── database/
│   └── init.sql              # 🤖 AI-Assisted
├── prometheus/               # 🤖 AI-Assisted
└── grafana/                  # 🤖 AI-Assisted

taggernews-scraper-rs/        # 🦀 Rust Scraper
├── src/
│   ├── http/                 # 🧠 HUMAN: Custom HTTP Client
│   ├── parser/               # 🧠 HUMAN: Parsing logic
│   └── main.rs
└── Cargo.toml                # 🤖 AI-Assisted

taggernews-server-cpp/        # ⚡ C++ Server
├── src/
│   ├── core/
│   │   ├── Server.cpp        # 🧠 HUMAN: socket, bind, listen
│   │   ├── EPoller.cpp       # 🧠 HUMAN: epoll event loop
│   │   └── ThreadPool.cpp    # 🧠 HUMAN: Worker threads
│   ├── http/
│   │   ├── Request.cpp       # 🧠 HUMAN: Zero-copy parsing
│   │   └── Response.cpp      # 🧠 HUMAN
│   └── main.cpp
├── CMakeLists.txt            # 🤖 AI-Assisted
└── Dockerfile                # 🤖 AI-Assisted
```

---

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Rust 1.75+
- GCC 12+ / Clang 15+ with C++20
- PostgreSQL 15+
- OpenAI API Key

### Development Setup

```bash
# Clone all repositories
git clone https://github.com/yourname/TaggerNews.git
git clone https://github.com/yourname/taggernews-scraper-rs.git
git clone https://github.com/yourname/taggernews-server-cpp.git

# Start infrastructure
cd TaggerNews
docker-compose up -d postgres prometheus grafana

# Run the scraper
cd ../taggernews-scraper-rs
cargo run

# Build and run the server
cd ../taggernews-server-cpp
mkdir build && cd build
cmake .. && make
./taggernews-server
```

---

## 📊 Performance Goals

| Metric | Target |
|--------|--------|
| Server Latency (p99) | < 5ms |
| Concurrent Connections | 10,000+ (C10k) |
| Scraper Throughput | 100 req/s |

---

## 📜 License

MIT License

---

<p align="center">
  <i>🧠 Core Systems Code: Human-Written | 🤖 Boilerplate: AI-Assisted</i>
</p>
