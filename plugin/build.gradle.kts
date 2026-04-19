import org.jetbrains.intellij.platform.gradle.TestFrameworkType

repositories {
    mavenCentral()

    intellijPlatform {
        defaultRepositories()
    }
}

dependencies {
    intellijPlatform {
        intellijIdea("2025.3")

        bundledPlugin("com.intellij.java")

        testFramework(TestFrameworkType.Platform)
    }

    testImplementation("junit:junit:4.13.2")
    // other dependencies, e.g., 3rd-party libraries
}

//plugins {
//    id("java")
//    id("org.jetbrains.kotlin.jvm") version "1.9.25"
//    id("org.jetbrains.intellij.platform") version "2.1.0"
//}
//
//group = providers.gradleProperty("pluginGroup").get()
//version = providers.gradleProperty("pluginVersion").get()
//
//repositories {
//    mavenCentral()
//    intellijPlatform {
//        defaultRepositories()
//    }
//}
//
//dependencies {
//
//    intellijPlatform {
//        create(providers.gradleProperty("platformType"), providers.gradleProperty("platformVersion"))
//        bundledPlugin("com.intellij.java")
//        bundledPlugin("Git4Idea")
//        testFramework(TestFrameworkType.Platform)
//    }
//    // JSON serialization for backend requests
//    implementation("com.google.code.gson:gson:2.10.1")
//}
//
//intellijPlatform {
//    pluginConfiguration {
//        name = providers.gradleProperty("pluginName")
//        version = providers.gradleProperty("pluginVersion")
//        ideaVersion {
//            sinceBuild = providers.gradleProperty("pluginSinceBuild")
//            untilBuild = providers.gradleProperty("pluginUntilBuild")
//        }
//    }
//    signing { }
//    publishing { }
//}
//
//kotlin {
//    jvmToolchain(17)
//}
//
//// ---------------------------------------------------------------------------
//// Local deployment: builds the plugin zip and unpacks it directly into
//// the running IntelliJ IDEA's plugins directory.
////
//// Usage:
////   1. Set localIdePluginsDir in gradle.properties (see the commented example)
////   2. Run the task: Gradle panel → Tasks → whyline → deployToLocalIde
////   3. Restart IntelliJ IDEA (File → Invalidate Caches → Just Restart)
////
//// After first setup you can also use "Reload Plugin from Disk" via
////   Help → Find Action → "Reload Plugin from Disk"  (no full restart needed)
//// ---------------------------------------------------------------------------
val localIdePluginsDir: String? = providers.gradleProperty("localIdePluginsDir").orNull
//
//tasks.register<Copy>("deployToLocalIde") {
//    group = "whyline"
//    description = "Builds plugin zip and deploys it to the local IntelliJ plugins directory."
//    dependsOn("buildPlugin")
//
//    doFirst {
//        if (localIdePluginsDir == null) {
//            throw GradleException(
//                "localIdePluginsDir is not set.\n" +
//                "Add it to plugin/gradle.properties, for example:\n" +
//                "  localIdePluginsDir=/Users/you/Library/Application Support/JetBrains/IntelliJIdea2024.3/plugins"
//            )
//        }
//        // Remove the old installation so stale files don't linger.
//        delete("$localIdePluginsDir/WhyLine")
//        logger.lifecycle("Deploying WhyLine plugin to: $localIdePluginsDir")
//    }
//
//    val zipFile = layout.buildDirectory.file("distributions/WhyLine-${project.version}.zip")
//    from(zipTree(zipFile))
//    into(localIdePluginsDir ?: error("unreachable"))
//}
