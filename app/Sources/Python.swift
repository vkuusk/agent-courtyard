import Foundation

/// scripts/install.py in the courtyard directory, run with the directory's own Python.
/// Every menu action and the status poll go through here; the app holds no logic.
struct Python {
    let directory: URL

    static let path = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

    var interpreter: String {
        let venv = directory.appendingPathComponent(".venv/bin/python").path
        return FileManager.default.isExecutableFile(atPath: venv) ? venv : "/usr/bin/env"
    }

    /// Runs `install.py <args>`; returns (exit status, stdout). Blocking: call it off the
    /// main thread.
    func run(_ args: [String], timeout: TimeInterval = 120) -> (Int32, String) {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: interpreter)
        var arguments = [directory.appendingPathComponent("scripts/install.py").path] + args
        if interpreter == "/usr/bin/env" { arguments.insert("python3", at: 0) }
        process.arguments = arguments
        process.currentDirectoryURL = directory
        process.environment = Python.environment()
        let out = Pipe()
        process.standardOutput = out
        process.standardError = FileHandle.nullDevice
        do {
            try process.run()
        } catch {
            AppLog.write("install.py \(args.joined(separator: " ")): \(error)")
            return (-1, "")
        }
        let data = out.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        return (process.terminationStatus, String(decoding: data, as: UTF8.self))
    }

    func status() -> [String: Any]? {
        let (code, text) = run(["status", "--json"], timeout: 30)
        guard code == 0, let data = text.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        return json
    }

    static func environment() -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = path + ":" + (env["PATH"] ?? "")
        env["HOME"] = Config.home.path
        return env
    }
}
