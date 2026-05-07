package com.whyline.plugin.settings

import com.intellij.credentialStore.CredentialAttributes
import com.intellij.credentialStore.Credentials
import com.intellij.credentialStore.generateServiceName
import com.intellij.ide.passwordSafe.PasswordSafe
import com.intellij.openapi.application.ApplicationManager

class WhyCredentialService {

    private fun openAiAttrs() = CredentialAttributes(generateServiceName("WhyLine", "openai-api-key"))
    private fun jiraAttrs()   = CredentialAttributes(generateServiceName("WhyLine", "jira-api-token"))

    fun saveOpenAiKey(key: String) = PasswordSafe.instance.set(openAiAttrs(), Credentials("whyline", key))
    fun getOpenAiKey(): String?    = PasswordSafe.instance.get(openAiAttrs())?.getPasswordAsString()
    fun clearOpenAiKey()           = PasswordSafe.instance.set(openAiAttrs(), null)

    fun saveJiraToken(token: String) = PasswordSafe.instance.set(jiraAttrs(), Credentials("whyline", token))
    fun getJiraToken(): String?      = PasswordSafe.instance.get(jiraAttrs())?.getPasswordAsString()
    fun clearJiraToken()             = PasswordSafe.instance.set(jiraAttrs(), null)

    companion object {
        fun getInstance(): WhyCredentialService =
            ApplicationManager.getApplication().getService(WhyCredentialService::class.java)
    }
}
