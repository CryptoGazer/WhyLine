package com.whyline.plugin.analyzer

import java.time.Instant

data class JiraIssueData(
    val issueKey: String,
    val projectKey: String,
    val summary: String,
    val description: String?,
    val status: String?,
    val labels: List<String>,
    val createdAt: Instant?,
    val updatedAt: Instant?,
    val comments: List<JiraCommentData>,
)

data class JiraCommentData(
    val id: String,
    val body: String?,
    val authorName: String?,
)
