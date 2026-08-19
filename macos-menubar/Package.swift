// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "DownloadCuratorApp",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "DownloadCuratorApp", targets: ["DownloadCuratorApp"])
    ],
    dependencies: [],
    targets: [
        .executableTarget(
            name: "DownloadCuratorApp",
            dependencies: [],
            path: "Sources/DownloadCuratorApp"
        )
    ]
)
