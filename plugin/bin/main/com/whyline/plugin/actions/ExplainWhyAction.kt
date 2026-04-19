package com.whyline.plugin.actions

import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.ui.Messages
import com.intellij.openapi.wm.ToolWindowManager
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.psi.PsiMethod
import com.intellij.psi.PsiClass
import com.whyline.plugin.model.AnalyzeRequest
import com.whyline.plugin.services.BackendClient
import com.whyline.plugin.services.GitContextService
import com.whyline.plugin.settings.WhySettings
import com.whyline.plugin.toolwindow.WhyPanel

class ExplainWhyAction : AnAction() {

    // Must run on EDT for editor access, then dispatch background work via ProgressManager
    override fun getActionUpdateThread() = ActionUpdateThread.EDT

    override fun update(e: AnActionEvent) {
        // Show action only when an editor with a file is focused
        val editor = e.getData(CommonDataKeys.EDITOR)
        val file = e.getData(CommonDataKeys.VIRTUAL_FILE)
        e.presentation.isEnabledAndVisible = editor != null && file != null
    }

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val editor = e.getData(CommonDataKeys.EDITOR) ?: return
        val virtualFile = e.getData(CommonDataKeys.VIRTUAL_FILE) ?: return
        val psiFile = e.getData(CommonDataKeys.PSI_FILE)

        val selectionModel = editor.selectionModel
        val document = editor.document

        // Resolve line range: use selection if present, otherwise current caret line
        val (lineStart, lineEnd) = if (selectionModel.hasSelection()) {
            val start = document.getLineNumber(selectionModel.selectionStart) + 1
            val end = document.getLineNumber(selectionModel.selectionEnd) + 1
            Pair(start, end)
        } else {
            val line = document.getLineNumber(editor.caretModel.offset) + 1
            Pair(line, line)
        }

        val selectedText = selectionModel.selectedText

        // Extract PSI context (class / method names) — null-safe, best-effort
        val psiElement = psiFile?.findElementAt(editor.caretModel.offset)
        val enclosingMethod = PsiTreeUtil.getParentOfType(psiElement, PsiMethod::class.java)
        val enclosingClass = PsiTreeUtil.getParentOfType(psiElement, PsiClass::class.java)

        // Context lines around the selection (best-effort, bounded)
        // TODO: extract actual text from document for contextBefore/After
        val contextBefore: String? = null
        val contextAfter: String? = null

        val settings = WhySettings.getInstance().state
        val filePath = virtualFile.path

        // Show loading state in the Tool Window immediately
        val toolWindow = ToolWindowManager.getInstance(project).getToolWindow("WhyLine")
        toolWindow?.show()
        val whyPanel = toolWindow?.contentManager?.contents
            ?.firstOrNull()?.component as? WhyPanel
        whyPanel?.showLoading()

        // Run network call on background thread
        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "WhyLine: Analyzing…", true) {
            override fun run(indicator: ProgressIndicator) {
                val gitEvidence = GitContextService.getInstance()
                    .collectEvidence(project, virtualFile, lineStart, lineEnd)

                val request = AnalyzeRequest(
                    workspaceId = settings.workspaceId,
                    repositoryId = settings.repositoryId,
                    filePath = filePath,
                    lineStart = lineStart,
                    lineEnd = lineEnd,
                    selectedText = selectedText,
                    className = enclosingClass?.name,
                    methodName = enclosingMethod?.name,
                    contextBefore = contextBefore,
                    contextAfter = contextAfter,
                    blameSha = gitEvidence.blameSha,
                    commitMessage = gitEvidence.commitMessage,
                    branch = gitEvidence.branch,
                    commitDate = gitEvidence.commitDate,
                    rawDiff = gitEvidence.rawDiff,
                    nearbyCommits = gitEvidence.nearbyCommits,
                    enableLlm = settings.enableLlm,
                    openAiModel = settings.openAiModel,
                )

                val result = BackendClient().analyze(request)

                ApplicationManager.getApplication().invokeLater {
                    result.fold(
                        onSuccess = { response -> whyPanel?.showResult(response) },
                        onFailure = { err ->
                            whyPanel?.showError(err.message ?: "Unknown error")
                            Messages.showErrorDialog(project, err.message, "WhyLine Error")
                        },
                    )
                }
            }
        })
    }
}
