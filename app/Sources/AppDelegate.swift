import AppKit
import ServiceManagement

/// The menu, the status poll and the app's lifetime (hub and postgres end with the app).
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var config: Config!
    private var supervisor: Supervisor!
    private var socket: ControlSocket!
    private var statusItem: NSStatusItem!
    private var menu = NSMenu()
    private var status: [String: Any] = [:]
    private var pollTimer: Timer?
    private var settings: SettingsWindow?
    private var quitting = false

    // menu items that change with the state
    private let stateLine = NSMenuItem(title: "hub: ...", action: nil, keyEquivalent: "")
    private let startItem = NSMenuItem(title: "Start hub", action: #selector(startHub), keyEquivalent: "")
    private let stopItem = NSMenuItem(title: "Stop hub", action: #selector(stopHub), keyEquivalent: "")
    private let restartItem = NSMenuItem(title: "Restart hub", action: #selector(restartHub), keyEquivalent: "")
    private let shiftStartItem = NSMenuItem(title: "Start shift", action: #selector(startShift), keyEquivalent: "")
    private let shiftEndItem = NSMenuItem(title: "End shift", action: #selector(endShift), keyEquivalent: "")
    private let envNote = NSMenuItem(title: "restart the hub to apply .env", action: nil, keyEquivalent: "")

    private var python: Python { Python(directory: config.directoryURL) }
    private var hubUp: Bool { (status["hub"] as? String) == "up" }
    private var shiftState: String { (status["shift"] as? String) ?? "off" }

    func applicationDidFinishLaunching(_ notification: Notification) {
        AppLog.write("\(Config.appName) \(Config.version) launching, config \(Config.file.path)")
        guard let loaded = Config.load() else {
            AppLog.write("no config: stopping")
            alert("\(Config.appName) is not set up",
                  "Run `make install` in the courtyard directory; it writes \(Config.file.path).")
            NSApp.terminate(nil)
            return
        }
        config = loaded
        AppLog.write("\(Config.appName) \(Config.version) started for \(config.directory)")
        supervisor = Supervisor(directory: config.directoryURL)
        supervisor.onChange = { [weak self] in self?.refreshMenu() }
        socket = ControlSocket(path: Config.socketPath) { [weak self] request in
            self?.handle(request) ?? ["ok": false, "error": "gone"]
        }
        socket.listen()
        applyLoginItem()
        buildStatusItem()
        pollTimer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.poll() }
        poll()
        if config.start_hub_with_app { supervisor.start() }
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if quitting { return .terminateNow }
        quit(unregisterLoginItem: false)
        return .terminateLater
    }

    // -- the menu ----------------------------------------------------------------------------

    private func buildStatusItem() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            if let url = Bundle.main.url(forResource: "menu-icon", withExtension: "png"),
               let image = NSImage(contentsOf: url) {
                image.size = NSSize(width: 18, height: 18)
                image.isTemplate = true
                button.image = image
            } else {
                button.image = NSImage(systemSymbolName: "square.grid.2x2", accessibilityDescription: Config.appName)
            }
            button.imagePosition = .imageLeading
        }
        stateLine.isEnabled = false
        envNote.isEnabled = false
        envNote.isHidden = true
        menu.autoenablesItems = false
        menu.addItem(stateLine)
        menu.addItem(.separator())
        menu.addItem(item("Open WebUI", #selector(openWebUI)))
        menu.addItem(.separator())
        menu.addItem(startItem)
        menu.addItem(stopItem)
        menu.addItem(restartItem)
        menu.addItem(.separator())
        menu.addItem(shiftStartItem)
        menu.addItem(shiftEndItem)
        menu.addItem(.separator())
        menu.addItem(item("Show hub log", #selector(showLog)))
        menu.addItem(item("Edit .env", #selector(editEnv)))
        menu.addItem(envNote)
        menu.addItem(item("Settings...", #selector(openSettings)))
        menu.addItem(item("About \(Config.appName)", #selector(about)))
        menu.addItem(.separator())
        menu.addItem(item("Uninstall...", #selector(uninstall)))
        menu.addItem(item("Quit \(Config.appName)", #selector(quitFromMenu)))
        for case let entry in menu.items where entry.action != nil { entry.target = self }
        statusItem.menu = menu
        refreshMenu()
    }

    private func item(_ title: String, _ action: Selector) -> NSMenuItem {
        let entry = NSMenuItem(title: title, action: action, keyEquivalent: "")
        entry.target = self
        return entry
    }

    private func refreshMenu() {
        let up = hubUp
        let starting = supervisor.state == .starting
        var line: String
        if up {
            let db = (status["db"] as? String) ?? "?"
            let pending = (status["pending"] as? Int) ?? 0
            let stale = (status["stale"] as? Bool) ?? false
            let shift = shiftState == "off" ? "no shift" : "shift \(shiftState)" + (stale ? " (nobody home)" : "")
            line = "hub: up (db \(db)) · \(shift) · \(pending) at the gate"
        } else if starting {
            line = "hub: starting..."
        } else if supervisor.state == .stopping {
            line = "hub: stopping..."
        } else {
            line = "hub: down"
        }
        if Config.appName != "Courtyard" { line = "\(Config.appName) · " + line }
        stateLine.title = line
        startItem.isEnabled = !up && !starting
        stopItem.isEnabled = up || starting
        restartItem.isEnabled = up
        shiftStartItem.isEnabled = up && shiftState == "off"
        shiftEndItem.isEnabled = up && shiftState != "off"
        if let button = statusItem.button {
            let pending = (status["pending"] as? Int) ?? 0
            button.title = !up ? "○" : (pending > 0 ? " \(pending)" : "")
        }
    }

    private func poll() {
        let py = python
        DispatchQueue.global().async { [weak self] in
            let report = py.status() ?? [:]
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.status = report
                if (report["hub"] as? String) == "up" { self.supervisor.noteUp() }
                self.refreshMenu()
            }
        }
    }

    // -- actions ----------------------------------------------------------------------------

    @objc private func startHub() { supervisor.start() }
    @objc private func stopHub() { supervisor.stop() }
    @objc private func restartHub() { supervisor.restart() }

    @objc private func openWebUI() { runInBackground(["open"]) }

    @objc private func showLog() {
        NSWorkspace.shared.open([Config.hubLog], withApplicationAt: URL(fileURLWithPath: "/System/Applications/Utilities/Console.app"), configuration: NSWorkspace.OpenConfiguration())
    }

    @objc private func editEnv() {
        runInBackground(["edit-env"])
        envNote.isHidden = false
    }

    @objc private func startShift() { runInBackground(["shift-start"]) }

    @objc private func endShift() {
        let py = python
        DispatchQueue.global().async { [weak self] in
            let (code, _) = py.run(["shift-end"])
            DispatchQueue.main.async {
                guard let self = self else { return }
                if code == 3 {  // shift_busy: a conversation is open
                    if self.confirm("End the shift?", "A conversation is open. End the shift anyway? Unfinished messages expire.", "End shift") {
                        self.runInBackground(["shift-end", "--force"])
                    }
                } else {
                    self.poll()
                }
            }
        }
    }

    @objc private func openSettings() {
        if settings == nil {
            settings = SettingsWindow(config: config) { [weak self] updated in self?.apply(updated) }
        }
        settings?.show()
    }

    @objc private func about() {
        let hubVersion = (status["version"] as? String) ?? "?"
        let credits = NSAttributedString(string:
            "Hub \(hubVersion) in \(config.directory)\n\((status["url"] as? String) ?? "")\n\nThe hub starts from this menu; it ends with the app.")
        NSApp.activate(ignoringOtherApps: true)
        NSApp.orderFrontStandardAboutPanel(options: [
            .applicationName: Config.appName,
            .applicationVersion: Config.version,
            .credits: credits,
        ])
    }

    @objc private func uninstall() {
        guard confirm("Uninstall \(Config.appName)?",
                      "This takes the courtyard files out of every agent's directory, stops the hub and postgres, removes the app, its settings and logs, and the directory's .venv. The database, the registrations, the charter and .env stay.",
                      "Uninstall") else { return }
        let py = python
        quitting = true
        DispatchQueue.global().async { [weak self] in
            let (code, _) = py.run(["uninstall"], timeout: 600)
            DispatchQueue.main.async {
                AppLog.write("uninstall finished (status \(code))")
                self?.socket.close()
                NSApp.terminate(nil)
            }
        }
    }

    @objc private func quitFromMenu() { quit(unregisterLoginItem: false) }

    /// Quit: ask when a shift is open (then end it, the windows stay), stop the hub,
    /// compose down, and only then let the app go.
    private func quit(unregisterLoginItem: Bool) {
        if shiftState != "off" && hubUp {
            guard confirm("A shift is open", "Quit anyway? The shift ends (its books close); the agents' windows stay open, without a hub.", "Quit") else {
                NSApp.reply(toApplicationShouldTerminate: false)
                return
            }
            _ = python.run(["shift-end", "--force", "--keep-terminals"])
        }
        quitting = true
        pollTimer?.invalidate()
        if unregisterLoginItem { setLoginItem(false) }
        supervisor.stop { [weak self] in
            guard let self = self else { return }
            DispatchQueue.global().async {
                self.supervisor.composeDown()
                DispatchQueue.main.async {
                    self.socket.close()
                    AppLog.write("quit")
                    NSApp.reply(toApplicationShouldTerminate: true)
                    NSApp.terminate(nil)
                }
            }
        }
    }

    private func apply(_ updated: Config) {
        let directoryChanged = updated.directory != config.directory
        config = updated
        config.save()
        applyLoginItem()
        if directoryChanged {
            supervisor.use(directory: config.directoryURL)
            AppLog.write("directory changed to \(config.directory)")
            poll()
        }
    }

    // -- the login item: the app in the menu bar after a login --------------------------------

    private func applyLoginItem() { setLoginItem(config.start_at_login) }

    private func setLoginItem(_ on: Bool) {
        if #available(macOS 13.0, *) {
            let service = SMAppService.mainApp
            do {
                if on, service.status != .enabled { try service.register() }
                if !on, service.status == .enabled { try service.unregister() }
            } catch {
                AppLog.write("login item: \(error)")
            }
        }
    }

    // -- the control socket --------------------------------------------------------------------

    private func handle(_ request: [String: Any]) -> [String: Any] {
        let command = (request["command"] as? String) ?? ""
        var reply: [String: Any] = ["ok": true, "directory": config.directory, "app": Config.appName]
        switch command {
        case "status":
            reply["hub"] = hubUp ? "up" : (supervisor.state == .starting ? "starting" : "down")
            if let pid = supervisor.pid { reply["pid"] = Int(pid) }
        case "start":
            supervisor.start()
        case "stop":
            supervisor.stop()
        case "restart":
            supervisor.restart()
        case "quit":
            let unregister = (request["unregister_login_item"] as? Bool) ?? false
            DispatchQueue.main.async { [weak self] in self?.quit(unregisterLoginItem: unregister) }
        default:
            reply = ["ok": false, "error": "unknown command \(command)"]
        }
        return reply
    }

    // -- helpers --------------------------------------------------------------------------------

    private func runInBackground(_ args: [String]) {
        let py = python
        DispatchQueue.global().async { [weak self] in
            _ = py.run(args)
            DispatchQueue.main.async { self?.poll() }
        }
    }

    private func confirm(_ title: String, _ text: String, _ button: String) -> Bool {
        let a = NSAlert()
        a.messageText = title
        a.informativeText = text
        a.addButton(withTitle: button)
        a.addButton(withTitle: "Cancel")
        NSApp.activate(ignoringOtherApps: true)
        return a.runModal() == .alertFirstButtonReturn
    }

    private func alert(_ title: String, _ text: String) {
        let a = NSAlert()
        a.messageText = title
        a.informativeText = text
        NSApp.activate(ignoringOtherApps: true)
        a.runModal()
    }
}
