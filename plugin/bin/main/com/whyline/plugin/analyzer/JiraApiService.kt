package com.whyline.plugin.analyzer

import com.google.gson.Gson
import com.google.gson.JsonElement
import com.google.gson.JsonObject
import com.intellij.openapi.diagnostic.Logger
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.time.format.DateTimeFormatter
import java.util.Base64
import java.util.concurrent.ConcurrentHashMap

private val LOG = Logger.getInstance("WhyLine.JiraApiService")
private const val STALE_MILLIS = 6 * 60 * 60 * 1000L
private const val MAX_KEYWORD_TERMS = 8
private const val MAX_COMMENTS = 10

object JiraApiService {

    private val cache = ConcurrentHashMap<String, Pair<JiraIssueData, Long>>()
    private val gson = Gson()

    fun clearCache() = cache.clear()

    fun fetchCandidates(
        jiraBaseUrl: String,
        jiraEmail: String,
        jiraToken: String,
        jiraProjectKeys: List<String>,
        features: GitFeatures,
        fetchComments: Boolean,
    ): List<JiraIssueData> {
        val baseUrl = jiraBaseUrl.trimEnd('/')
        val seen = mutableSetOf<String>()
        val results = mutableListOf<JiraIssueData>()

        for (key in features.explicitJiraKeys) {
            val issue = fetchOrRefreshByKey(baseUrl, jiraEmail, jiraToken, key) ?: continue
            if (seen.add(key)) {
                val withComments = if (fetchComments) issue.copy(comments = fetchComments(baseUrl, jiraEmail, jiraToken, key)) else issue
                results.add(withComments)
            }
        }

        val keywordIssues = keywordSearch(baseUrl, jiraEmail, jiraToken, jiraProjectKeys, features, seen)
        for (issue in keywordIssues) {
            if (seen.add(issue.issueKey)) {
                val withComments = if (fetchComments) issue.copy(comments = fetchComments(baseUrl, jiraEmail, jiraToken, issue.issueKey)) else issue
                results.add(withComments)
            }
        }

        return results
    }

    private fun fetchOrRefreshByKey(baseUrl: String, email: String, token: String, key: String): JiraIssueData? {
        val cacheKey = "$baseUrl/$key"
        val cached = cache[cacheKey]
        if (cached != null && (System.currentTimeMillis() - cached.second) < STALE_MILLIS) {
            return cached.first
        }
        val raw = apiGetIssue(baseUrl, email, token, key)
        if (raw != null) {
            val issue = parseIssue(raw)
            if (issue != null) {
                cache[cacheKey] = Pair(issue, System.currentTimeMillis())
                return issue
            }
        }
        return cached?.first
    }

    private fun keywordSearch(
        baseUrl: String,
        email: String,
        token: String,
        projectKeys: List<String>,
        features: GitFeatures,
        excludeKeys: Set<String>,
    ): List<JiraIssueData> {
        val terms = (features.messageKeywords + features.identifierKeywords)
            .filter { it.length > 3 }
            .take(MAX_KEYWORD_TERMS)
        if (terms.isEmpty()) return emptyList()

        val projectClause = if (projectKeys.isNotEmpty()) {
            val keys = projectKeys.take(10).joinToString(", ") { "\"$it\"" }
            "project IN ($keys) AND "
        } else ""

        val textTerms = terms.take(4).joinToString(" ")
        val jql = "${projectClause}(summary ~ \"$textTerms\" OR description ~ \"$textTerms\") ORDER BY updated DESC"

        return apiSearch(baseUrl, email, token, jql, maxResults = 20)
            .mapNotNull { parseIssue(it) }
            .filter { it.issueKey !in excludeKeys }
            .also { issues ->
                for (issue in issues) {
                    cache["$baseUrl/${issue.issueKey}"] = Pair(issue, System.currentTimeMillis())
                }
            }
    }

    private fun fetchComments(baseUrl: String, email: String, token: String, issueKey: String): List<JiraCommentData> {
        val url = "$baseUrl/rest/api/3/issue/$issueKey/comment?maxResults=$MAX_COMMENTS&orderBy=-created"
        return try {
            val json = httpGet(url, email, token) ?: return emptyList()
            val obj = gson.fromJson(json, JsonObject::class.java)
            val comments = obj.getAsJsonArray("comments") ?: return emptyList()
            comments.take(MAX_COMMENTS).mapNotNull { el ->
                val c = el.asJsonObject
                val id = c.get("id")?.asString ?: return@mapNotNull null
                val body = extractAdfText(c.get("body"))
                val author = c.getAsJsonObject("author")?.get("displayName")?.asString
                JiraCommentData(id = id, body = body?.take(500), authorName = author)
            }
        } catch (e: Exception) {
            LOG.warn("fetchComments $issueKey: ${e.message}")
            emptyList()
        }
    }

