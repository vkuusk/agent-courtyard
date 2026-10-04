import Foundation

/// The app's settings: ~/Library/Application Support/<name>/config.json, written by the
/// install and by the Settings window. The name is the bundle's.
struct Config: Codable {
    var directory: String
    var start_hub_with_app: Bool
    var start_at_login: Bool
    var editor: String?
    var bundle_id: String?
    var name: String?

    static var appName: String {
        (Bundle.main.infoDictionary?["CFBundleName"] as? String) ?? "Courtyard"
    }

    static var version: String {
        (Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String) ?? "?"
    }

    // $HOME when set (a test points the app at a scratch home), else the account's home
    static var home: URL {
        URL(fileURLWithPath: ProcessInfo.processInfo.environment["HOME"] ?? NSHomeDirectory(), isDirectory: true)
    }

    static var supportDir: URL {
        home.appendingPathComponent("Library/Application Support/\(appName)", isDirectory: true)
    }

    static var logsDir: URL {
        home.appendingPathComponent("Library/Logs/\(appName)", isDirectory: true)
    }

    static var file: URL { supportDir.appendingPathComponent("config.json") }
    static var socketPath: String { supportDir.appendingPathComponent("control.sock").path }
    static var hubLog: URL { logsDir.appendingPathComponent("hub.log") }
    static var appLog: URL { logsDir.appendingPathComponent("app.log") }

    static func load() -> Config? {
        guard let data = try? Data(contentsOf: file) else { return nil }
        return try? JSONDecoder().decode(Config.self, from: data)
    }

    func save() {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try? FileManager.default.createDirectory(at: Config.supportDir, withIntermediateDirectories: true)
        if let data = try? encoder.encode(self) {
            try? data.write(to: Config.file)
        }
    }

    var directoryURL: URL { URL(fileURLWithPath: directory, isDirectory: true) }
}

/// One line per event in app.log; the hub has its own log.
enum AppLog {
    static func write(_ text: String) {
        try? FileManager.default.createDirectory(at: Config.logsDir, withIntermediateDirectories: true)
        let stamp = ISO8601DateFormatter().string(from: Date())
        let line = "\(stamp) \(text)\n"
        if let handle = try? FileHandle(forWritingTo: Config.appLog) {
            handle.seekToEndOfFile()
            handle.write(line.data(using: .utf8)!)
            handle.closeFile()
        } else {
            try? line.write(to: Config.appLog, atomically: true, encoding: .utf8)
        }
    }
}
