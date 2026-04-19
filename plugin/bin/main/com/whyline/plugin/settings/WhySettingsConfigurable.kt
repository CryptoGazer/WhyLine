package com.whyline.plugin.settings

import com.intellij.openapi.options.Configurable
import com.intellij.ui.components.JBCheckBox
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBPasswordField
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.FormBuilder
import com.whyline.plugin.services.BackendClient
import javax.swing.JComponent
import javax.swing.JPanel

class WhySettingsConfigurable : Configurable {

    private lateinit var backendUrlField: JBTextField
    private lateinit var enableLlmBox: JBCheckBox
    private lateinit var useMyKeyBox: JBCheckBox
    private lateinit var storeOnServerBox: JBCheckBox
    private lateinit var apiKeyField: JBPasswordField
    private lateinit var modelField: JBTextField
    private lateinit var panel: JPanel

    override fun getDisplayName() = "WhyLine"

    override fun createComponent(): JComponent {
        backendUrlField = JBTextField()
        enableLlmBox = JBCheckBox("Enable LLM features (requires OpenAI API key)")
        useMyKeyBox = JBCheckBox("Use my OpenAI API key")
        storeOnServerBox = JBCheckBox("Store key on server (workspace-wide — shared with team)")
        apiKeyField = JBPasswordField()
        modelField = JBTextField()

        val keyHint = JBLabel(
            "<html><small style='color:gray'>Key is saved in JetBrains Password Safe. " +
            "If 'Store on server' is checked, it is also sent to and stored in the WhyLine backend " +
            "so all team members benefit without configuring their own key.</small></html>"
        )

        panel = FormBuilder.createFormBuilder()
            .addLabeledComponent("Backend URL:", backendUrlField)
            .addComponent(enableLlmBox)
            .addSeparator()
            .addComponent(useMyKeyBox)
            .addLabeledComponent("OpenAI API key:", apiKeyField)
            .addComponent(storeOnServerBox)
            .addComponent(keyHint)
            .addLabeledComponent("Model:", modelField)
            .addComponentFillVertically(JPanel(), 0)
            .panel

        useMyKeyBox.addActionListener { syncKeyFieldState() }

        return panel
    }

    private fun syncKeyFieldState() {
        val enabled = useMyKeyBox.isSelected
        apiKeyField.isEnabled = enabled
        storeOnServerBox.isEnabled = enabled
    }

    override fun isModified(): Boolean {
        val s = WhySettings.getInstance().state
        val currentKey = WhyCredentialService.getInstance().getApiKey() ?: ""
        return backendUrlField.text != s.backendUrl
            || enableLlmBox.isSelected != s.enableLlm
            || useMyKeyBox.isSelected != s.useMyOpenAiKey
            || storeOnServerBox.isSelected != s.storeKeyOnServer
            || String(apiKeyField.password) != currentKey
            || modelField.text != s.openAiModel
    }

    override fun apply() {
        val s = WhySettings.getInstance().state
        s.backendUrl = backendUrlField.text.trimEnd('/')
        s.enableLlm = enableLlmBox.isSelected
        s.useMyOpenAiKey = useMyKeyBox.isSelected
        s.storeKeyOnServer = storeOnServerBox.isSelected
        s.openAiModel = modelField.text.trim()

        val typedKey = String(apiKeyField.password)

        if (useMyKeyBox.isSelected && typedKey.isNotBlank()) {
            // Always store locally in Password Safe
            WhyCredentialService.getInstance().saveApiKey(typedKey)

            // Optionally push to backend so team members share it
            if (storeOnServerBox.isSelected) {
                BackendClient().saveWorkspaceKey(s.workspaceId, typedKey)
            }
        } else if (!useMyKeyBox.isSelected) {
            WhyCredentialService.getInstance().clearApiKey()
            // Clear server-side key too if "store on server" was previously enabled
            if (s.storeKeyOnServer) {
                BackendClient().saveWorkspaceKey(s.workspaceId, "")
            }
        }
    }

    override fun reset() {
        val s = WhySettings.getInstance().state
        backendUrlField.text = s.backendUrl
        enableLlmBox.isSelected = s.enableLlm
        useMyKeyBox.isSelected = s.useMyOpenAiKey
        storeOnServerBox.isSelected = s.storeKeyOnServer
        apiKeyField.text = WhyCredentialService.getInstance().getApiKey() ?: ""
        modelField.text = s.openAiModel
        syncKeyFieldState()
    }
}
