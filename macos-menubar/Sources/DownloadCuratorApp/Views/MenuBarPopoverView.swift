import SwiftUI

public struct MenuBarPopoverView: View {
    @State private var proposals: [ProposalModel] = []
    @State private var currentIndex: Int = 0
    @State private var isEditing: Bool = false
    @State private var editFilename: String = ""
    @State private var editDestination: String = ""
    @State private var isLoading: Bool = false
    @State private var statusMessage: String? = nil

    private let timer = Timer.publish(every: 3.0, on: .main, in: .common).autoconnect()

    public var currentProposal: ProposalModel? {
        guard !proposals.isEmpty, currentIndex < proposals.count else { return nil }
        return proposals[currentIndex]
    }

    public var body: some View {
        VStack(spacing: 12) {
            // Header
            HStack {
                Image(systemName: "tray.full.fill")
                    .foregroundColor(.accentColor)
                Text("Downloads Curator")
                    .font(.headline)

                Spacer()

                if !proposals.isEmpty {
                    Text("\(currentIndex + 1) of \(proposals.count)")
                        .font(.caption.monospaced())
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.gray.opacity(0.15))
                        .cornerRadius(4)
                }

                Button(action: refreshData) {
                    Image(systemName: "arrow.clockwise")
                        .font(.caption)
                }
                .buttonStyle(.plain)
                .help("Refresh proposals")
            }
            .padding(.horizontal, 14)
            .padding(.top, 12)

            Divider()

            if isLoading && proposals.isEmpty {
                VStack(spacing: 8) {
                    ProgressView()
                    Text("Loading proposals...")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, minHeight: 200)
            } else if let proposal = currentProposal {
                if isEditing {
                    EditProposalView(
                        filename: $editFilename,
                        destination: $editDestination,
                        onSaveAndApprove: {
                            Task {
                                await approveCurrent(
                                    customFilename: editFilename,
                                    customDestination: editDestination
                                )
                                isEditing = false
                            }
                        },
                        onCancel: {
                            isEditing = false
                        }
                    )
                    .padding(.horizontal, 14)
                } else {
                    ProposalCardView(proposal: proposal)
                        .padding(.horizontal, 14)

                    // Secondary Quick Actions
                    HStack(spacing: 8) {
                        Button(action: {
                            CuratorService.shared.openFile(path: proposal.current_path)
                        }) {
                            Label("Open File", systemImage: "doc")
                        }
                        .keyboardShortcut(.space, modifiers: [])

                        Button(action: {
                            CuratorService.shared.revealInFinder(path: proposal.current_path)
                        }) {
                            Label("Reveal in Finder", systemImage: "magnifyingglass")
                        }

                        Spacer()

                        Button("Ignore") {
                            Task { await ignoreCurrent() }
                        }
                        .keyboardShortcut("i", modifiers: [])
                        .foregroundColor(.red)

                        Button("Skip") {
                            nextProposal()
                        }
                    }
                    .font(.caption)
                    .padding(.horizontal, 14)

                    Divider()

                    // Primary Actions Bar
                    HStack(spacing: 12) {
                        // Previous / Next Buttons
                        HStack(spacing: 4) {
                            Button(action: prevProposal) {
                                Image(systemName: "chevron.left")
                            }
                            .disabled(currentIndex == 0)

                            Button(action: nextProposal) {
                                Image(systemName: "chevron.right")
                            }
                            .disabled(currentIndex >= proposals.count - 1)
                        }

                        Button("Edit (E)") {
                            editFilename = proposal.proposed_filename
                            editDestination = proposal.proposed_destination
                            isEditing = true
                        }
                        .keyboardShortcut("e", modifiers: [])

                        Spacer()

                        Button(action: {
                            Task { await approveCurrent() }
                        }) {
                            Text("Approve")
                                .bold()
                        }
                        .keyboardShortcut(.return, modifiers: [])
                        .buttonStyle(.borderedProminent)
                        .tint(.green)
                    }
                    .padding(.horizontal, 14)
                    .padding(.bottom, 12)
                }
            } else {
                VStack(spacing: 10) {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 32))
                        .foregroundColor(.green)
                    Text("No Pending Downloads")
                        .font(.headline)
                    Text("New downloads appearing in ~/Downloads will be analyzed and queued here for your explicit approval.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 20)
                }
                .frame(maxWidth: .infinity, minHeight: 180)
                .padding(.bottom, 12)
            }

            if let msg = statusMessage {
                Text(msg)
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .padding(.bottom, 4)
            }
        }
        .frame(width: 380)
        .onAppear {
            refreshData()
        }
        .onReceive(timer) { _ in
            if !isEditing {
                refreshDataSilently()
            }
        }
    }

    private func refreshData() {
        isLoading = true
        Task {
            do {
                let items = try await CuratorService.shared.fetchPendingProposals()
                await MainActor.run {
                    self.proposals = items
                    if self.currentIndex >= items.count {
                        self.currentIndex = max(0, items.count - 1)
                    }
                    self.isLoading = false
                }
            } catch {
                await MainActor.run {
                    self.isLoading = false
                }
            }
        }
    }

    private func refreshDataSilently() {
        Task {
            if let items = try? await CuratorService.shared.fetchPendingProposals() {
                await MainActor.run {
                    self.proposals = items
                    if self.currentIndex >= items.count {
                        self.currentIndex = max(0, items.count - 1)
                    }
                }
            }
        }
    }

    private func approveCurrent(customFilename: String? = nil, customDestination: String? = nil) async {
        guard let p = currentProposal else { return }
        do {
            try await CuratorService.shared.approveProposal(
                id: p.id,
                customFilename: customFilename,
                customDestination: customDestination
            )
            refreshData()
        } catch {
            statusMessage = "Approval failed: \(error.localizedDescription)"
        }
    }

    private func ignoreCurrent() async {
        guard let p = currentProposal else { return }
        try? await CuratorService.shared.ignoreProposal(id: p.id)
        refreshData()
    }

    private func nextProposal() {
        if currentIndex < proposals.count - 1 {
            currentIndex += 1
        }
    }

    private func prevProposal() {
        if currentIndex > 0 {
            currentIndex -= 1
        }
    }
}
