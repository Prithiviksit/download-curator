import AppKit
import Foundation

public final class CuratorService {
    public static let shared = CuratorService()

    private let baseURL = URL(string: "http://127.0.0.1:58291/api")!
    private let session = URLSession(configuration: .ephemeral)

    public func fetchPendingProposals() async throws -> [ProposalModel] {
        // Try HTTP API first
        let endpoint = baseURL.appendingPathComponent("proposals/pending")
        var request = URLRequest(url: endpoint)
        request.timeoutInterval = 2.0

        do {
            let (data, response) = try await session.data(for: request)
            if let httpRes = response as? HTTPURLResponse, httpRes.statusCode == 200 {
                let decoder = JSONDecoder()
                return try decoder.decode([ProposalModel].self, from: data)
            }
        } catch {
            // Fallback to CLI invocation
            return try fetchViaCLI()
        }
        return try fetchViaCLI()
    }

    private func fetchViaCLI() throws -> [ProposalModel] {
        let process = Process()
        let pipe = Pipe()

        // Locate download-curator binary in PATH or ~/.local/bin or current project venv
        let possiblePaths = [
            "/usr/local/bin/download-curator",
            "/opt/homebrew/bin/download-curator",
            NSHomeDirectory() + "/.local/bin/download-curator",
            NSHomeDirectory() + "/Projects/download-curator/.venv/bin/download-curator",
        ]

        var executable = "download-curator"
        for p in possiblePaths {
            if FileManager.default.fileExists(atPath: p) {
                executable = p
                break
            }
        }

        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = [executable, "pending", "--json"]
        process.standardOutput = pipe
        process.standardError = Pipe()

        try process.run()
        process.waitUntilExit()

        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        if data.isEmpty {
            return []
        }

        let decoder = JSONDecoder()
        return (try? decoder.decode([ProposalModel].self, from: data)) ?? []
    }

    public func approveProposal(
        id: Int,
        customFilename: String? = nil,
        customDestination: String? = nil
    ) async throws {
        let endpoint = baseURL.appendingPathComponent("proposals/\(id)/approve")
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 5.0

        var bodyDict: [String: String] = [:]
        if let fn = customFilename { bodyDict["proposed_filename"] = fn }
        if let dst = customDestination { bodyDict["proposed_destination"] = dst }
        request.httpBody = try? JSONSerialization.data(withJSONObject: bodyDict)

        do {
            let (_, response) = try await session.data(for: request)
            if let httpRes = response as? HTTPURLResponse, httpRes.statusCode == 200 {
                return
            }
        } catch {
            // Fallback to CLI
            try runCLIApprove(id: id, filename: customFilename, destination: customDestination)
        }
    }

    private func runCLIApprove(id: Int, filename: String?, destination: String?) throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        var args = ["download-curator", "approve", "\(id)"]
        if let fn = filename { args.append(contentsOf: ["--filename", fn]) }
        if let dst = destination { args.append(contentsOf: ["--destination", dst]) }
        process.arguments = args
        try process.run()
        process.waitUntilExit()
    }

    public func rejectProposal(id: Int) async throws {
        let endpoint = baseURL.appendingPathComponent("proposals/\(id)/reject")
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.timeoutInterval = 3.0
        _ = try? await session.data(for: request)
    }

    public func ignoreProposal(id: Int) async throws {
        let endpoint = baseURL.appendingPathComponent("proposals/\(id)/ignore")
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.timeoutInterval = 3.0
        _ = try? await session.data(for: request)
    }

    public func enhanceWithAI(id: Int) async throws -> ProposalModel {
        let endpoint = baseURL.appendingPathComponent("proposals/\(id)/ai_enhance")
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.timeoutInterval = 30.0

        let (data, response) = try await session.data(for: request)
        if let httpRes = response as? HTTPURLResponse, httpRes.statusCode == 200 {
            let decoder = JSONDecoder()
            return try decoder.decode(ProposalModel.self, from: data)
        }
        throw NSError(domain: "CuratorService", code: 500, userInfo: [NSLocalizedDescriptionKey: "AI enhancement failed"])
    }

    public func openFile(path: String) {
        let url = URL(fileURLWithPath: path)
        NSWorkspace.shared.open(url)
    }

    public func revealInFinder(path: String) {
        let url = URL(fileURLWithPath: path)
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }
}
