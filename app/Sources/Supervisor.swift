import Foundation

/// The hub as the app's child: scripts/hub-launch.sh (waits for Docker, postgres up, execs
/// the hub) with COURTYARD_SUPERVISED set, so the hub accepts the WebUI's restart. An exit
/// nobody asked for is restarted after five seconds; Stop ends the hub and leaves
/// postgres; Quit also runs `docker compose down`.
final class Supervisor {
    enum State { case down, starting, up, stopping }

    private(set) var state: State = .down
    private var process: Process?
    private var wanted = false  // the operator wants the hub up (restart on exit)
    private var directory: URL
    var onChange: (() -> Void)?

    init(directory: URL) { self.directory = directory }

    func use(directory: URL) { self.directory = directory }

    var pid: Int32? { process?.processIdentifier }

    func start() {
        guard process == nil else { return }
        wanted = true
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/sh")
        p.arguments = [directory.appendingPathComponent("scripts/hub-launch.sh").path]
        p.currentDirectoryURL = directory
        var env = Python.environment()
        env["COURTYARD_SUPERVISED"] = "courtyard-app"
        p.environment = env
        try? FileManager.default.createDirectory(at: Config.logsDir, withIntermediateDirectories: true)
        if !FileManager.default.fileExists(atPath: Config.hubLog.path) {
            FileManager.default.createFile(atPath: Config.hubLog.path, contents: nil)
        }
        if let log = try? FileHandle(forWritingTo: Config.hubLog) {
            log.seekToEndOfFile()
            p.standardOutput = log
            p.standardError = log
        }
        p.terminationHandler = { [weak self] proc in
            DispatchQueue.main.async { self?.exited(proc) }
        }
        do {
            try p.run()
            process = p
            state = .starting
            AppLog.write("hub started (pid \(p.processIdentifier))")
        } catch {
            AppLog.write("hub could not start: \(error)")
            state = .down
            wanted = false
        }
        onChange?()
    }

    /// The hub answered: the status poll says so.
    func noteUp() {
        if state == .starting { state = .up; onChange?() }
    }

    func stop(then: (() -> Void)? = nil) {
        wanted = false
        guard let p = process, p.isRunning else {
            process = nil
            state = .down
            onChange?()
            then?()
            return
        }
        state = .stopping
        onChange?()
        p.terminate()  // SIGTERM; the launcher exec'd the hub, so this is the hub's pid
        DispatchQueue.global().async {
            let deadline = Date().addingTimeInterval(15)
            while p.isRunning && Date() < deadline { usleep(200_000) }
            if p.isRunning { kill(p.processIdentifier, SIGKILL) }
            DispatchQueue.main.async { then?() }
        }
    }

    func restart() {
        stop { [weak self] in self?.start() }
    }

    private func exited(_ proc: Process) {
        guard proc === process else { return }
        process = nil
        let asked = state == .stopping
        state = .down
        AppLog.write("hub exited (status \(proc.terminationStatus), \(asked ? "asked" : "not asked"))")
        onChange?()
        if wanted && !asked {
            DispatchQueue.main.asyncAfter(deadline: .now() + 5) { [weak self] in
                guard let self = self, self.wanted, self.process == nil else { return }
                AppLog.write("hub restarted after an unexpected exit")
                self.start()
            }
        }
    }

    /// `docker compose down` in the directory (containers removed, the data volume kept).
    func composeDown() {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        p.arguments = ["docker", "compose", "--profile", "tools", "down"]
        p.currentDirectoryURL = directory
        p.environment = Python.environment()
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        try? p.run()
        p.waitUntilExit()
        AppLog.write("docker compose down (status \(p.terminationStatus))")
    }
}
