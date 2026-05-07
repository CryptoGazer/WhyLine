package com.whyline.plugin.analyzer

import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import kotlin.math.abs
import kotlin.math.max

private const val W_EXACT_KEY = 100f
private const val W_MSG_SUMMARY = 45f
private const val W_DIFF_DESC = 35f
private const val W_DIFF_COMMENTS = 35f
private const val W_IDENTIFIER = 20f
private const val W_TIME_PROXIMITY = 20f
private const val W_HISTORICAL = 15f
private const val W_PROJECT_WHITELIST = 10f
private const val W_LABELS = 5f
private const val W_VECTOR_SIMILARITY = 35f
private const val MIN_SCORE_THRESHOLD = 5f

data class ScoredCandidate(
    val issue: JiraIssueData,
    val totalScore: Float,
    val breakdown: Map<String, Float>,
)

object ScorerService {

    fun scoreCandidates(
        features: GitFeatures,
        candidates: List<JiraIssueData>,
        projectKeysWhitelist: List<String> = emptyList(),
        priorIssueKeys: Set<String> = emptySet(),
        vectorDistances: Map<String, Float> = emptyMap(),
    ): List<ScoredCandidate> {
        val whitelist = projectKeysWhitelist.toSet()
        val results = mutableListOf<ScoredCandidate>()

        for (issue in candidates) {
            val (summaryToks, descToks, labelToks) = issueTextTokens(issue)
            val breakdown = mutableMapOf<String, Float>()

            val exactKeyMatch = issue.issueKey in features.explicitJiraKeys
            breakdown["exact_key"] = if (exactKeyMatch) W_EXACT_KEY else 0f

            val msgOverlap = tokenOverlap(features.messageKeywords, summaryToks)
            breakdown["msg_summary"] = W_MSG_SUMMARY * msgOverlap

            val diffDescOverlap = tokenOverlap(features.diffKeywords, descToks)
            breakdown["diff_desc"] = W_DIFF_DESC * diffDescOverlap

            val commentTokens = mutableSetOf<String>()
            for (c in issue.comments) {
                if (!c.body.isNullOrBlank()) commentTokens += tokenize(c.body)
            }
            val diffCommentsOverlap = tokenOverlap(features.diffKeywords, commentTokens)
            breakdown["diff_comments"] = W_DIFF_COMMENTS * diffCommentsOverlap

            val identifierOverlap = tokenOverlap(features.identifierKeywords, summaryToks + descToks)
            breakdown["identifier"] = W_IDENTIFIER * identifierOverlap

            val timeScore = timeProximityScore(features.commitDate, issue)
            breakdown["time_proximity"] = W_TIME_PROXIMITY * timeScore

            breakdown["historical"] = if (issue.issueKey in priorIssueKeys) W_HISTORICAL else 0f
            breakdown["project_whitelist"] = if (issue.projectKey in whitelist) W_PROJECT_WHITELIST else 0f

            val labelOverlap = tokenOverlap(features.identifierKeywords, labelToks)
            breakdown["labels"] = W_LABELS * labelOverlap

            val cosineDist = vectorDistances[issue.issueKey]
            if (cosineDist != null) {
                breakdown["vector_similarity"] = W_VECTOR_SIMILARITY * max(0f, 1f - cosineDist)
            } else {
                breakdown["vector_similarity"] = 0f
            }

            var total = breakdown.values.sum()

            if (exactKeyMatch && (msgOverlap + diffDescOverlap + identifierOverlap) < 0.05f) {
                breakdown["_exact_key_penalty"] = -total * 0.5f
                total *= 0.5f
            }

            if (total >= MIN_SCORE_THRESHOLD) {
                results.add(ScoredCandidate(issue = issue, totalScore = total, breakdown = breakdown))
            }
        }

        results.sortByDescending { it.totalScore }
        return results
    }

    fun scoreToConfidence(score: Float): String = when {
        score >= 120f -> "high"
        score >= 60f  -> "medium"
        score >= 20f  -> "low"
        else          -> "no_match"
    }

    private fun tokenOverlap(a: Set<String>, b: Set<String>): Float {
        if (a.isEmpty() || b.isEmpty()) return 0f
        val intersection = (a intersect b).size
        val union = (a union b).size
        return if (union == 0) 0f else intersection.toFloat() / union.toFloat()
    }

    private fun timeProximityScore(commitDateStr: String?, issue: JiraIssueData): Float {
        if (commitDateStr == null) return 0f
        val commitInstant = try {
            java.time.Instant.from(DateTimeFormatter.ISO_OFFSET_DATE_TIME.parse(commitDateStr))
        } catch (e: Exception) {
            return 0f
        }
        var best = 0f
        for (remoteInstant in listOfNotNull(issue.createdAt, issue.updatedAt)) {
            val diffDays = abs(ChronoUnit.DAYS.between(commitInstant, remoteInstant)).toFloat()
            best = max(best, max(0f, 1f - diffDays / 180f))
        }
        return best
    }

    private fun issueTextTokens(issue: JiraIssueData): Triple<Set<String>, Set<String>, Set<String>> {
        val summaryTokens = tokenize(issue.summary)
        val descTokens = tokenize(issue.description ?: "")
        val labelTokens = issue.labels.flatMapTo(mutableSetOf()) { tokenize(it) }
        return Triple(summaryTokens, descTokens, labelTokens)
    }

    private fun tokenize(text: String): Set<String> =
        Regex("[a-zA-Z_][a-zA-Z0-9_]{2,}").findAll(text.lowercase())
            .mapTo(mutableSetOf()) { it.value }
}
