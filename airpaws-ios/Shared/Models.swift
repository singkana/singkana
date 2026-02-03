import Foundation

// MARK: - SharedState

struct SharedState: Codable, Equatable {
    var selectedCharacterID: String
    var lens: Lens
    var weather: Weather
    var pawprints: [PawprintStamp]
    var catDisplayName: String?
    var showNameOnWidget: Bool
    var updatedAt: Date

    static func `default`() -> SharedState {
        SharedState(
            selectedCharacterID: "cat_orange",
            lens: .cute,
            weather: .clear,
            pawprints: [],
            catDisplayName: nil,
            showNameOnWidget: false,
            updatedAt: Date()
        )
    }
}

enum Lens: String, Codable, CaseIterable, Equatable {
    case cute
    case chic
}

enum Weather: String, Codable, CaseIterable, Equatable {
    case clear
    case rain
    case snow
    case wind
    case thunder
}

// MARK: - PawprintStamp

struct PawprintStamp: Codable, Identifiable, Equatable {
    var id: String
    /// 正規化座標 (0..1)
    var x: Double
    /// 正規化座標 (0..1)
    var y: Double
    var opacity: Double
    var createdAt: Date

    init(id: String = UUID().uuidString, x: Double, y: Double, opacity: Double = 0.95, createdAt: Date = Date()) {
        self.id = id
        self.x = x
        self.y = y
        self.opacity = opacity
        self.createdAt = createdAt
    }
}

