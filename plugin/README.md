# WhyLine — JetBrains Plugin

**WhyLine** answers the question *"why did this code change?"* without leaving the IDE.

Select any range of code, right-click → **WhyLine: Explain Why** (or `Ctrl+Shift+W`), and instantly see the linked Jira ticket and a plain-language explanation.

---

## How it works

Everything runs locally on the developer's machine — no external server required.

1. **Git context** — WhyLine reads `git blame`, recent commit messages, and the diff for the selected lines.
2. **Jira candidates** — The plugin calls the Jira REST API directly to fetch issues that match commit keywords or explicit Jira keys found in commit messages and branches.
3. **Multi-signal scoring** — Candidates are ranked using ten weighted signals:

   | Signal | Weight |
   | --- | --- |
   | Exact Jira key in commit / branch | 100 |
   | Commit message ↔ issue summary overlap | 45 |
   | Diff tokens ↔ issue description overlap | 35 |
   | Diff tokens ↔ issue comment overlap | 35 |
   | Vector similarity (OpenAI embeddings) | 35 |
   | Identifier names ↔ issue text overlap | 20 |
   | Commit date proximity to issue dates | 20 |
   | Historical co-occurrence | 15 |
   | Project whitelist bonus | 10 |
   | Label overlap | 5 |

4. **Optional LLM mode** — With an OpenAI API key, the top candidates are reranked by GPT and the result becomes a 2–4 sentence natural language explanation instead of a raw ticket title.

---

## Setup

1. Open **Settings → Tools → WhyLine**
2. Enter your **Jira credentials**:
   - Email (your Atlassian account email)
   - API token (generate at [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens))
   - Base URL (`https://your-site.atlassian.net`)
3. Optionally enter **Project keys** (comma-separated, e.g. `PROJ,BACK`) to narrow search scope. Leave blank to search all visible projects.
4. Optionally add an **OpenAI API key** and enable **LLM features** for GPT-powered explanations.

---

## Usage

- Select a block of code in any file
- Right-click → **WhyLine: Explain Why** — or press `Ctrl+Shift+W`
- Results appear in the **WhyLine** tool window (right side panel)

The result shows:

- The top matching Jira ticket key and a clickable URL in the status bar
- A summary or explanation (LLM mode) in the main area
- Confidence level: `HIGH` / `MEDIUM` / `LOW`
- Contributing issues list when multiple tickets overlap

---

## Compatibility

| OS | Status |
| --- | --- |
| macOS | Fully supported |
| Linux | Fully supported |
| Windows | Fully supported |

The plugin runs entirely on the JVM — all scoring, HTTP calls (Jira, OpenAI), and credential storage are platform-independent. Git operations are spawned as a subprocess; `git` must be installed and available in `PATH` (standard on all platforms).

---

## Build

Requires Java 21 and IntelliJ IDEA installed at `/Applications/IntelliJ IDEA.app`.

```bash
./gradlew clean buildPlugin
```

The plugin zip is produced in `build/distributions/`. Install via **Settings → Plugins → Install Plugin from Disk**.

---

## Project structure

```text
src/main/kotlin/com/whyline/plugin/
├── actions/
│   └── ExplainWhyAction.kt        — right-click menu entry, keyboard shortcut
├── analyzer/
│   ├── AnalyzerService.kt         — main pipeline orchestrator
│   ├── EmbeddingService.kt        — OpenAI text-embedding-3-small, in-memory cache
│   ├── GitFeaturesExtractor.kt    — extracts keywords and Jira keys from git context
│   ├── JiraApiService.kt          — Jira REST API client, 6-hour issue cache
│   ├── JiraIssueData.kt           — local data classes for Jira entities
│   ├── LlmService.kt              — GPT reranking and explanation generation
│   └── ScorerService.kt           — multi-signal weighted scorer
├── model/
│   ├── AnalyzeRequest.kt          — CommitInfo data class
│   └── AnalyzeResponse.kt         — result model consumed by WhyPanel
├── services/
│   └── GitContextService.kt       — git blame / log / diff via subprocess
├── settings/
│   ├── WhyCredentialService.kt    — Jira token + OpenAI key via JetBrains Password Safe
│   ├── WhySettings.kt             — persistent non-secret settings (XML)
│   └── WhySettingsConfigurable.kt — Settings UI panel
└── toolwindow/
    ├── WhyPanel.kt                — result display panel
    └── WhyToolWindowFactory.kt    — registers the tool window
```

---

## Privacy

All analysis runs locally. The only outbound network calls are:

- **Jira REST API** — to fetch issue metadata using your own credentials
- **OpenAI API** (optional) — to generate embeddings and LLM explanations using your own API key

No data is sent to any third-party server operated by this project.
