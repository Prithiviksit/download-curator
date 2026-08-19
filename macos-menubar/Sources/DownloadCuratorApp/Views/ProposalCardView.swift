import SwiftUI

public struct ProposalCardView: View {
    public let proposal: ProposalModel

    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Category & Confidence Badge
            HStack {
                Text(proposal.category)
                    .font(.caption.bold())
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.blue.opacity(0.15))
                    .foregroundColor(.blue)
                    .cornerRadius(6)

                Spacer()

                HStack(spacing: 4) {
                    Circle()
                        .fill(proposal.isHighConfidence ? Color.green : Color.orange)
                        .frame(width: 8, height: 8)
                    Text("\(proposal.formattedConfidence) confidence")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }

            Divider()

            // Current File Info
            VStack(alignment: .leading, spacing: 4) {
                Text("CURRENT FILE")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(.secondary)
                Text(proposal.currentFilename)
                    .font(.system(.body, design: .monospaced))
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .foregroundColor(.primary)
            }

            // Proposed Filename
            VStack(alignment: .leading, spacing: 4) {
                Text("PROPOSED FILENAME")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(.secondary)
                Text(proposal.proposed_filename)
                    .font(.system(.body, design: .monospaced).bold())
                    .foregroundColor(.accentColor)
            }

            // Proposed Destination
            VStack(alignment: .leading, spacing: 4) {
                Text("PROPOSED DESTINATION")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(.secondary)
                HStack(spacing: 4) {
                    Image(systemName: "folder.fill")
                        .foregroundColor(.yellow)
                        .font(.caption)
                    Text("\(proposal.proposed_destination)/")
                        .font(.subheadline)
                        .foregroundColor(.primary)
                }
            }

            // Reason
            VStack(alignment: .leading, spacing: 4) {
                Text("REASON")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(.secondary)
                Text(proposal.reason)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(14)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(10)
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.gray.opacity(0.2), lineWidth: 1)
        )
    }
}
