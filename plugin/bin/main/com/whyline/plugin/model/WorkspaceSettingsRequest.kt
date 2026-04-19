package com.whyline.plugin.model

data class WorkspaceSettingsRequest(
    val openaiApiKey: String?,
)

data class WorkspaceSettingsResponse(
    val workspaceId: Int,
    val hasOpenaiKey: Boolean,
)
