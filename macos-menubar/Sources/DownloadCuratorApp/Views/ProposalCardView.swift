import SwiftUI

public struct ProposalCardView: View {
    public let proposal: ProposalModel
    public var onSelectName: ((String, String) -> Void)? = nil

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
                Text("ACTIVE PROPOSED FILENAME")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(.secondary)
                Text(proposal.proposed_filename)
                    .font(.system(.body, design: .monospaced).bold())
                    .foregroundColor(.accentColor)
            }

            // Comparison Section if AI comparison is available
            if let aiName = proposal.ai_filename {
                let ruleName = proposal.rule_based_filename ?? proposal.proposed_filename
                let isMatch = (aiName == ruleName)

                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text("COMPARE PROPOSALS")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(.secondary)
                        if isMatch {
                            Text("• Both Engines Agree")
                                .font(.caption2.bold())
                                .foregroundColor(.green)
                        }
                    }

                    // Rule-Based option
                    Button(action: {
                        onSelectName?(ruleName, proposal.rule_based_destination ?? proposal.proposed_destination)
                    }) {
                        HStack {
                            Image(systemName: proposal.proposed_filename == ruleName ? "largecircle.fill.circle" : "circle")
                                .foregroundColor(proposal.proposed_filename == ruleName ? .blue : .secondary)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Rule-Based Heuristic")
                                    .font(.caption2.bold())
                                    .foregroundColor(.secondary)
                                Text(ruleName)
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundColor(.primary)
                            }
                            Spacer()
                        }
                        .padding(6)
                        .background(proposal.proposed_filename == ruleName ? Color.blue.opacity(0.12) : Color.clear)
                        .cornerRadius(6)
                    }
                    .buttonStyle(.plain)

                    // AI Model option
                    Button(action: {
                        onSelectName?(aiName, proposal.ai_destination ?? proposal.proposed_destination)
                    }) {
                        HStack {
                            Image(systemName: proposal.proposed_filename == aiName ? "largecircle.fill.circle" : "circle")
                                .foregroundColor(proposal.proposed_filename == aiName ? .purple : .secondary)
                            VStack(alignment: .leading, spacing: 2) {
                                HStack(spacing: 4) {
                                    Text("AI Model (LLM)")
                                        .font(.caption2.bold())
                                        .foregroundColor(.purple)
                                    if let reason = proposal.ai_reason {
                                        Text("• \(reason)")
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                            .lineLimit(1)
                                    }
                                }
                                Text(aiName)
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundColor(.primary)
                            }
                            Spacer()
                        }
                        .padding(6)
                        .background(proposal.proposed_filename == aiName ? Color.purple.opacity(0.12) : Color.clear)
                        .cornerRadius(6)
                    }
                    .buttonStyle(.plain)
                }
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
            if proposal.ai_filename == nil {
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
