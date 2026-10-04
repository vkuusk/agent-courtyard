// The Courtyard menu bar app: an accessory (no Dock tile) that controls one courtyard
// directory. The logic is in scripts/install.py; this app shows what it reports and runs
// what the menu says. Design: docs/design/architecture-v1.md, 9.5.
import AppKit

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
