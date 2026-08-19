import AppKit
import SwiftUI
import UserNotifications

public final class AppDelegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    private var statusItem: NSStatusItem!
    private var popover: NSPopover!
    private var timer: Timer?
    private var knownProposalIDs: Set<Int> = []
    private var hasInitializedKnownIDs: Bool = false

    public func applicationDidFinishLaunching(_ notification: Notification) {
        // Configure native UserNotifications
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        center.requestAuthorization(options: [.alert, .sound, .badge]) { granted, error in
            if let error = error {
                print("Notification authorization error: \(error)")
            }
        }

        // Create popover
        popover = NSPopover()
        popover.contentSize = NSSize(width: 380, height: 420)
        popover.behavior = .transient
        popover.contentViewController = NSHostingController(rootView: MenuBarPopoverView())

        // Create status bar item
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.image = NSImage(systemSymbolName: "tray.and.arrow.down.fill", accessibilityDescription: "Download Curator")
            button.action = #selector(togglePopover)
            button.target = self
            button.sendAction(on: [.leftMouseUp, .rightMouseUp])
        }

        // Start periodic poll and badge update timer
        timer = Timer.scheduledTimer(withTimeInterval: 2.5, repeats: true) { [weak self] _ in
            self?.pollPendingProposals()
        }
        pollPendingProposals()
    }

    @objc public func togglePopover() {
        guard let button = statusItem.button else { return }

        let event = NSApp.currentEvent
        if event?.type == .rightMouseUp {
            showContextMenu()
            return
        }

        if popover.isShown {
            popover.performClose(nil)
        } else {
            showPopover()
        }
    }

    public func showPopover() {
        guard let button = statusItem.button else { return }
        popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func showContextMenu() {
        let menu = NSMenu()
        menu.addItem(NSMenuItem(title: "Downloads Curator", action: nil, keyEquivalent: ""))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Open Review Queue", action: #selector(openReviewQueue), keyEquivalent: "o"))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Quit", action: #selector(quitApp), keyEquivalent: "q"))

        statusItem.menu = menu
        statusItem.button?.performClick(nil)
        statusItem.menu = nil
    }

    @objc private func openReviewQueue() {
        showPopover()
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
            sendNativeNotification(for: newItems)
        }

        knownProposalIDs = currentIDs
    }

    private func sendNativeNotification(for newItems: [ProposalModel]) {
        let content = UNMutableNotificationContent()
        content.title = "Downloads Curator"
        content.sound = .default

        if newItems.count == 1, let item = newItems.first {
            content.subtitle = "New download ready to organize"
            content.body = "Proposed: \(item.proposed_filename)\nCategory: \(item.category)"
        } else {
            content.subtitle = "\(newItems.count) downloads ready to organize"
            let names = newItems.map { $0.proposed_filename }.prefix(3).joined(separator: ", ")
            content.body = names + (newItems.count > 3 ? " and \(newItems.count - 3) more" : "")
        }

        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil // deliver immediately
        )

        UNUserNotificationCenter.current().add(request) { error in
            if let error = error {
                print("Failed to deliver native notification: \(error)")
            }
        }
    }

    // MARK: - UNUserNotificationCenterDelegate

    // Present notification banner even if app is in foreground
    public func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound, .badge])
    }

    // Handle user clicking the notification banner
    public func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        DispatchQueue.main.async { [weak self] in
            self?.showPopover()
        }
        completionHandler()
    }
}
