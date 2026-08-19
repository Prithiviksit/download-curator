import SwiftUI

public struct EditProposalView: View {
    @Binding public var filename: String
    @Binding public var destination: String
    public let onSaveAndApprove: () -> Void
    public let onCancel: () -> Void

    public var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Edit Proposal")
                .font(.headline)

            VStack(alignment: .leading, spacing: 4) {
                Text("Filename")
                    .font(.caption.bold())
                    .foregroundColor(.secondary)
                TextField("Proposed filename", text: $filename)
                    .textFieldStyle(.roundedBorder)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Destination Folder")
                    .font(.caption.bold())
                    .foregroundColor(.secondary)
                TextField("Destination subfolder", text: $destination)
                    .textFieldStyle(.roundedBorder)
            }

            HStack {
                Button("Cancel", action: onCancel)
                    .keyboardShortcut(.cancelAction)

                Spacer()

                Button("Save & Approve") {
                    onSaveAndApprove()
                }
                .keyboardShortcut(.defaultAction)
                .buttonStyle(.borderedProminent)
            }
            .padding(.top, 6)
        }
        .padding(14)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(10)
    }
}
