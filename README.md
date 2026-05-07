# WhyLine

WhyLine answers the question "why did this code change?" directly inside the IDE.
Select a range of code lines, right-click, and choose **WhyLine: Explain Why**.
The plugin reads local Git history, sends a normalized evidence bundle to the backend,
and displays the linked Jira ticket with a short human-readable explanation in the Tool Window.

---

## Try the plugin

The ready-to-install plugin zip is included in this repository:

```text
WhyLinePlugin-1.0-SNAPSHOT.zip
```

### Installation

1. Open IntelliJ IDEA
2. Go to **Settings → Plugins**
3. Click the gear icon and choose **Install Plugin from Disk...**
4. Select `WhyLinePlugin-1.0-SNAPSHOT.zip` from this repository
5. Restart the IDE when prompted

### Configuration

After installation, open **Settings → Tools → WhyLine** and fill in the following:

#### Connection

- **Backend URL** — URL of the WhyLine backend server (e.g. `http://3.126.4.198:8000`)
- **Workspace ID / Repository ID** — leave blank, then click **Auto-Register Workspace** to fill these automatically

#### OpenAI *(optional — required for GPT explanations)*

- **API key** — your personal OpenAI key from [platform.openai.com](https://platform.openai.com). Stored locally in the JetBrains Password Safe; never sent to the server except as part of each analysis request.
- **Enable LLM features** — becomes available once a key is entered. When enabled, GPT re-ranks Jira candidates and generates a 2–4 sentence explanation.

#### Jira

- **Email** — your Atlassian account email
- **API token** — generate one at id.atlassian.com under Security → API tokens
- **Base URL** — `https://your-site.atlassian.net`

Click **OK**. The plugin sends your Jira credentials to the backend (stored server-side, never returned to the client).

### Usage

1. Open any Java/Kotlin project that is a Git repository
2. Select one or more lines of code in the editor
3. Right-click → **WhyLine: Explain Why** (or press `Ctrl+Shift+W`)
4. The **WhyLine** panel on the right side will show the matched Jira ticket and explanation

---

## How it works

1. User selects code lines in a JetBrains IDE and right-clicks → **WhyLine: Explain Why**
2. Plugin collects Git evidence locally (blame SHA, commit message, diff, nearby commits)
3. Plugin sends one HTTP request to the backend
4. Backend scores Jira candidates using a weighted multi-signal pipeline (no native Jira-Git integration required)
5. If LLM is enabled — GPT re-ranks candidates and generates a 2–4 sentence explanation
6. Result appears in the WhyLine Tool Window: ticket link + explanation + confidence

Jira keys in commit messages are optional — WhyLine works without them via semantic matching.

---

## Repository layout

```text
WhyLinePlugin-1.0-SNAPSHOT.zip   ready-to-install plugin
backend/      FastAPI service — Jira enrichment, scoring, LLM, cache
migrations/   Alembic migrations (PostgreSQL + pgvector)
infra/        deployment (Docker Compose, AWS)
docs/         architecture overview, backend schema, devpost story
```

Full architecture specification: [ARCHITECTURE.md](ARCHITECTURE.md)

---

## Component overview

```text
[User's machine]
  JetBrains IDE
    └── WhyLine plugin
          ExplainWhyAction      right-click entry point
          GitContextService     reads .git locally via Git4Idea
          BackendClient         sends HTTP request to backend
          WhyPanel              renders result in Tool Window
          WhySettings           persistent settings (backend URL, IDs, Jira)
          WhyCredentialService  stores Jira token via JetBrains Password Safe

[AWS — 3.126.4.198:8000]
  FastAPI backend
    ├── Receives Git evidence bundle
    ├── Fetches Jira candidates via REST API + multi-signal keyword search
    ├── Scores candidates with a 10-signal weighted deterministic scorer
    ├── Runs cosine vector search via pgvector (OpenAI embeddings)
    ├── Calls OpenAI GPT for rerank + explanation (when LLM enabled)
    └── Returns { ticket_key, ticket_url, summary, confidence, output_mode }

  PostgreSQL + pgvector
    ├── workspaces / jira_connections / repositories
    ├── git_commits / jira_issues (with vector embeddings) / jira_comments
    ├── anchors / anchor_candidates
    └── final_answers  — response cache (TTL 24h)
```
