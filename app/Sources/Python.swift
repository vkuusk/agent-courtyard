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
        run(args, timeout: timeout, onLine: nil)
    }

    /// The same, with every line of output handed to `onLine` on the main thread as it
    /// is printed (the uninstall's progress window follows install.py's numbered steps).
    func run(_ args: [String], timeout: TimeInterval, onLine: ((String) -> Void)?) -> (Int32, String) {
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
        var collected = Data()
        if let onLine = onLine {
            var pending = ""
            out.fileHandleForReading.readabilityHandler = { handle in
                let chunk = handle.availableData
                if chunk.isEmpty { return }
                collected.append(chunk)
                pending += String(decoding: chunk, as: UTF8.self)
                while let nl = pending.firstIndex(of: "\n") {
                    let line = String(pending[..<nl])
                    pending = String(pending[pending.index(after: nl)...])
                    DispatchQueue.main.async { onLine(line) }
                }
            }
            process.waitUntilExit()
            out.fileHandleForReading.readabilityHandler = nil
            let rest = out.fileHandleForReading.readDataToEndOfFile()
            collected.append(rest)
            if !rest.isEmpty || !pending.isEmpty {
                let tail = pending + String(decoding: rest, as: UTF8.self)
                for line in tail.split(separator: "\n", omittingEmptySubsequences: true) {
                    let text = String(line)
                    DispatchQueue.main.async { onLine(text) }
                }
            }
            return (process.terminationStatus, String(decoding: collected, as: UTF8.self))
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
