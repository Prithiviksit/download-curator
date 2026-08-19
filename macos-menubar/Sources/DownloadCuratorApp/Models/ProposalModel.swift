import Foundation

public struct ProposalModel: Identifiable, Codable, Equatable {
    public let id: Int
    public let file_hash: String
    public let current_path: String
    public let original_path: String
    public var proposed_filename: String
    public var proposed_destination: String
    public var category: String
    public var confidence: Double
    public var reason: String
    public var rule_based_filename: String?
    public var rule_based_destination: String?
    public var ai_filename: String?
    public var ai_destination: String?
    public var ai_reason: String?
    public var ai_confidence: Double?
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
