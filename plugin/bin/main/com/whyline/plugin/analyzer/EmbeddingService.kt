package com.whyline.plugin.analyzer

import com.google.gson.Gson
import com.google.gson.JsonObject
import com.intellij.openapi.diagnostic.Logger
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.ConcurrentHashMap
import kotlin.math.sqrt

private val LOG = Logger.getInstance("WhyLine.EmbeddingService")
private const val EMBED_MODEL = "text-embedding-3-small"
private const val MAX_INPUT_CHARS = 8000

object EmbeddingService {

    private val cache = ConcurrentHashMap<String, FloatArray>()
    private val gson = Gson()

    fun computeVectorDistances(
        query: String,
        issues: List<JiraIssueData>,
        apiKey: String,
    ): Map<String, Float> {
        val toEmbed = issues.filter { !cache.containsKey(it.issueKey) }
        if (toEmbed.isNotEmpty()) {
            val texts = toEmbed.map { buildIssueText(it) }
            val embeddings = batchEmbed(texts, apiKey)
            for ((issue, vec) in toEmbed.zip(embeddings)) {
                if (vec != null) cache[issue.issueKey] = vec
            }
        }

        val queryVec = batchEmbed(listOf(query.take(MAX_INPUT_CHARS)), apiKey).firstOrNull() ?: return emptyMap()

        val result = mutableMapOf<String, Float>()
        for (issue in issues) {
            val issueVec = cache[issue.issueKey] ?: continue
            result[issue.issueKey] = cosineDistance(queryVec, issueVec)
        }
        return result
    }

    private fun buildIssueText(issue: JiraIssueData): String {
        val parts = mutableListOf(issue.summary)
        if (!issue.description.isNullOrBlank()) parts.add(issue.description)
        return parts.joinToString(" ").take(MAX_INPUT_CHARS)
    }

    private fun batchEmbed(texts: List<String>, apiKey: String): List<FloatArray?> {
        if (texts.isEmpty()) return emptyList()
        return try {
            val body = gson.toJson(mapOf("model" to EMBED_MODEL, "input" to texts))
            val json = httpPost("https://api.openai.com/v1/embeddings", apiKey, body)
                ?: return List(texts.size) { null }
            val obj = gson.fromJson(json, JsonObject::class.java)
            val data = obj.getAsJsonArray("data") ?: return List(texts.size) { null }
            val results = arrayOfNulls<FloatArray>(texts.size)
            data.forEach { el ->
                val item = el.asJsonObject
                val index = item.get("index").asInt
                val arr = item.getAsJsonArray("embedding")
                results[index] = FloatArray(arr.size()) { i -> arr[i].asFloat }
            }
            results.toList()
        } catch (e: Exception) {
            LOG.warn("batchEmbed failed: ${e.message}")
            List(texts.size) { null }
        }
    }

    private fun cosineDistance(a: FloatArray, b: FloatArray): Float {
        var dot = 0.0
        var normA = 0.0
        var normB = 0.0
        val len = minOf(a.size, b.size)
        for (i in 0 until len) {
            dot += a[i] * b[i]
            normA += a[i] * a[i]
            normB += b[i] * b[i]
        }
        val denom = sqrt(normA) * sqrt(normB)
        return if (denom == 0.0) 1f else (1.0 - dot / denom).toFloat().coerceIn(0f, 2f)
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
                LOG.warn("OpenAI embeddings → HTTP ${conn.responseCode}")
                return null
            }
            conn.inputStream.bufferedReader().readText()
        } finally {
            conn.disconnect()
        }
    }
}
