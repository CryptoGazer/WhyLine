package com.whyline.plugin.settings

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage

@State(name = "WhyLineSettings", storages = [Storage("whyline.xml")])
class WhySettings : PersistentStateComponent<WhySettings.State> {

    data class State(
        var backendUrl: String = "http://localhost:8000",
        var enableLlm: Boolean = true,
        // useMyOpenAiKey: key stored in JetBrains Password Safe, sent per-request in header.
        // storeKeyOnServer: key is also pushed to the workspace record in the backend DB
        //   so all team members share it without each configuring their own.
        var useMyOpenAiKey: Boolean = false,
        var storeKeyOnServer: Boolean = false,
        var openAiModel: String = "gpt-4o",
        // Workspace / repo IDs — set once during onboarding
        // TODO: replace with per-project settings once project-level config is added
        var workspaceId: Int = 1,
        var repositoryId: Int = 1,
    )

    private var state = State()

    override fun getState(): State = state

    override fun loadState(state: State) {
        this.state = state
    }

    companion object {
        fun getInstance(): WhySettings =
            ApplicationManager.getApplication().getService(WhySettings::class.java)
    }
}
