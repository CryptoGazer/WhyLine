package com.whyline.plugin.analyzer

import com.whyline.plugin.model.AnalyzeResponse
import com.whyline.plugin.model.CommitInfo
import com.whyline.plugin.model.ContributingIssue
import com.whyline.plugin.settings.WhyCredentialService
import com.whyline.plugin.settings.WhySettings

object AnalyzerService {

    fun analyze(
        filePath: String,
        lineStart: Int,
        lineEnd: Int,
        selectedText: String?,
        className: String?,
        methodName: String?,
        contextBefore: String?,
        contextAfter: String?,
        blameSha: String?,
        commitMessage: String?,
        branch: String?,
        commitDate: String?,
        rawDiff: String?,
        nearbyCommits: List<CommitInfo>,
    ): AnalyzeResponse {
        val settings = WhySettings.getInstance().state
        val cred = WhyCredentialService.getInstance()
        val jiraToken = cred.getJiraToken() ?: ""
        val openAiKey = cred.getOpenAiKey()

        val projectKeys = settings.jiraProjectKeys
            .split(",")
            .map { it.trim() }
            .filter { it.isNotBlank() }

        val features = GitFeaturesExtractor.extract(
            filePath = filePath,
            lineStart = lineStart,
            lineEnd = lineEnd,
            className = className,
            methodName = methodName,
            selectedText = selectedText,
            contextBefore = contextBefore,
            contextAfter = contextAfter,
            blameSha = blameSha,
            commitMessage = commitMessage,
            branch = branch,
            commitDate = commitDate,
            rawDiff = rawDiff,
            nearbyCommits = nearbyCommits,
        )

        val jiraCandidates = if (settings.jiraBaseUrl.isNotBlank() && settings.jiraEmail.isNotBlank() && jiraToken.isNotBlank()) {
            JiraApiService.fetchCandidates(
                jiraBaseUrl = settings.jiraBaseUrl,
                jiraEmail = settings.jiraEmail,
                jiraToken = jiraToken,
                jiraProjectKeys = projectKeys,
                features = features,
                fetchComments = settings.enableLlm,
            )
        } else emptyList()

        val vectorDistances = mutableMapOf<String, Float>()
        if (!openAiKey.isNullOrBlank() && jiraCandidates.isNotEmpty()) {
            val queryText = features.commitMessages.take(3).joinToString(" ")
            vectorDistances += EmbeddingService.computeVectorDistances(queryText, jiraCandidates, openAiKey)
        }

        var scored = ScorerService.scoreCandidates(
            features = features,
            candidates = jiraCandidates,
            projectKeysWhitelist = projectKeys,
            vectorDistances = vectorDistances,
        )

        val outputMode = when {
            scored.isEmpty() -> if (features.commitMessages.isNotEmpty()) "git_only" else "no_match"
            scored.size > 1 && (features.selectedTextKeys.size > 1 || (lineEnd - lineStart) > 30) -> "combined"
            else -> "single_issue"
        }

        if (settings.enableLlm && !openAiKey.isNullOrBlank() && scored.isNotEmpty()) {
            scored = LlmService.rerankCandidates(features, scored, settings.openAiModel, openAiKey)
        }

        val summary = if (settings.enableLlm && !openAiKey.isNullOrBlank()) {
            LlmService.generateExplanation(features, scored.take(3), outputMode, settings.openAiModel, openAiKey)
        } else {
            fallbackSummary(scored, features, outputMode)
        }

        val topIssue = scored.firstOrNull()?.issue
        val confidence = ScorerService.scoreToConfidence(scored.firstOrNull()?.totalScore ?: 0f)

        val contributing = if (outputMode == "combined" && scored.size > 1) {
            scored.take(3).map { sc ->
                ContributingIssue(
                    issueKey = sc.issue.issueKey,
                    summary = sc.issue.summary,
                    ticketUrl = buildTicketUrl(settings.jiraBaseUrl, sc.issue.issueKey),
                )
            }
        } else emptyList()

        return AnalyzeResponse(
            anchorId = 0,
            ticketKey = topIssue?.issueKey,
            ticketUrl = topIssue?.let { buildTicketUrl(settings.jiraBaseUrl, it.issueKey) },
            summary = summary,
            outputMode = outputMode,
            confidence = confidence,
            fromCache = false,
            contributingIssues = contributing,
        )
    }

    private fun buildTicketUrl(jiraBaseUrl: String, issueKey: String): String? {
        if (jiraBaseUrl.isBlank()) return null
        return "${jiraBaseUrl.trimEnd('/')}/browse/$issueKey"
    }

    private fun fallbackSummary(scored: List<ScoredCandidate>, features: GitFeatures, outputMode: String): String {
        if (scored.isEmpty()) {
            val msgs = features.commitMessages
            return if (msgs.isNotEmpty()) "Git context: ${msgs[0].take(200)}" else "No matching Jira issue found."
        }
        if (outputMode == "combined") return "This code block is linked to multiple Jira tickets (see list below)."
        val top = scored[0]
        return "[${top.issue.issueKey}] ${top.issue.summary}"
    }
}
