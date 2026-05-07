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
import com.intellij.openapi.util.TextRange
import com.intellij.openapi.wm.ToolWindowManager
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.psi.PsiMethod
import com.intellij.psi.PsiClass
import com.whyline.plugin.analyzer.AnalyzerService
import com.whyline.plugin.services.GitContextService
import com.whyline.plugin.toolwindow.WhyPanel

class ExplainWhyAction : AnAction() {

    override fun getActionUpdateThread() = ActionUpdateThread.EDT

    override fun update(e: AnActionEvent) {
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

        val (lineStart, lineEnd) = if (selectionModel.hasSelection()) {
            val start = document.getLineNumber(selectionModel.selectionStart) + 1
            val end = document.getLineNumber(selectionModel.selectionEnd) + 1
            Pair(start, end)
        } else {
            val line = document.getLineNumber(editor.caretModel.offset) + 1
            Pair(line, line)
        }

        val selectedText = selectionModel.selectedText

        val psiElement = psiFile?.findElementAt(editor.caretModel.offset)
        val enclosingMethod = PsiTreeUtil.getParentOfType(psiElement, PsiMethod::class.java)
        val enclosingClass = PsiTreeUtil.getParentOfType(psiElement, PsiClass::class.java)

        val contextLines = 10
        val lineCount = document.lineCount
        val contextBefore: String? = if (lineStart > 1) {
            val fromLine = maxOf(0, lineStart - 1 - contextLines)
            val toLine = lineStart - 2
            document.getText(TextRange(
                document.getLineStartOffset(fromLine),
                document.getLineEndOffset(toLine),
            ))
        } else null
        val contextAfter: String? = if (lineEnd < lineCount) {
            val fromLine = lineEnd
            val toLine = minOf(lineCount - 1, lineEnd - 1 + contextLines)
            document.getText(TextRange(
                document.getLineStartOffset(fromLine),
                document.getLineEndOffset(toLine),
            ))
        } else null

        val filePath = virtualFile.path

        val toolWindow = ToolWindowManager.getInstance(project).getToolWindow("WhyLine")
        toolWindow?.show()
        val whyPanel = toolWindow?.contentManager?.contents
            ?.firstOrNull()?.component as? WhyPanel
        whyPanel?.showLoading()

        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "WhyLine: Analyzing…", true) {
            override fun run(indicator: ProgressIndicator) {
                val gitEvidence = GitContextService.getInstance()
                    .collectEvidence(project, virtualFile, lineStart, lineEnd)

                val result = try {
                    Result.success(AnalyzerService.analyze(
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
                    ))
                } catch (ex: Exception) {
                    Result.failure(ex)
                }

                ApplicationManager.getApplication().invokeLater {
                    result.fold(
                        onSuccess = { response -> whyPanel?.showResult(response) },
                        onFailure = { err ->
                            val detail = buildString {
                                append(err::class.simpleName ?: "Exception")
                                if (!err.message.isNullOrBlank()) append(": ${err.message}")
                                err.cause?.let { append("\nCaused by: ${it::class.simpleName}: ${it.message}") }
                            }
                            whyPanel?.showError(detail)
                            Messages.showErrorDialog(project, detail, "WhyLine Error")
                        },
                    )
                }
            }
        })
    }
}
