import AppKit

/// A small window with a step bar and one line of text, for the uninstall: install.py
/// prints its numbered steps and the bar follows them.
final class ProgressWindow {
    private let window: NSWindow
    private let bar = NSProgressIndicator()
    private let label = NSTextField(labelWithString: "")

    init(title: String, steps: Int) {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 420, height: 90),
                          styleMask: [.titled], backing: .buffered, defer: false)
        window.title = title
        window.isReleasedWhenClosed = false
        bar.style = .bar
        bar.isIndeterminate = false
        bar.minValue = 0
        bar.maxValue = Double(steps)
        bar.doubleValue = 0
        bar.frame = NSRect(x: 20, y: 44, width: 380, height: 20)
        label.frame = NSRect(x: 20, y: 16, width: 380, height: 20)
        label.lineBreakMode = .byTruncatingTail
        window.contentView?.addSubview(bar)
        window.contentView?.addSubview(label)
    }

    func show(_ text: String) {
        label.stringValue = text
        NSApp.activate(ignoringOtherApps: true)
        window.center()
        window.makeKeyAndOrderFront(nil)
    }

    /// Step `n` of the bar (1-based) has begun; `text` says what it does.
    func step(_ n: Int, _ text: String) {
        bar.doubleValue = Double(n - 1)
        label.stringValue = text
    }

    func done(_ text: String) {
        bar.doubleValue = bar.maxValue
        label.stringValue = text
    }
}
