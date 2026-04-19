package com.whyline.plugin.services

import com.google.gson.Gson
import com.google.gson.GsonBuilder
import com.whyline.plugin.model.AnalyzeRequest
import com.whyline.plugin.model.AnalyzeResponse
import com.whyline.plugin.model.WorkspaceSettingsRequest
import com.whyline.plugin.model.WorkspaceSettingsResponse
import com.whyline.plugin.settings.WhyCredentialService
import com.whyline.plugin.settings.WhySettings
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration

class BackendClient {

    private val gson: Gson = GsonBuilder().create()
    private val http: HttpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(10))
        .build()

    /**
     * Sends the analysis request to the backend.
     *
     * Key resolution order on the server:
     *   1. workspace.openai_api_key (DB, stored via saveWorkspaceKey)
     *   2. X-OpenAI-Key header (sent here if useMyOpenAiKey=true)
     *   3. OPENAI_API_KEY env var on the server
     *
     * The header key is a per-session fallback for users who have NOT stored the key on the server.
     */
    fun analyze(request: AnalyzeRequest): Result<AnalyzeResponse> {
        val settings = WhySettings.getInstance().state
        val url = "${settings.backendUrl}/api/v1/analyze"
        val body = gson.toJson(request)

        val requestBuilder = HttpRequest.newBuilder()
            .uri(URI.create(url))
            .timeout(Duration.ofSeconds(30))
            .header("Content-Type", "application/json")

        // Send header key only when user opted in AND key not already stored server-side.
        // If storeKeyOnServer=true the backend already has it — no need to re-send every request.
        if (settings.useMyOpenAiKey && !settings.storeKeyOnServer) {
            val key = WhyCredentialService.getInstance().getApiKey()
            if (!key.isNullOrBlank()) {
                requestBuilder.header("X-OpenAI-Key", key)
            }
        }

        requestBuilder.POST(HttpRequest.BodyPublishers.ofString(body))

        return try {
            val response = http.send(requestBuilder.build(), HttpResponse.BodyHandlers.ofString())
            if (response.statusCode() == 200) {
                Result.success(gson.fromJson(response.body(), AnalyzeResponse::class.java))
            } else {
                Result.failure(RuntimeException("Backend returned ${response.statusCode()}: ${response.body()}"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    /**
     * Pushes the OpenAI API key to the backend workspace record.
     * Called from WhySettingsConfigurable.apply() when "Store on server" is checked.
     * Pass an empty string to clear the server-side key.
     */
    fun saveWorkspaceKey(workspaceId: Int, apiKey: String): Result<WorkspaceSettingsResponse> {
        val settings = WhySettings.getInstance().state
        val url = "${settings.backendUrl}/api/v1/workspace/$workspaceId/settings"
        val payload = WorkspaceSettingsRequest(openaiApiKey = apiKey.ifBlank { null })
        val body = gson.toJson(payload)

        val req = HttpRequest.newBuilder()
            .uri(URI.create(url))
            .timeout(Duration.ofSeconds(10))
            .header("Content-Type", "application/json")
            .PUT(HttpRequest.BodyPublishers.ofString(body))
            .build()

        return try {
            val response = http.send(req, HttpResponse.BodyHandlers.ofString())
            if (response.statusCode() == 200) {
                Result.success(gson.fromJson(response.body(), WorkspaceSettingsResponse::class.java))
            } else {
                Result.failure(RuntimeException("saveWorkspaceKey failed ${response.statusCode()}: ${response.body()}"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
