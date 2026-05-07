package com.whyline.plugin.settings

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage

@State(name = "WhyLineSettings", storages = [Storage("whyline.xml")])
class WhySettings : PersistentStateComponent<WhySettings.State> {

    data class State(
        var enableLlm: Boolean = false,
        var openAiModel: String = "gpt-4o",
        var jiraEmail: String = "",
        var jiraBaseUrl: String = "",
        var jiraProjectKeys: String = "",
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
