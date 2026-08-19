import Foundation

public struct ProposalModel: Identifiable, Codable, Equatable {
    public let id: Int
    public let file_hash: String
    public let current_path: String
    public let original_path: String
    public var proposed_filename: String
    public var proposed_destination: String
    public var category: String
    public let confidence: Double
    public let reason: String
    public let status: String

    public var currentFilename: String {
        URL(fileURLWithPath: current_path).lastPathComponent
    }

    public var formattedConfidence: String {
        String(format: "%.0f%%", confidence * 100)
    }

    public var isHighConfidence: Bool {
        confidence >= 0.85
    }
}
