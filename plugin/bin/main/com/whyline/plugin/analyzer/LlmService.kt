package com.whyline.plugin.analyzer

import com.google.gson.Gson
import com.google.gson.JsonObject
import com.intellij.openapi.diagnostic.Logger
import java.net.HttpURLConnection
import java.net.URL

private val LOG = Logger.getInstance("WhyLine.LlmService")
private val GSON = Gson()

object LlmService {

    fun rerankCandidates(
        features: GitFeatures,
        scored: List<ScoredCandidate>,
        model: String,
        apiKey: String,
        topN: Int = 10,
    ): List<ScoredCandidate> {
        if (scored.isEmpty()) return scored
        val toRank = scored.take(topN)
        val commitText = features.commitMessages.take(3).joinToString("\n")
        val candidateLines = toRank.mapIndexed { i, c ->
            "${i + 1}. [${c.issue.issueKey}] ${c.issue.summary} (score: ${"%.0f".format(c.totalScore)})"
        }.joinToString("\n")

        val prompt = "You are ranking Jira issues by relevance to a code change.\n\n" +
            "Commit messages:\n$commitText\n\n" +
            "Candidates (already pre-scored):\n$candidateLines\n\n" +
            "Return ONLY a comma-separated list of the candidate numbers in order of relevance, " +
            "most relevant first. Example: 3,1,2,5,4"

        return try {
            val response = chatCompletion(prompt, model, maxTokens = 64, temperature = 0.0, apiKey = apiKey)
                ?: return scored
            val indices = response.split(",")
                .mapNotNull { it.trim().toIntOrNull()?.minus(1) }
                .filter { it in toRank.indices }
            val reranked = indices.map { toRank[it] }.toMutableList()
            val mentioned = indices.toSet()
            for (i in toRank.indices) { if (i !in mentioned) reranked.add(toRank[i]) }
            reranked + scored.drop(topN)
        } catch (e: Exception) {
            LOG.warn("LLM rerank failed: ${e.message}")
            scored
        }
    }

    fun generateExplanation(
        features: GitFeatures,
        topCandidates: List<ScoredCandidate>,
        outputMode: String,
        model: String,
        apiKey: String,
    ): String {
        val commitText = features.commitMessages.take(3).joinToString("\n")

        val prompt = when (outputMode) {
            "git_only" ->
                "Explain in 2-3 sentences why this code likely changed, " +
                    "based only on the commit messages below. No Jira context is available.\n\nCommits:\n$commitText"

            "combined" -> {
                val issuesText = topCandidates.take(3).joinToString("\n") {
                    "- [${it.issue.issueKey}] ${it.issue.summary}"
                }
                "Explain in 2-4 sentences why the selected code block changed. " +
                    "Multiple Jira issues contributed to this change — describe the combined context.\n\n" +
                    "Commit messages:\n$commitText\n\nContributing Jira issues:\n$issuesText"
            }

            "no_match" -> return "No matching Jira issue found for this code change."

            else -> {
                if (topCandidates.isEmpty()) return "No matching Jira issue found for this code change."
                val best = topCandidates[0]
                val commentsText = best.issue.comments.take(3)
                    .mapNotNull { it.body?.trim()?.takeIf { b -> b.isNotEmpty() }?.take(200) }
                    .joinToString("\n") { "- $it" }
                "Explain in 2-3 sentences why this code changed, " +
                    "linking it to the Jira issue below.\n\n" +
                    "Commit: $commitText\n" +
                    "Jira issue [${best.issue.issueKey}]: ${best.issue.summary}\n" +
                    "Description: ${best.issue.description?.take(500) ?: "(none)"}" +
                    (if (commentsText.isNotBlank()) "\nTop comments:\n$commentsText" else "")
            }
        }

        return try {
            chatCompletion(prompt, model, maxTokens = 256, temperature = 0.3, apiKey = apiKey)
                ?: fallback(topCandidates, commitText)
        } catch (e: Exception) {
            LOG.warn("LLM explanation failed: ${e.message}")
            fallback(topCandidates, commitText)
        }
    }

    private fun fallback(candidates: List<ScoredCandidate>, commitText: String): String {
        if (candidates.isNotEmpty()) {
            val best = candidates[0]
            return "This code was likely changed in relation to [${best.issue.issueKey}]: ${best.issue.summary}. (LLM explanation unavailable.)"
        }
        return "Change context: ${commitText.take(200)}"
    }

    private fun chatCompletion(
        prompt: String,
        model: String,
        maxTokens: Int,
        temperature: Double,
        apiKey: String,
    ): String? {
        val body = GSON.toJson(mapOf(
            "model" to model,
            "messages" to listOf(mapOf("role" to "user", "content" to prompt)),
            "max_tokens" to maxTokens,
            "temperature" to temperature,
        ))
        return try {
            val json = httpPost("https://api.openai.com/v1/chat/completions", apiKey, body) ?: return null
            val obj = GSON.fromJson(json, JsonObject::class.java)
            obj.getAsJsonArray("choices")?.firstOrNull()?.asJsonObject
                ?.getAsJsonObject("message")?.get("content")?.asString?.trim()
        } catch (e: Exception) {
            LOG.warn("chatCompletion failed: ${e.message}")
            null
        }
    }

    private fun httpPost(url: String, apiKey: String, body: String): String? {
        val conn = URL(url).openConnection() as HttpURLConnection
        return try {
            conn.requestMethod = "POST"
            conn.doOutput = true
            conn.setRequestProperty("Authorization", "Bearer $apiKey")
            conn.setRequestProperty("Content-Type", "application/json")
            conn.connectTimeout = 30_000
            conn.readTimeout = 30_000
            conn.outputStream.use { it.write(body.toByteArray()) }
            if (conn.responseCode !in 200..299) {
                LOG.warn("OpenAI chat → HTTP ${conn.responseCode}")
                return null
            }
            conn.inputStream.bufferedReader().readText()
        } finally {
            conn.disconnect()
        }
    }
}
