import AppKit

/// Settings: start the hub with the app, start the app at login, the editor for .env,
/// the courtyard directory. Every change is saved at once.
final class SettingsWindow: NSObject, NSWindowDelegate {
    private var config: Config
    private let onChange: (Config) -> Void
    private var window: NSWindow!
    private let hubWithApp = NSButton(checkboxWithTitle: "Start the hub when \(Config.appName) starts", target: nil, action: nil)
    private let atLogin = NSButton(checkboxWithTitle: "Start \(Config.appName) at login", target: nil, action: nil)
    private let editor = NSTextField(string: "")
    private let directory = NSTextField(labelWithString: "")

    init(config: Config, onChange: @escaping (Config) -> Void) {
        self.config = config
        self.onChange = onChange
        super.init()
        build()
    }

    func show() {
        load()
        NSApp.activate(ignoringOtherApps: true)
        window.center()
        window.makeKeyAndOrderFront(nil)
    }

    private func build() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 460, height: 230),
                          styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "\(Config.appName) Settings"
        window.isReleasedWhenClosed = false
        window.delegate = self

        hubWithApp.target = self
        hubWithApp.action = #selector(changed)
        atLogin.target = self
        atLogin.action = #selector(changed)
        editor.placeholderString = "the system's text editor"
        editor.target = self
        editor.action = #selector(changed)
        editor.delegate = self
        let editorLabel = NSTextField(labelWithString: "Editor for .env (an app name):")
        let directoryLabel = NSTextField(labelWithString: "Courtyard directory:")
        directory.lineBreakMode = .byTruncatingMiddle
        let change = NSButton(title: "Change...", target: self, action: #selector(chooseDirectory))

        let stack = NSStackView(views: [hubWithApp, atLogin, editorLabel, editor, directoryLabel, directory, change])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 8
        stack.edgeInsets = NSEdgeInsets(top: 20, left: 20, bottom: 20, right: 20)
        stack.translatesAutoresizingMaskIntoConstraints = false
        window.contentView = stack
        editor.widthAnchor.constraint(equalToConstant: 400).isActive = true
        directory.widthAnchor.constraint(equalToConstant: 400).isActive = true
    }

    private func load() {
        hubWithApp.state = config.start_hub_with_app ? .on : .off
        atLogin.state = config.start_at_login ? .on : .off
        editor.stringValue = config.editor ?? ""
        directory.stringValue = config.directory
    }

    @objc private func changed() {
        config.start_hub_with_app = hubWithApp.state == .on
        config.start_at_login = atLogin.state == .on
        let name = editor.stringValue.trimmingCharacters(in: .whitespaces)
        config.editor = name.isEmpty ? nil : name
        onChange(config)
    }

    @objc private func chooseDirectory() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.directoryURL = config.directoryURL
        panel.message = "The courtyard directory (it holds scripts/install.py and .env)"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        let installer = url.appendingPathComponent("scripts/install.py")
        guard FileManager.default.fileExists(atPath: installer.path) else {
            let a = NSAlert()
            a.messageText = "Not a courtyard directory"
            a.informativeText = "\(url.path) has no scripts/install.py."
            a.runModal()
            return
        }
        config.directory = url.path
        directory.stringValue = config.directory
        onChange(config)
    }

    func windowWillClose(_ notification: Notification) { changed() }
}

extension SettingsWindow: NSTextFieldDelegate {
    func controlTextDidEndEditing(_ obj: Notification) { changed() }
}
