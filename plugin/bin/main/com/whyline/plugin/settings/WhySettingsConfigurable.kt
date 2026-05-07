package com.whyline.plugin.settings

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.options.Configurable
import com.intellij.ui.components.JBCheckBox
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBPasswordField
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.FormBuilder
import com.whyline.plugin.analyzer.JiraApiService
import java.awt.BorderLayout
import javax.swing.JButton
import javax.swing.JComponent
import javax.swing.JOptionPane
import javax.swing.JPanel

class WhySettingsConfigurable : Configurable {

    private lateinit var openAiKeyField: JBPasswordField
    private lateinit var enableLlmBox: JBCheckBox
    private lateinit var jiraEmailField: JBTextField
    private lateinit var jiraTokenField: JBPasswordField
    private lateinit var jiraBaseUrlField: JBTextField
    private lateinit var jiraProjectKeysField: JBTextField
    private lateinit var panel: JPanel

    override fun getDisplayName() = "WhyLine"

    override fun createComponent(): JComponent {
        val fieldW = 460
        fun fixedField(f: JBTextField) {
            f.maximumSize = java.awt.Dimension(fieldW, f.preferredSize.height)
            f.preferredSize = java.awt.Dimension(fieldW, f.preferredSize.height)
        }
        fun fixedField(f: JBPasswordField) {
            f.maximumSize = java.awt.Dimension(fieldW, f.preferredSize.height)
            f.preferredSize = java.awt.Dimension(fieldW, f.preferredSize.height)
        }

        openAiKeyField = JBPasswordField().also { fixedField(it) }
        enableLlmBox = JBCheckBox("Enable LLM features")
        jiraEmailField = JBTextField().also { fixedField(it) }
        jiraTokenField = JBPasswordField().also { fixedField(it) }
        jiraBaseUrlField = JBTextField().also { fixedField(it) }
        jiraProjectKeysField = JBTextField().also { fixedField(it) }

        val updateLlmCheckbox = {
            val hasKey = String(openAiKeyField.password).isNotBlank()
            enableLlmBox.isEnabled = hasKey
            if (!hasKey) enableLlmBox.isSelected = false
        }
        openAiKeyField.document.addDocumentListener(object : javax.swing.event.DocumentListener {
            override fun insertUpdate(e: javax.swing.event.DocumentEvent) = updateLlmCheckbox()
            override fun removeUpdate(e: javax.swing.event.DocumentEvent) = updateLlmCheckbox()
            override fun changedUpdate(e: javax.swing.event.DocumentEvent) = updateLlmCheckbox()
        })

        val clearCacheBtn = JButton("Clear Issue Cache").apply {
            addActionListener {
                ApplicationManager.getApplication().executeOnPooledThread {
                    JiraApiService.clearCache()
                    javax.swing.SwingUtilities.invokeLater {
                        JOptionPane.showMessageDialog(panel, "Issue cache cleared.", "WhyLine", JOptionPane.INFORMATION_MESSAGE)
                    }
                }
            }
        }

        panel = FormBuilder.createFormBuilder()
            .addLabeledComponent(JBLabel("<html><b>OpenAI</b></html>"), JPanel())
            .addLabeledComponent("API key:", revealPanel(openAiKeyField))
            .addComponent(JBLabel("<html><small style='color:gray'>Required for LLM features. Get yours at platform.openai.com</small></html>"))
            .addComponent(enableLlmBox)
            .addSeparator()
            .addLabeledComponent(JBLabel("<html><b>Jira</b></html>"), JPanel())
            .addLabeledComponent("Email:", jiraEmailField)
            .addLabeledComponent("API token:", revealPanel(jiraTokenField))
            .addLabeledComponent("Base URL:", jiraBaseUrlField)
            .addComponent(JBLabel("<html><small style='color:gray'>e.g. https://your-site.atlassian.net</small></html>"))
            .addLabeledComponent("Project keys:", jiraProjectKeysField)
            .addComponent(JBLabel("<html><small style='color:gray'>Comma-separated, e.g. PROJ,BACK — leave blank to search all projects</small></html>"))
            .addSeparator()
            .addComponent(clearCacheBtn)
            .addComponentFillVertically(JPanel(), 0)
            .panel

        return panel
    }

    private fun revealPanel(field: JBPasswordField): JPanel {
        val btn = JButton("Show")
        btn.addActionListener {
            if (field.echoChar == ' ') {
                field.echoChar = '•'; btn.text = "Show"
            } else {
                field.echoChar = ' '; btn.text = "Hide"
            }
        }
        return JPanel(BorderLayout(4, 0)).apply {
            add(field, BorderLayout.CENTER)
            add(btn, BorderLayout.EAST)
            val h = field.preferredSize.height
            val totalW = field.preferredSize.width + btn.preferredSize.width + 4
            preferredSize = java.awt.Dimension(totalW, h)
            maximumSize = java.awt.Dimension(totalW, h)
        }
    }

    override fun isModified(): Boolean {
        val s = WhySettings.getInstance().state
        val cred = WhyCredentialService.getInstance()
        return enableLlmBox.isSelected != s.enableLlm
            || String(openAiKeyField.password) != (cred.getOpenAiKey() ?: "")
            || String(jiraTokenField.password) != (cred.getJiraToken() ?: "")
            || jiraEmailField.text.trim() != s.jiraEmail
            || jiraBaseUrlField.text.trimEnd('/') != s.jiraBaseUrl
            || jiraProjectKeysField.text.trim() != s.jiraProjectKeys
    }

    override fun apply() {
        val s = WhySettings.getInstance().state
        val cred = WhyCredentialService.getInstance()

        s.enableLlm = enableLlmBox.isSelected
        s.jiraEmail = jiraEmailField.text.trim()
        s.jiraBaseUrl = jiraBaseUrlField.text.trimEnd('/')
        s.jiraProjectKeys = jiraProjectKeysField.text.trim()

        val openAiKey = String(openAiKeyField.password)
        if (openAiKey.isNotBlank()) cred.saveOpenAiKey(openAiKey) else cred.clearOpenAiKey()

        val jiraToken = String(jiraTokenField.password)
        if (jiraToken.isNotBlank()) cred.saveJiraToken(jiraToken) else cred.clearJiraToken()
    }

    override fun reset() {
        val s = WhySettings.getInstance().state
        val cred = WhyCredentialService.getInstance()

        openAiKeyField.text = cred.getOpenAiKey() ?: ""
        enableLlmBox.isSelected = s.enableLlm
        enableLlmBox.isEnabled = (cred.getOpenAiKey() ?: "").isNotBlank()
        jiraEmailField.text = s.jiraEmail
        jiraTokenField.text = cred.getJiraToken() ?: ""
        jiraBaseUrlField.text = s.jiraBaseUrl
        jiraProjectKeysField.text = s.jiraProjectKeys
    }
}
