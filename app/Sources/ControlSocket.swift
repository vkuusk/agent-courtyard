import Foundation

/// The app's control socket: one JSON line in ({"command": ...}), one JSON line out.
/// `make hub-start|stop|restart|status` and the installer talk to the app through it, so
/// a hub started from the terminal is the app's hub. Commands: status, start, stop,
/// restart, quit (with "unregister_login_item": true for an uninstall).
final class ControlSocket {
    typealias Handler = ([String: Any]) -> [String: Any]

    private let path: String
    private let handler: Handler  // called on the main thread
    private var fd: Int32 = -1

    init(path: String, handler: @escaping Handler) {
        self.path = path
        self.handler = handler
    }

    func listen() {
        unlink(path)
        fd = socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else { AppLog.write("socket: \(String(cString: strerror(errno)))"); return }
        var addr = sockaddr_un()
        addr.sun_family = sa_family_t(AF_UNIX)
        let bytes = Array(path.utf8)
        guard bytes.count < MemoryLayout.size(ofValue: addr.sun_path) else {
            AppLog.write("socket path too long: \(path)")
            return
        }
        withUnsafeMutableBytes(of: &addr.sun_path) { raw in
            raw.copyBytes(from: bytes)
            raw[bytes.count] = 0
        }
        let size = socklen_t(MemoryLayout<sockaddr_un>.size)
        let bound = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(fd, $0, size) }
        }
        guard bound == 0, Darwin.listen(fd, 8) == 0 else {
            AppLog.write("socket bind/listen: \(String(cString: strerror(errno)))")
            return
        }
        let listening = fd
        Thread.detachNewThread { [weak self] in
            while let self = self {
                let client = accept(listening, nil, nil)
                if client < 0 { break }
                self.serve(client)
            }
        }
    }

    func close() {
        if fd >= 0 { Darwin.close(fd) }
        fd = -1  // a second close is a no-op
        unlink(path)
    }

    private func serve(_ client: Int32) {
        defer { Darwin.close(client) }
        var data = Data()
        var buf = [UInt8](repeating: 0, count: 4096)
        while !data.contains(UInt8(ascii: "\n")) {
            let n = read(client, &buf, buf.count)
            if n <= 0 { break }
            data.append(buf, count: n)
        }
        let request = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
        var reply: [String: Any] = ["ok": false, "error": "bad request"]
        DispatchQueue.main.sync { reply = self.handler(request) }
        if var out = try? JSONSerialization.data(withJSONObject: reply) {
            out.append(UInt8(ascii: "\n"))
            out.withUnsafeBytes { raw in
                _ = write(client, raw.baseAddress, raw.count)
            }
        }
    }
}
