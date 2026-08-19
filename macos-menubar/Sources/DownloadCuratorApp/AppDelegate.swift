import AppKit
import SwiftUI
import UserNotifications

public final class AppDelegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate, NSUserNotificationCenterDelegate {
    public static var shared: AppDelegate?

    private var statusItem: NSStatusItem!
    private var popover: NSPopover!
    private var timer: Timer?
    private var knownProposalIDs: Set<Int> = []
    private var hasInitializedKnownIDs: Bool = false

    public func applicationDidFinishLaunching(_ notification: Notification) {
        AppDelegate.shared = self

        // Configure AppKit NSUserNotificationCenter
        NSUserNotificationCenter.default.delegate = self

        // Configure UserNotifications UNUserNotificationCenter
        let unCenter = UNUserNotificationCenter.current()
        unCenter.delegate = self
        unCenter.requestAuthorization(options: [.alert, .sound, .badge]) { _, _ in }

        // Create popover
        popover = NSPopover()
        popover.contentSize = NSSize(width: 380, height: 420)
        popover.behavior = .transient
        popover.contentViewController = NSHostingController(rootView: MenuBarPopoverView())

        // Create status bar item
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.image = NSImage(systemSymbolName: "tray.and.arrow.down.fill", accessibilityDescription: "Download Curator")
            button.action = #selector(statusBarButtonClicked)
            button.target = self
            button.sendAction(on: [.leftMouseUp, .rightMouseUp])
        }

        // Listen for IPC show UI requests
        DistributedNotificationCenter.default().addObserver(
            self,
            selector: #selector(handleOpenUIRequest),
            name: NSNotification.Name("com.user.downloadcurator.openUI"),
            object: nil
        )

        // Start periodic poll timer
        timer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            self?.pollPendingProposals()
        }
        pollPendingProposals()
    }

    @objc public func statusBarButtonClicked() {
        let event = NSApp.currentEvent
        if event?.type == .rightMouseUp {
            showContextMenu()
            return
        }
        togglePopover()
    }

    @objc public func togglePopover() {
        if popover.isShown {
            popover.performClose(nil)
        } else {
            showPopover()
        }
    }

    public func showPopover() {
        DispatchQueue.main.async { [weak self] in
            guard let self = self, let button = self.statusItem.button else { return }
            if !self.popover.isShown {
                self.popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
            }
            NSApp.activate(ignoringOtherApps: true)
        }
    }

    @objc private func handleOpenUIRequest() {
        showPopover()
    }

    public func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showPopover()
        return true
    }

    private func showContextMenu() {
        let menu = NSMenu()
        menu.addItem(NSMenuItem(title: "Downloads Curator", action: nil, keyEquivalent: ""))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Review Proposals Queue", action: #selector(openReviewQueue), keyEquivalent: "o"))
        menu.addItem(NSMenuItem(title: "Scan ~/Downloads Now", action: #selector(scanNowClicked), keyEquivalent: "s"))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Restart Service & Reload Config", action: #selector(restartServiceClicked), keyEquivalent: "r"))
        menu.addItem(NSMenuItem(title: "Quit", action: #selector(quitApp), keyEquivalent: "q"))

        statusItem.menu = menu
        statusItem.button?.performClick(nil)
        statusItem.menu = nil
    }

    @objc private func openReviewQueue() {
        showPopover()
    }

    @objc private func scanNowClicked() {
        Task {
            _ = try? await CuratorService.shared.triggerScan()
            await MainActor.run {
                self.pollPendingProposals()
            }
        }
    }

    @objc private func restartServiceClicked() {
        Task {
            try? await CuratorService.shared.restartService()
            await MainActor.run {
                self.pollPendingProposals()
            }
        }
    }

    @objc private func quitApp() {
        NSApplication.shared.terminate(nil)
    }

    private func pollPendingProposals() {
        Task {
            let proposals = (try? await CuratorService.shared.fetchPendingProposals()) ?? []
            await MainActor.run {
                self.updateUI(with: proposals)
            }
        }
    }

    private func updateUI(with proposals: [ProposalModel]) {
        // Update menu bar badge
        if let button = statusItem.button {
            if proposals.isEmpty {
                button.title = ""
            } else {
                button.title = " \(proposals.count)"
            }
        }

        let currentIDs = Set(proposals.map { $0.id })

        if !hasInitializedKnownIDs {
            knownProposalIDs = currentIDs
            hasInitializedKnownIDs = true
            return
        }

        // Detect newly arrived proposals
        let newItems = proposals.filter { !knownProposalIDs.contains($0.id) }
        if !newItems.isEmpty {
            sendNotification(for: newItems)
        }

        knownProposalIDs = currentIDs
    }

    private func sendNotification(for newItems: [ProposalModel]) {
        let title = "Downloads Curator"
        let subtitle: String
        let body: String

        if newItems.count == 1, let item = newItems.first {
            subtitle = "New download ready to organize"
            body = "Proposed: \(item.proposed_filename)\nFolder: \(item.proposed_destination)/"
        } else {
            subtitle = "\(newItems.count) downloads ready to organize"
            let names = newItems.map { $0.proposed_filename }.prefix(3).joined(separator: ", ")
            body = names + (newItems.count > 3 ? " and \(newItems.count - 3) more" : "")
        }

        // 1. Deliver via NSUserNotificationCenter (AppKit - guaranteed native click handling)
        let notification = NSUserNotification()
        notification.title = title
        notification.subtitle = subtitle
        notification.informativeText = body
        notification.soundName = NSUserNotificationDefaultSoundName
        NSUserNotificationCenter.default.deliver(notification)

        // 2. Also deliver via UNUserNotificationCenter
        let unContent = UNMutableNotificationContent()
        unContent.title = title
        unContent.subtitle = subtitle
        unContent.body = body
        unContent.sound = .default
        let request = UNNotificationRequest(identifier: UUID().uuidString, content: unContent, trigger: nil)
        UNUserNotificationCenter.current().add(request, withCompletionHandler: nil)
    }

    // MARK: - NSUserNotificationCenterDelegate

    public func userNotificationCenter(_ center: NSUserNotificationCenter, shouldPresent notification: NSUserNotification) -> Bool {
        return true
    }

    public func userNotificationCenter(_ center: NSUserNotificationCenter, didActivate notification: NSUserNotification) {
        showPopover()
    }

    // MARK: - UNUserNotificationCenterDelegate

    public func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound, .badge])
    }

    public func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        showPopover()
        completionHandler()
    }
}
