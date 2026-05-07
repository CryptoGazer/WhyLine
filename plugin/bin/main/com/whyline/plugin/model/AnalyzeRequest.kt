package com.whyline.plugin.model

data class CommitInfo(
    val sha: String,
    val message: String,
    val date: String?,
    val rawDiff: String? = null,
)