    private fun apiGetIssue(baseUrl: String, email: String, token: String, key: String): JsonObject? {
        val url = "$baseUrl/rest/api/3/issue/$key?fields=summary,description,status,labels,created,updated"
        return try {
            val json = httpGet(url, email, token) ?: return null
            gson.fromJson(json, JsonObject::class.java)
        } catch (e: Exception) {
            LOG.warn("Jira GET issue $key: ${e.message}")
            null
        }
    }

    private fun apiSearch(baseUrl: String, email: String, token: String, jql: String, maxResults: Int): List<JsonObject> {
        val url = "$baseUrl/rest/api/3/search/jql"
        return try {
            val body = """{"jql":${gson.toJson(jql)},"maxResults":$maxResults,"fields":["summary","description","status","labels","created","updated"]}"""
            val json = httpPost(url, email, token, body) ?: return emptyList()
            val obj = gson.fromJson(json, JsonObject::class.java)
            val issues = obj.getAsJsonArray("issues") ?: return emptyList()
            issues.map { it.asJsonObject }
        } catch (e: Exception) {
            LOG.warn("Jira search: ${e.message}")
            emptyList()
        }
    }

    private fun parseIssue(raw: JsonObject): JiraIssueData? {
        val key = raw.get("key")?.asString ?: return null
        val fields = raw.getAsJsonObject("fields") ?: return null
        val summary = fields.get("summary")?.asString?.takeIf { it.isNotBlank() } ?: return null
        val projectKey = key.substringBefore("-")
        val description = extractAdfText(fields.get("description"))
        val status = fields.getAsJsonObject("status")?.get("name")?.asString
        val labels = fields.getAsJsonArray("labels")?.map { it.asString } ?: emptyList()
        val createdAt = parseDt(fields.get("created")?.asString)
        val updatedAt = parseDt(fields.get("updated")?.asString)
        return JiraIssueData(
            issueKey = key,
            projectKey = projectKey,
            summary = summary,
            description = description?.take(4000),
            status = status,
            labels = labels,
            createdAt = createdAt,
            updatedAt = updatedAt,
            comments = emptyList(),
        )
    }

    private fun extractAdfText(element: JsonElement?): String? {
        if (element == null || element.isJsonNull) return null
        if (element.isJsonPrimitive) return element.asString
        val parts = mutableListOf<String>()
        walkAdf(element.asJsonObject, parts)
        return parts.joinToString(" ").take(4000).ifBlank { null }
    }

    private fun walkAdf(node: JsonObject, out: MutableList<String>) {
        if (node.get("type")?.asString == "text" && node.has("text")) {
            out.add(node.get("text").asString)
        }
        node.getAsJsonArray("content")?.forEach { child ->
            if (child.isJsonObject) walkAdf(child.asJsonObject, out)
        }
    }

    private fun parseDt(value: String?): Instant? {
        if (value.isNullOrBlank()) return null
        return try {
            val normalized = value
                .replace(Regex("""\.\d+"""), "")
                .replace("Z", "+00:00")
                .replace(Regex("""([+-]\d{2})(\d{2})$"""), "$1:$2")
            Instant.from(DateTimeFormatter.ISO_OFFSET_DATE_TIME.parse(normalized))
        } catch (e: Exception) {
            null
        }
    }

    private fun httpGet(url: String, email: String, token: String): String? {
        val conn = URL(url).openConnection() as HttpURLConnection
        return try {
            conn.requestMethod = "GET"
            conn.setRequestProperty("Authorization", "Basic " + Base64.getEncoder().encodeToString("$email:$token".toByteArray()))
            conn.setRequestProperty("Accept", "application/json")
            conn.connectTimeout = 10_000
            conn.readTimeout = 10_000
            if (conn.responseCode !in 200..299) {
                LOG.warn("Jira GET $url → HTTP ${conn.responseCode}")
                return null
            }
            conn.inputStream.bufferedReader().readText()
        } finally {
            conn.disconnect()
        }
    }

    private fun httpPost(url: String, email: String, token: String, body: String): String? {
        val conn = URL(url).openConnection() as HttpURLConnection
        return try {
            conn.requestMethod = "POST"
            conn.doOutput = true
            conn.setRequestProperty("Authorization", "Basic " + Base64.getEncoder().encodeToString("$email:$token".toByteArray()))
            conn.setRequestProperty("Content-Type", "application/json")
            conn.setRequestProperty("Accept", "application/json")
            conn.connectTimeout = 10_000
            conn.readTimeout = 10_000
            conn.outputStream.use { it.write(body.toByteArray()) }
            if (conn.responseCode !in 200..299) {
                LOG.warn("Jira POST $url → HTTP ${conn.responseCode}")
                return null
            }
            conn.inputStream.bufferedReader().readText()
        } finally {
            conn.disconnect()
        }
    }
}
