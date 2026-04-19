package com.whyline.plugin.toolwindow

import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBScrollPane
import com.intellij.util.ui.JBUI
import com.whyline.plugin.model.AnalyzeResponse
import java.awt.BorderLayout
import java.awt.Font
import javax.swing.JPanel
import javax.swing.JTextArea
import javax.swing.SwingConstants

class WhyPanel : JPanel(BorderLayout()) {

    private val statusLabel = JBLabel("Select code and right-click → WhyLine: Explain Why", SwingConstants.CENTER)
    private val summaryArea = JTextArea().apply {
        lineWrap = true
        wrapStyleWord = true
        isEditable = false
        border = JBUI.Borders.empty(8)
        font = Font(Font.SANS_SERIF, Font.PLAIN, 13)
    }
    private val metaLabel = JBLabel("").apply {
        border = JBUI.Borders.empty(4, 8)
        font = Font(Font.MONOSPACED, Font.PLAIN, 11)
    }

    init {
        add(statusLabel, BorderLayout.NORTH)
        add(JBScrollPane(summaryArea), BorderLayout.CENTER)
        add(metaLabel, BorderLayout.SOUTH)
    }

    fun showLoading() {
        statusLabel.text = "Analyzing…"
        summaryArea.text = ""
        metaLabel.text = ""
    }

    fun showResult(response: AnalyzeResponse) {
        val confidenceTag = "[${response.confidence.uppercase()}]"
        val modeTag = "[${response.outputMode}]"
        val cacheTag = if (response.fromCache) " [cached]" else ""

        statusLabel.text = "${response.ticketKey ?: "no match"} — $confidenceTag $modeTag$cacheTag"
        summaryArea.text = buildString {
            append(response.summary)
            if (response.contributingIssues.isNotEmpty()) {
                append("\n\nContributing issues:")
                response.contributingIssues.forEach { append("\n  • ${it.issueKey} — ${it.summary}") }
            }
            if (response.zones.isNotEmpty()) {
                append("\n\nZone breakdown:")
                response.zones.forEach { z ->
                    append("\n  Lines ${z.lineStart}–${z.lineEnd}: ${z.issueKey ?: "no match"} (${z.confidence})")
                    append("\n    ${z.summary}")
                }
            }
            if (!response.evidenceText.isNullOrBlank()) {
                append("\n\nEvidence:\n${response.evidenceText}")
            }
        }
        metaLabel.text = response.ticketUrl ?: ""

        // TODO: make ticket URL clickable via HyperlinkLabel
        // TODO: add "open in browser" button next to ticket key
    }

    fun showError(message: String) {
        statusLabel.text = "Error"
        summaryArea.text = message
        metaLabel.text = ""
    }
}
