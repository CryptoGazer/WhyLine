package com.whyline.plugin.analyzer

import com.whyline.plugin.model.CommitInfo

private val JIRA_KEY_RE = Regex("""\b([A-Z][A-Z0-9]+-\d+)\b""")

private val STOP_WORDS = setOf(
    "fix", "bug", "the", "and", "for", "are", "was", "were", "been", "with",
    "this", "that", "from", "feat", "chore", "refactor", "revert", "merge",
    "its", "orr", "byy", "too",
)

data class GitFeatures(
    val filePath: String,
    val lineStart: Int,
    val lineEnd: Int,
    val className: String?,
    val methodName: String?,
    val blameSha: String?,
    val commitDate: String?,
    val branch: String?,
    val commitMessages: List<String>,
    val rawDiffs: List<String>,
    val explicitJiraKeys: List<String>,
    val selectedTextKeys: List<String>,
    val messageKeywords: Set<String>,
    val diffKeywords: Set<String>,
    val identifierKeywords: Set<String>,
)

object GitFeaturesExtractor {

    fun extract(
        filePath: String,
        lineStart: Int,
        lineEnd: Int,
        className: String?,
        methodName: String?,
        selectedText: String?,
        contextBefore: String?,
        contextAfter: String?,
        blameSha: String?,
        commitMessage: String?,
        branch: String?,
        commitDate: String?,
        rawDiff: String?,
        nearbyCommits: List<CommitInfo>,
    ): GitFeatures {
        val commitMessages = mutableListOf<String>()
        if (commitMessage != null) commitMessages.add(commitMessage)
        nearbyCommits.mapTo(commitMessages) { it.message }

        val rawDiffs = mutableListOf<String>()
        if (rawDiff != null) rawDiffs.add(rawDiff)
        nearbyCommits.mapNotNullTo(rawDiffs) { it.rawDiff }

        val keySources = commitMessages.toMutableList()
        if (branch != null) keySources.add(branch)
        if (selectedText != null) keySources.add(selectedText)
        if (contextBefore != null) keySources.add(contextBefore)
        if (contextAfter != null) keySources.add(contextAfter)

        val explicitKeys = extractJiraKeys(keySources)
        val selectedTextKeys = extractJiraKeys(listOfNotNull(selectedText))

        val messageKeywords = mutableSetOf<String>()
        for (msg in commitMessages) messageKeywords += tokenize(msg)

        val diffKeywords = mutableSetOf<String>()
        for (diff in rawDiffs) diffKeywords += tokenize(diff)

        val identifierKeywords = mutableSetOf<String>()
        for (part in filePath.split(Regex("""[/\\._\-]"""))) {
            if (part.length > 2) identifierKeywords.add(part.lowercase())
        }
        if (className != null) identifierKeywords += tokenize(className)
        if (methodName != null) identifierKeywords += tokenize(methodName)
        if (selectedText != null) {
            Regex("[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|\$)").findAll(selectedText).forEach { m ->
                if (m.value.length > 2) identifierKeywords.add(m.value.lowercase())
            }
        }

        return GitFeatures(
            filePath = filePath,
            lineStart = lineStart,
            lineEnd = lineEnd,
            className = className,
            methodName = methodName,
            blameSha = blameSha,
            commitDate = commitDate,
            branch = branch,
            commitMessages = commitMessages,
            rawDiffs = rawDiffs,
            explicitJiraKeys = explicitKeys,
            selectedTextKeys = selectedTextKeys,
            messageKeywords = messageKeywords,
            diffKeywords = diffKeywords,
            identifierKeywords = identifierKeywords,
        )
    }

    private fun tokenize(text: String): Set<String> =
        Regex("[a-zA-Z_][a-zA-Z0-9_]{2,}").findAll(text.lowercase())
            .map { it.value }
            .filterTo(mutableSetOf()) { it !in STOP_WORDS }

    private fun extractJiraKeys(texts: List<String>): List<String> {
        val seen = mutableSetOf<String>()
        val keys = mutableListOf<String>()
        for (text in texts) {
            JIRA_KEY_RE.findAll(text).forEach { m ->
                val key = m.groupValues[1]
                if (seen.add(key)) keys.add(key)
            }
        }
        return keys
    }
}
