import Foundation

final class SharedStore {
    static let shared = SharedStore()

    private let defaults: UserDefaults?
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    private init() {
        self.defaults = UserDefaults(suiteName: AppConstants.appGroupID)
        encoder.dateEncodingStrategy = .iso8601
        decoder.dateDecodingStrategy = .iso8601
    }

    func load() -> SharedState {
        guard
            let defaults,
            let data = defaults.data(forKey: AppConstants.sharedStateKey),
            let decoded = try? decoder.decode(SharedState.self, from: data)
        else {
            return .default()
        }
        return decoded
    }

    func save(_ state: SharedState) {
        guard let defaults else { return }
        guard let data = try? encoder.encode(state) else { return }
        defaults.set(data, forKey: AppConstants.sharedStateKey)
    }

    func update(_ mutate: (inout SharedState) -> Void) {
        var state = load()
        mutate(&state)
        state.updatedAt = Date()
        save(state)
    }
}

