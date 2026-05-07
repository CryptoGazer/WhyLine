plugins {
    id("java")
    id("org.jetbrains.kotlin.jvm") version "2.3.0"
    id("org.jetbrains.intellij.platform") version "2.14.0"
}

group = "org.example"
version = "1.0.0"

repositories {
    mavenCentral()
    intellijPlatform {
        defaultRepositories()
    }
}

// Read more: https://plugins.jetbrains.com/docs/intellij/tools-intellij-platform-gradle-plugin.html
dependencies {
    intellijPlatform {
        local("/Applications/IntelliJ IDEA.app")
        testFramework(org.jetbrains.intellij.platform.gradle.TestFrameworkType.Platform)

        bundledPlugin("org.jetbrains.kotlin")
        bundledPlugin("com.intellij.modules.json")
        bundledPlugin("com.intellij.java")
        compatiblePlugin("PythonCore")
    }

    implementation("com.google.code.gson:gson:2.10.1")
}

intellijPlatform {
    pluginConfiguration {
        ideaVersion {
            sinceBuild = "233"
            untilBuild = "253.*"
        }

        changeNotes = """
            <ul>
                <li>Initial public release</li>
                <li>Multi-signal Jira matching via Git blame, commit history, and diff analysis</li>
                <li>Optional LLM mode with per-user OpenAI API key</li>
                <li>Auto-Register Workspace button for one-click setup</li>
                <li>Secure credential storage via JetBrains Password Safe</li>
            </ul>
        """.trimIndent()
    }
}

tasks {
    // Set the JVM compatibility versions
    withType<JavaCompile> {
        sourceCompatibility = "21"
        targetCompatibility = "21"
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_21)
    }
}
