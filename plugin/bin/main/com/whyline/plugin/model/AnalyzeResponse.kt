package com.whyline.plugin.model

data class ContributingIssue(
    val issueKey: String,
    val summary: String,
    val ticketUrl: String?,
)

data class ZoneResult(
    val lineStart: Int,
    val lineEnd: Int,
    val issueKey: String?,
    val summary: String,
    val confidence: String,
)

data class AnalyzeResponse(
    val anchorId: Int,
    val ticketKey: String?,
    val ticketUrl: String?,
    val summary: String,
    // single_issue | combined | grouped | git_only | no_match
    val outputMode: String,
    // high | medium | low | no_match
    val confidence: String,
    val evidenceText: String? = null,
    val fromCache: Boolean = false,
    val contributingIssues: List<ContributingIssue> = emptyList(),
    val zones: List<ZoneResult> = emptyList(),
)
