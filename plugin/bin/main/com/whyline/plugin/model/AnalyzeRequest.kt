package com.whyline.plugin.model

/**
 * Per-commit snapshot collected by GitContextService.
 *
 * [rawDiff] carries at most 4 KB of raw unified diff for the commit,
 * or null when the commit is a nearby-commit entry (diff not fetched per-commit, see
 * GitContextService.nearbyCommits for the rationale).
 *
 * BACKEND BOUNDARY: backend.services.git_features.extract_git_features() tokenises
 * [rawDiff] into diff_keywords used by the scorer. The plugin never summarises this field.
 */
data class CommitInfo(
    val sha: String,
    val message: String,
    val date: String?,
    val rawDiff: String? = null,
)

/**
 * Request payload sent to POST /api/v1/analyze.
 *
 * Git evidence fields ([blameSha], [commitMessage], [branch], [commitDate], [rawDiff],
 * [nearbyCommits]) are populated by GitContextService and represent raw local-git data.
 *
 * BACKEND BOUNDARY: all diff summarisation and keyword extraction happen server-side.
 * The plugin's job is to collect and forward; the backend's job is to score and explain.
 */
data class AnalyzeRequest(
    // Workspace / repo identity — configured once in plugin settings
    val workspaceId: Int,
    val repositoryId: Int,

    // Code anchor
    val filePath: String,
    val lineStart: Int,
    val lineEnd: Int,
    val selectedText: String? = null,
    val className: String? = null,
    val methodName: String? = null,
    val contextBefore: String? = null,
    val contextAfter: String? = null,

    // Git evidence bundle — all collected locally by GitContextService, never by the backend
    val blameSha: String? = null,
    val commitMessage: String? = null,
    val branch: String? = null,
    val commitDate: String? = null,
    // Raw unified diff for the blame commit (≤ 4 KB). Plugin does not summarise this.
    // BACKEND BOUNDARY: scorer extracts diff_keywords from this field.
    val rawDiff: String? = null,
    val nearbyCommits: List<CommitInfo> = emptyList(),

    // LLM settings — key travels in X-OpenAI-Key header, never in this body
    val enableLlm: Boolean = true,
    val openAiModel: String = "gpt-4o",
)
