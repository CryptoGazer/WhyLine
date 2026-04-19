package com.whyline.plugin.services

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.whyline.plugin.model.CommitInfo
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * Raw Git evidence collected from the local .git directory.
 *
 * OWNERSHIP BOUNDARY:
 *   Plugin (this file)  → collects raw data, no summarisation
 *   Backend             → extracts keyword tokens, produces digests, runs scoring
 *
 * All fields are nullable — partial evidence is still useful to the scorer.
 */
data class GitEvidence(
    val blameSha: String?,
    val commitMessage: String?,
    val branch: String?,
    val commitDate: String?,
    // Raw unified diff for the blame commit, capped at RAW_DIFF_MAX_CHARS.
    // Plugin does NOT summarise this — it is sent verbatim to the backend.
    // BACKEND BOUNDARY: backend.services.git_features tokenises rawDiff into diff_keywords.
    val rawDiff: String?,
    val nearbyCommits: List<CommitInfo>,
)

/**
 * Collects Git evidence for a code location using local git CLI.
 *
 * Design decisions:
 * - Uses ProcessBuilder("git", ...) — no Git4Idea platform services, no GitHub API.
 * - Returns partial evidence on any git failure; never throws.
 * - Does not fetch per-commit diffs for nearby commits (O(n) — too expensive).
 *   Backend resolves those lazily from git_commits table.
 * - Does not touch Jira or the backend — responsibility of BackendClient.
 */
class GitContextService {

    private val logger = Logger.getInstance(GitContextService::class.java)

    companion object {
        private const val GIT_TIMEOUT_SEC = 5L

        // Cap raw diff size sent to backend. Backend owns summarisation beyond this limit.
        private const val RAW_DIFF_MAX_CHARS = 4_000

        private const val NEARBY_COMMITS_LIMIT = 10

        // SHA used as "empty tree" parent for initial commits with no parent commit.
        private const val EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

        fun getInstance(): GitContextService =
            ApplicationManager.getApplication().getService(GitContextService::class.java)
    }

    fun collectEvidence(
        project: Project,
        file: VirtualFile,
        lineStart: Int,
        lineEnd: Int,
    ): GitEvidence {
        val repoRoot = findRepoRoot(file)
        if (repoRoot == null) {
            logger.warn("WhyLine: no .git root found for ${file.path}")
            return emptyEvidence()
        }

        val relPath = repoRoot.toPath()
            .relativize(File(file.path).toPath())
            .toString()

        val blameSha = blame(repoRoot, relPath, lineStart, lineEnd)
        val branch = currentBranch(repoRoot)
        val commitMessage = blameSha?.let { commitField(repoRoot, it, "%s") }
        val commitDate = blameSha?.let { commitField(repoRoot, it, "%aI") }

        // Raw diff for the blame commit — backend extracts keywords from this.
        val rawDiff = blameSha?.let { rawDiffSnippet(repoRoot, relPath, it) }

        // Recent commits touching this file. rawDiff per commit intentionally not fetched.
        val nearbyCommits = nearbyCommits(repoRoot, relPath)

        return GitEvidence(
            blameSha = blameSha,
            commitMessage = commitMessage?.trim(),
            branch = branch,
            commitDate = commitDate?.trim(),
            rawDiff = rawDiff,
            nearbyCommits = nearbyCommits,
        )
    }

    // ---------------------------------------------------------------------------
    // Git operations — each returns null on failure, never throws
    // ---------------------------------------------------------------------------

    private fun blame(repoRoot: File, relPath: String, lineStart: Int, lineEnd: Int): String? {
        val out = git(repoRoot, "blame", "-L", "$lineStart,$lineEnd", "--porcelain", relPath)
            ?: return null
        val sha = out.lines().firstOrNull()?.take(40) ?: return null
        // All-zero SHA means the line is uncommitted — no blame available.
        return if (sha.all { it == '0' }) null else sha
    }

    private fun currentBranch(repoRoot: File): String? =
        git(repoRoot, "rev-parse", "--abbrev-ref", "HEAD")?.trim()
            ?.takeIf { it.isNotEmpty() && it != "HEAD" } // "HEAD" means detached

    private fun commitField(repoRoot: File, sha: String, format: String): String? =
        git(repoRoot, "log", "-1", "--format=$format", sha)
            ?.trim()?.takeIf { it.isNotEmpty() }

    private fun rawDiffSnippet(repoRoot: File, relPath: String, sha: String): String? {
        // Try normal parent first; fall back to empty-tree for initial commits.
        val out = git(repoRoot, "diff", "--unified=3", "$sha^", sha, "--", relPath)
            ?: git(repoRoot, "diff", "--unified=3", EMPTY_TREE_SHA, sha, "--", relPath)
        // Cap size — backend owns further processing of this raw content.
        return out?.take(RAW_DIFF_MAX_CHARS)
    }

    private fun nearbyCommits(repoRoot: File, relPath: String): List<CommitInfo> {
        // "|||" separator is safe: git log %s rarely contains it in practice.
        val out = git(
            repoRoot,
            "log", "--format=%H|||%s|||%aI", "-$NEARBY_COMMITS_LIMIT", "--", relPath,
        ) ?: return emptyList()

        return out.lines()
            .filter { it.contains("|||") }
            .mapNotNull { line ->
                val parts = line.split("|||", limit = 3)
                if (parts.size < 3) null
                else CommitInfo(
                    sha = parts[0].trim(),
                    message = parts[1].trim(),
                    date = parts[2].trim(),
                    // rawDiff intentionally null for nearby commits: fetching a diff per commit
                    // is O(n) network + disk I/O. Backend resolves from git_commits if needed.
                    rawDiff = null,
                )
            }
    }

    // ---------------------------------------------------------------------------
    // Utilities
    // ---------------------------------------------------------------------------

    private fun findRepoRoot(file: VirtualFile): File? {
        var dir = File(file.parent?.path ?: return null)
        while (true) {
            if (File(dir, ".git").exists()) return dir
            dir = dir.parentFile ?: return null
        }
    }

    /**
     * Runs a git sub-command in [repoRoot], returns stdout or null on error / timeout.
     * stderr is discarded — git writes progress info there which is noise here.
     */
    private fun git(repoRoot: File, vararg args: String): String? {
        return try {
            val process = ProcessBuilder(listOf("git") + args.toList())
                .directory(repoRoot)
                .redirectErrorStream(false)
                .start()
            val output = process.inputStream.bufferedReader().readText()
            val finished = process.waitFor(GIT_TIMEOUT_SEC, TimeUnit.SECONDS)
            if (!finished) {
                process.destroyForcibly()
                logger.warn("WhyLine: git ${args.take(2).joinToString(" ")} timed out after ${GIT_TIMEOUT_SEC}s")
                return null
            }
            if (process.exitValue() != 0) null else output
        } catch (e: Exception) {
            logger.warn("WhyLine: git ${args.take(2).joinToString(" ")} failed: ${e.message}")
            null
        }
    }

    private fun emptyEvidence() = GitEvidence(
        blameSha = null,
        commitMessage = null,
        branch = null,
        commitDate = null,
        rawDiff = null,
        nearbyCommits = emptyList(),
    )
}
