package com.whyline.plugin.settings

import com.intellij.credentialStore.CredentialAttributes
import com.intellij.credentialStore.Credentials
import com.intellij.credentialStore.generateServiceName
import com.intellij.ide.passwordSafe.PasswordSafe
import com.intellij.openapi.application.ApplicationManager

/**
 * Stores and retrieves the user's OpenAI API key via JetBrains Password Safe.
 * The key is NEVER written to plugin state XML, project files, or PostgreSQL.
 */
class WhyCredentialService {

    private fun credentialAttributes(): CredentialAttributes =
        CredentialAttributes(generateServiceName("WhyLine", "openai-api-key"))

    fun saveApiKey(key: String) {
        PasswordSafe.instance.set(credentialAttributes(), Credentials("whyline", key))
    }

    fun getApiKey(): String? =
        PasswordSafe.instance.get(credentialAttributes())?.getPasswordAsString()

    fun clearApiKey() {
        PasswordSafe.instance.set(credentialAttributes(), null)
    }

    companion object {
        fun getInstance(): WhyCredentialService =
            ApplicationManager.getApplication().getService(WhyCredentialService::class.java)
    }
}
