# plugin

JetBrains IDE plugin (IntelliJ Platform SDK).

## Responsibilities

- Detect the currently open file and selected line range.
- Run `git blame` and `git log` locally via JGit.
- Build and send a normalized Git evidence bundle to the backend.
- Render the returned ticket link and summary in a tool window or inline popup.

## TODO

- [ ] Scaffold IntelliJ plugin project (build.gradle.kts, plugin.xml)
- [ ] Implement GitReader using JGit
- [ ] Implement evidence bundle serialization
- [ ] Implement HTTP client for backend API
- [ ] Implement result UI (tool window)
